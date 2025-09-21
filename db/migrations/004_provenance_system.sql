-- Add provenance system to sources table
-- Migration: 004_provenance_system.sql

-- Add provenance column to sources table
ALTER TABLE sources ADD COLUMN IF NOT EXISTS provenance TEXT DEFAULT 'yt_caption' 
    CHECK (provenance IN ('owner', 'yt_caption', 'yt_dlp', 'whisper'));

-- Add access_level column to sources table
ALTER TABLE sources ADD COLUMN IF NOT EXISTS access_level TEXT DEFAULT 'public'
    CHECK (access_level IN ('public', 'restricted', 'private'));

-- Update existing records to have default provenance
UPDATE sources SET provenance = 'yt_caption' WHERE provenance IS NULL;

-- Create index for provenance-based queries
CREATE INDEX IF NOT EXISTS idx_sources_provenance ON sources(provenance);
CREATE INDEX IF NOT EXISTS idx_sources_access_level ON sources(access_level);

-- Create composite index for search ordering (provenance + published_at)
CREATE INDEX IF NOT EXISTS idx_sources_provenance_published ON sources(provenance, published_at DESC);

-- Update ingest_state table to support new statuses
-- Add constraint to include new status values
ALTER TABLE ingest_state DROP CONSTRAINT IF EXISTS ingest_state_status_check;
ALTER TABLE ingest_state ADD CONSTRAINT ingest_state_status_check 
    CHECK (status IN ('pending', 'has_yt_transcript', 'transcribed', 'chunked', 'embedded', 'upserted', 'done', 'error', 'skipped', 'needs_whisper'));

-- Create index for needs_whisper status for efficient Whisper processing
CREATE INDEX IF NOT EXISTS idx_ingest_state_needs_whisper ON ingest_state(status) WHERE status = 'needs_whisper';

-- Add comment for documentation
COMMENT ON COLUMN sources.provenance IS 'Transcript source: owner (channel owner), yt_caption (YouTube captions), yt_dlp (yt-dlp subs), whisper (AI transcribed)';
COMMENT ON COLUMN sources.access_level IS 'Content access level: public, restricted (members-only), private';
