-- Migration: Add API cache table for YouTube Data API ETags and watermarks
-- Created: 2025-01-06

-- Create api_cache table for storing ETags and watermarks
CREATE TABLE IF NOT EXISTS api_cache (
    key TEXT PRIMARY KEY,
    etag TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add index for efficient lookups by key
CREATE INDEX IF NOT EXISTS idx_api_cache_updated_at ON api_cache(updated_at);

-- Update ingest_state table to include additional metadata
ALTER TABLE ingest_state 
ADD COLUMN IF NOT EXISTS title TEXT,
ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS duration_s INTEGER,
ADD COLUMN IF NOT EXISTS has_yt_transcript BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS has_whisper BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS retries INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Add indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_ingest_state_published_at ON ingest_state(published_at);
CREATE INDEX IF NOT EXISTS idx_ingest_state_status ON ingest_state(status);
CREATE INDEX IF NOT EXISTS idx_ingest_state_duration ON ingest_state(duration_s);

-- Add comments for documentation
COMMENT ON TABLE api_cache IS 'Cache for YouTube Data API ETags and watermarks to minimize quota usage';
COMMENT ON COLUMN api_cache.key IS 'Cache key (e.g., uploads_<channelId>, channel_<channelId>)';
COMMENT ON COLUMN api_cache.etag IS 'ETag from YouTube API response for conditional requests';
COMMENT ON COLUMN api_cache.updated_at IS 'When this cache entry was last updated';

COMMENT ON COLUMN ingest_state.title IS 'Video title from YouTube API';
COMMENT ON COLUMN ingest_state.published_at IS 'Video publication timestamp';
COMMENT ON COLUMN ingest_state.duration_s IS 'Video duration in seconds';
COMMENT ON COLUMN ingest_state.has_yt_transcript IS 'Whether YouTube transcript was available';
COMMENT ON COLUMN ingest_state.has_whisper IS 'Whether Whisper transcription was used';
COMMENT ON COLUMN ingest_state.retries IS 'Number of processing attempts';
COMMENT ON COLUMN ingest_state.last_error IS 'Last error message if processing failed';
