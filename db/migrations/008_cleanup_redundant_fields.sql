-- Remove redundant denormalized fields from sources table
-- Migration 008: Cleanup redundant status/count fields

-- These fields are redundant and can be calculated from segments table:
-- - chunk_count: COUNT(*) FROM segments WHERE video_id = ?
-- - embedding_count: COUNT(*) FROM segments WHERE video_id = ? AND embedding IS NOT NULL
-- - progress: calculated from segments processed
-- - status: derived from segment existence

-- Drop redundant columns
ALTER TABLE sources DROP COLUMN IF EXISTS status;
ALTER TABLE sources DROP COLUMN IF EXISTS progress;
ALTER TABLE sources DROP COLUMN IF EXISTS chunk_count;
ALTER TABLE sources DROP COLUMN IF EXISTS embedding_count;
ALTER TABLE sources DROP COLUMN IF EXISTS has_yt_transcript;
ALTER TABLE sources DROP COLUMN IF EXISTS has_whisper;
ALTER TABLE sources DROP COLUMN IF EXISTS error;
ALTER TABLE sources DROP COLUMN IF EXISTS retries;
ALTER TABLE sources DROP COLUMN IF EXISTS last_error;
ALTER TABLE sources DROP COLUMN IF EXISTS last_updated;

-- Drop related indexes
DROP INDEX IF EXISTS idx_sources_status;
DROP INDEX IF EXISTS idx_sources_updated;

-- Add comment explaining the cleanup
COMMENT ON TABLE sources IS 'Video/recording sources with immutable metadata. Processing status and counts should be queried from segments table.';

-- Example queries for common operations:
-- Get segment count: SELECT COUNT(*) FROM segments WHERE video_id = 'VIDEO_ID';
-- Get embedding count: SELECT COUNT(*) FROM segments WHERE video_id = 'VIDEO_ID' AND embedding IS NOT NULL;
-- Check if processed: SELECT EXISTS(SELECT 1 FROM segments WHERE video_id = 'VIDEO_ID');
-- Get processing progress: SELECT COUNT(*) FILTER (WHERE embedding IS NOT NULL) * 100.0 / COUNT(*) FROM segments WHERE video_id = 'VIDEO_ID';
