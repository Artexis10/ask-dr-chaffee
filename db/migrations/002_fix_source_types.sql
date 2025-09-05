-- Fix source_type values in sources table
-- Change any 'yt-dlp' or 'api' source_type values to 'youtube'

BEGIN;

-- Update source_type for YouTube sources
UPDATE sources
SET source_type = 'youtube'
WHERE source_type IN ('yt-dlp', 'api');

-- Log the number of updated rows
DO $$
DECLARE
  updated_count INTEGER;
BEGIN
  GET DIAGNOSTICS updated_count = ROW_COUNT;
  RAISE NOTICE 'Updated % rows in sources table', updated_count;
END $$;

-- Update ingest_state table to match exact requirements
-- Migration: 002_fix_ingest_state_schema.sql

-- First, update the status constraint to match the exact required statuses
ALTER TABLE ingest_state DROP CONSTRAINT IF EXISTS valid_status;
ALTER TABLE ingest_state ADD CONSTRAINT valid_status CHECK (status IN (
    'pending', 'transcript', 'whisper', 'chunked', 'embedded', 'upserted', 'done', 'error'
));

-- Update existing status values to match new schema
UPDATE ingest_state SET status = 'transcript' WHERE status = 'has_yt_transcript';
UPDATE ingest_state SET status = 'whisper' WHERE status = 'transcribed';
UPDATE ingest_state SET status = 'done' WHERE status IN ('upserted');

-- Add missing columns if they don't exist
DO $$ 
BEGIN
    -- Add has_yt_transcript column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'ingest_state' AND column_name = 'has_yt_transcript') THEN
        ALTER TABLE ingest_state ADD COLUMN has_yt_transcript BOOLEAN DEFAULT FALSE;
    END IF;
    
    -- Add has_whisper column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'ingest_state' AND column_name = 'has_whisper') THEN
        ALTER TABLE ingest_state ADD COLUMN has_whisper BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Ensure index on status exists for efficient queue scanning
CREATE INDEX IF NOT EXISTS idx_ingest_state_status ON ingest_state(status);
CREATE INDEX IF NOT EXISTS idx_ingest_state_status_retries ON ingest_state(status, retries);

-- Fix source types mapping for better filtering
UPDATE sources 
SET source_type = 'youtube' 
WHERE source_type != 'youtube' AND (source_id LIKE '%youtube%' OR url LIKE '%youtube.com%');

UPDATE sources 
SET source_type = 'zoom'
WHERE source_type != 'zoom' AND (source_id LIKE '%zoom%' OR url LIKE '%zoom%');

-- Ensure all existing sources have proper source_type
UPDATE sources 
SET source_type = 'youtube'
WHERE source_type IS NULL OR source_type = '';

-- Add constraint to ensure source_type is valid
ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_source_type_check;
ALTER TABLE sources ADD CONSTRAINT sources_source_type_check 
    CHECK (source_type IN ('youtube', 'zoom'));

COMMIT;
