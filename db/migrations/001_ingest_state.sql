-- Enhanced ingest state tracking for YouTube video processing
-- Migration: 001_ingest_state.sql

CREATE TABLE IF NOT EXISTS ingest_state (
    video_id TEXT PRIMARY KEY,
    title TEXT,
    published_at TIMESTAMPTZ,
    duration_s INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    has_yt_transcript BOOLEAN DEFAULT FALSE,
    has_whisper BOOLEAN DEFAULT FALSE,
    retries INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    
    -- Additional metadata
    view_count BIGINT,
    like_count INTEGER,
    description TEXT,
    tags TEXT[],
    category_id TEXT,
    
    -- Processing metadata
    audio_duration_s INTEGER,
    transcript_language TEXT DEFAULT 'en',
    whisper_model TEXT,
    chunk_count INTEGER DEFAULT 0,
    embedding_count INTEGER DEFAULT 0,
    
    CONSTRAINT valid_status CHECK (status IN (
        'pending', 'has_yt_transcript', 'transcribed', 'chunked', 
        'embedded', 'upserted', 'done', 'error', 'skipped'
    ))
);

-- Index for efficient querying
CREATE INDEX IF NOT EXISTS idx_ingest_state_status ON ingest_state(status);
CREATE INDEX IF NOT EXISTS idx_ingest_state_published_at ON ingest_state(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingest_state_updated_at ON ingest_state(updated_at DESC);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_ingest_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_ingest_state_updated_at ON ingest_state;
CREATE TRIGGER trigger_update_ingest_state_updated_at
    BEFORE UPDATE ON ingest_state
    FOR EACH ROW
    EXECUTE FUNCTION update_ingest_state_updated_at();

-- Add columns to existing sources table if they don't exist
DO $$ 
BEGIN
    -- Add duration column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'sources' AND column_name = 'duration_s') THEN
        ALTER TABLE sources ADD COLUMN duration_s INTEGER;
    END IF;
    
    -- Add view_count column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'sources' AND column_name = 'view_count') THEN
        ALTER TABLE sources ADD COLUMN view_count BIGINT;
    END IF;
    
    -- Add published_at index if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM pg_indexes 
                   WHERE tablename = 'sources' AND indexname = 'idx_sources_published_at') THEN
        CREATE INDEX idx_sources_published_at ON sources(published_at DESC);
    END IF;
END $$;
