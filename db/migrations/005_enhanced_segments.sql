-- Enhanced segments table for Chaffee-aware speaker attribution
-- Migration 005: Enhanced segments with speaker labels and pgvector

-- Create enhanced segments table
CREATE TABLE IF NOT EXISTS segments (
    seg_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id TEXT NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    speaker_label TEXT CHECK (speaker_label IN ('CH','GUEST','G1','G2')) NOT NULL,
    speaker_conf REAL,
    text TEXT NOT NULL,
    avg_logprob REAL,
    compression_ratio REAL,
    no_speech_prob REAL,
    temperature_used REAL DEFAULT 0.0,
    re_asr BOOLEAN DEFAULT FALSE,
    is_overlap BOOLEAN DEFAULT FALSE,
    needs_refinement BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Add embedding column for pgvector (1536 dimensions for text-embedding-3-large)
ALTER TABLE segments ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS segments_video_idx ON segments(video_id);
CREATE INDEX IF NOT EXISTS segments_speaker_video_idx ON segments(speaker_label, video_id);
CREATE INDEX IF NOT EXISTS segments_time_idx ON segments(video_id, start_sec);
CREATE INDEX IF NOT EXISTS segments_re_asr_idx ON segments(re_asr) WHERE re_asr = true;
CREATE INDEX IF NOT EXISTS segments_speaker_conf_idx ON segments(speaker_label, speaker_conf) WHERE speaker_label = 'CH';

-- pgvector index (create after thousands of rows for better performance)
-- CREATE INDEX IF NOT EXISTS segments_embedding_idx
--   ON segments USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- Add trigger for updated_at
CREATE OR REPLACE FUNCTION update_segments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER segments_updated_at
    BEFORE UPDATE ON segments
    FOR EACH ROW EXECUTE FUNCTION update_segments_updated_at();

-- Create view for easy querying
CREATE OR REPLACE VIEW segments_with_metadata AS
SELECT 
    seg_id,
    video_id,
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
        WHEN speaker_label = 'CH' THEN 'Dr. Chaffee'
        WHEN speaker_label = 'GUEST' THEN 'Guest'
        ELSE speaker_label
    END as speaker_display_name,
    CASE 
        WHEN avg_logprob < -0.55 AND speaker_label = 'CH' THEN 'low_quality'
        WHEN avg_logprob < -0.8 AND speaker_label = 'GUEST' THEN 'low_quality'
        WHEN compression_ratio > 2.4 AND speaker_label = 'CH' THEN 'low_quality'
        WHEN compression_ratio > 2.6 AND speaker_label = 'GUEST' THEN 'low_quality'
        ELSE 'good_quality'
    END as quality_assessment
FROM segments;

-- Add comments for documentation
COMMENT ON TABLE segments IS 'Enhanced segments table with Chaffee-aware speaker attribution and quality metrics';
COMMENT ON COLUMN segments.speaker_label IS 'Speaker label: CH (Chaffee), GUEST, G1, G2';
COMMENT ON COLUMN segments.speaker_conf IS 'Cosine similarity confidence score vs Chaffee profile';
COMMENT ON COLUMN segments.avg_logprob IS 'Average log probability from Whisper (quality metric)';
COMMENT ON COLUMN segments.compression_ratio IS 'Compression ratio from Whisper (quality metric)';
COMMENT ON COLUMN segments.no_speech_prob IS 'No speech probability from Whisper';
COMMENT ON COLUMN segments.temperature_used IS 'Temperature used in Whisper transcription';
COMMENT ON COLUMN segments.re_asr IS 'Whether segment was re-transcribed with large-v3';
COMMENT ON COLUMN segments.is_overlap IS 'Whether segment has speaker overlap';
COMMENT ON COLUMN segments.needs_refinement IS 'Whether segment was flagged for potential refinement';
COMMENT ON COLUMN segments.embedding IS 'Text embedding vector for semantic search (1536-dim)';
