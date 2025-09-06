-- Migration: Add summaries table for caching answer responses
-- Created: 2025-01-07

-- Create summaries table for caching LLM-generated answers
CREATE TABLE IF NOT EXISTS summaries (
    id SERIAL PRIMARY KEY,
    cache_key TEXT NOT NULL UNIQUE,
    type VARCHAR(20) NOT NULL DEFAULT 'answer' CHECK (type IN ('answer', 'summary')),
    query_text TEXT NOT NULL,
    chunk_ids TEXT[] NOT NULL, -- Array of chunk identifiers used
    model_version TEXT NOT NULL,
    answer_md TEXT NOT NULL, -- Final prose with citation chips
    citations JSONB NOT NULL, -- Array of citation objects
    confidence DECIMAL(3,2) CHECK (confidence >= 0.0 AND confidence <= 1.0),
    notes TEXT, -- Optional conflicts/limits info
    used_chunk_ids TEXT[] NOT NULL, -- video_id:t_start_s format
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_summaries_cache_key ON summaries(cache_key);
CREATE INDEX IF NOT EXISTS idx_summaries_type ON summaries(type);
CREATE INDEX IF NOT EXISTS idx_summaries_expires_at ON summaries(expires_at);
CREATE INDEX IF NOT EXISTS idx_summaries_created_at ON summaries(created_at DESC);

-- Add trigger for updated_at
CREATE OR REPLACE TRIGGER update_summaries_updated_at
    BEFORE UPDATE ON summaries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE summaries IS 'Cache for LLM-generated answers and summaries with TTL';
COMMENT ON COLUMN summaries.cache_key IS 'Hash-based cache key (query_norm + chunk_ids + model_version)';
COMMENT ON COLUMN summaries.type IS 'Type of summary: answer or summary';
COMMENT ON COLUMN summaries.query_text IS 'Original user query text';
COMMENT ON COLUMN summaries.chunk_ids IS 'Array of chunk IDs used in the response';
COMMENT ON COLUMN summaries.model_version IS 'LLM model version used for generation';
COMMENT ON COLUMN summaries.answer_md IS 'Final answer with inline citation chips';
COMMENT ON COLUMN summaries.citations IS 'JSON array of citation objects with video_id, t_start_s, published_at';
COMMENT ON COLUMN summaries.confidence IS 'Confidence score 0.0-1.0 based on chunk quality and agreement';
COMMENT ON COLUMN summaries.notes IS 'Optional notes about conflicts, missing info, or scope limits';
COMMENT ON COLUMN summaries.used_chunk_ids IS 'Array of chunk identifiers in video_id:timestamp format';
COMMENT ON COLUMN summaries.expires_at IS 'Cache expiration timestamp (TTL)';

-- Create cleanup function to remove expired entries
CREATE OR REPLACE FUNCTION cleanup_expired_summaries()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM summaries WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Add cleanup scheduling comment (actual scheduling would be done via cron or pg_cron)
COMMENT ON FUNCTION cleanup_expired_summaries() IS 'Function to clean up expired summary cache entries. Schedule via cron: SELECT cleanup_expired_summaries();';
