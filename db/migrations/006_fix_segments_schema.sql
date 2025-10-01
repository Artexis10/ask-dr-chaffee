-- Fix segments table schema issues
-- Migration 006: Fix embedding dimensions, speaker labels, and add source reference

-- 1. Fix embedding dimension for GTE-Qwen2-1.5B-instruct (1536 dimensions)
ALTER TABLE segments DROP COLUMN IF EXISTS embedding CASCADE;
ALTER TABLE segments ADD COLUMN embedding VECTOR(1536);

-- 2. Normalize existing speaker labels to 'Chaffee' and 'GUEST' only
UPDATE segments SET speaker_label = 'Chaffee' WHERE speaker_label IN ('CH', 'CHAFFEE');
UPDATE segments SET speaker_label = 'GUEST' WHERE speaker_label IN ('G1', 'G2');

-- 3. Update speaker label constraint to only allow 'Chaffee' and 'GUEST'
ALTER TABLE segments DROP CONSTRAINT IF EXISTS segments_speaker_label_check;
ALTER TABLE segments ADD CONSTRAINT segments_speaker_label_check 
    CHECK (speaker_label IN ('Chaffee', 'GUEST'));

-- 4. Add source_id reference to link segments to sources table
-- First, add the column
ALTER TABLE segments ADD COLUMN IF NOT EXISTS source_id INTEGER;

-- Populate source_id from video_id (match with sources table)
UPDATE segments s
SET source_id = src.id
FROM sources src
WHERE s.video_id = src.source_id AND s.source_id IS NULL;

-- Add foreign key constraint
ALTER TABLE segments ADD CONSTRAINT segments_source_id_fkey 
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE;

-- Create index on source_id
CREATE INDEX IF NOT EXISTS segments_source_id_idx ON segments(source_id);

-- 5. Update pgvector index for 1536 dimensions (cosine similarity)
DROP INDEX IF EXISTS segments_embedding_idx;
CREATE INDEX IF NOT EXISTS segments_embedding_idx 
    ON segments USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 6. Update view to use normalized labels
CREATE OR REPLACE VIEW segments_with_metadata AS
SELECT 
    seg_id,
    video_id,
    source_id,
    start_sec,
    end_sec,
    (end_sec - start_sec) as duration_sec,
    speaker_label,
    speaker_conf,
    text,
    avg_logprob,
    compression_ratio,
    no_speech_prob,
    temperature_used,
    re_asr,
    is_overlap,
    needs_refinement,
    created_at,
    updated_at,
    -- Add helper columns
    CASE 
        WHEN speaker_label = 'Chaffee' THEN 'Dr. Chaffee'
        WHEN speaker_label = 'GUEST' THEN 'Guest'
        ELSE speaker_label
    END as speaker_display_name,
    CASE 
        WHEN avg_logprob < -0.55 AND speaker_label = 'Chaffee' THEN 'low_quality'
        WHEN avg_logprob < -0.8 AND speaker_label = 'GUEST' THEN 'low_quality'
        WHEN compression_ratio > 2.4 AND speaker_label = 'Chaffee' THEN 'low_quality'
        WHEN compression_ratio > 2.6 AND speaker_label = 'GUEST' THEN 'low_quality'
        ELSE 'good_quality'
    END as quality_assessment
FROM segments;

-- 7. Update comments
COMMENT ON COLUMN segments.embedding IS 'Text embedding vector for semantic search (1536-dim, Alibaba-NLP/gte-Qwen2-1.5B-instruct)';
COMMENT ON COLUMN segments.speaker_label IS 'Speaker label: Chaffee (Dr. Chaffee) or GUEST';
COMMENT ON COLUMN segments.source_id IS 'Foreign key to sources table';

-- 8. Mark chunks table as deprecated (keep for now, but add comment)
COMMENT ON TABLE chunks IS 'DEPRECATED: Use segments table instead. This table is kept for backward compatibility only.';
