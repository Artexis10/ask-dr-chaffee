-- Add rich metadata columns to sources table
-- Migration 007: Enhanced sources metadata from yt-dlp

-- Add channel information
ALTER TABLE sources ADD COLUMN IF NOT EXISTS channel_name TEXT;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS channel_url TEXT;

-- Add thumbnail
ALTER TABLE sources ADD COLUMN IF NOT EXISTS thumbnail_url TEXT;

-- Add engagement metrics
ALTER TABLE sources ADD COLUMN IF NOT EXISTS like_count INTEGER;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS comment_count INTEGER;

-- Add tags (array of strings)
ALTER TABLE sources ADD COLUMN IF NOT EXISTS tags TEXT[];

-- Add updated_at timestamp
ALTER TABLE sources ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sources_channel_name ON sources(channel_name);
CREATE INDEX IF NOT EXISTS idx_sources_like_count ON sources(like_count DESC NULLS LAST);

-- Create trigger for auto-updating updated_at
CREATE OR REPLACE FUNCTION update_sources_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS sources_updated_at_trigger ON sources;
CREATE TRIGGER sources_updated_at_trigger
    BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_sources_updated_at();

-- Add comments for documentation
COMMENT ON COLUMN sources.channel_name IS 'YouTube channel name (e.g., "Anthony Chaffee MD")';
COMMENT ON COLUMN sources.channel_url IS 'YouTube channel URL';
COMMENT ON COLUMN sources.thumbnail_url IS 'Video thumbnail URL (maxresdefault preferred)';
COMMENT ON COLUMN sources.like_count IS 'Number of likes on the video';
COMMENT ON COLUMN sources.comment_count IS 'Number of comments on the video';
COMMENT ON COLUMN sources.tags IS 'Array of video tags from YouTube';
COMMENT ON COLUMN sources.updated_at IS 'Timestamp of last update (auto-updated on row changes)';
