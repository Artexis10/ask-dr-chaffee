-- Database schema updates for hybrid processing support
-- Add processing method tracking and cost monitoring

-- Add processing method column to track how each video was processed
ALTER TABLE ingest_state 
ADD COLUMN IF NOT EXISTS processing_method VARCHAR(20);

-- Add cost tracking for API processing
ALTER TABLE ingest_state 
ADD COLUMN IF NOT EXISTS processing_cost_usd DECIMAL(8,4) DEFAULT 0.0;

-- Add processing metadata for quality analysis
ALTER TABLE ingest_state 
ADD COLUMN IF NOT EXISTS processing_metadata JSONB;

-- Create index for processing method queries
CREATE INDEX IF NOT EXISTS idx_ingest_state_processing_method 
ON ingest_state(processing_method);

-- Create index for cost tracking
CREATE INDEX IF NOT EXISTS idx_ingest_state_cost 
ON ingest_state(processing_cost_usd) WHERE processing_cost_usd > 0;

-- Add constraint for valid processing methods
ALTER TABLE ingest_state 
ADD CONSTRAINT chk_processing_method 
CHECK (processing_method IN ('local_gpu', 'api_whisper', 'youtube_transcript', NULL));

-- Create view for processing cost analysis
CREATE OR REPLACE VIEW processing_cost_summary AS
SELECT 
    processing_method,
    COUNT(*) as video_count,
    SUM(processing_cost_usd) as total_cost_usd,
    AVG(processing_cost_usd) as avg_cost_per_video,
    DATE_TRUNC('day', updated_at) as processing_date
FROM ingest_state 
WHERE processing_cost_usd > 0
GROUP BY processing_method, DATE_TRUNC('day', updated_at)
ORDER BY processing_date DESC;

-- Create view for processing quality comparison
CREATE OR REPLACE VIEW processing_quality_analysis AS
SELECT 
    processing_method,
    COUNT(*) as total_videos,
    COUNT(CASE WHEN status = 'done' THEN 1 END) as successful_videos,
    COUNT(CASE WHEN status = 'error' THEN 1 END) as failed_videos,
    ROUND(
        COUNT(CASE WHEN status = 'done' THEN 1 END)::DECIMAL / COUNT(*) * 100, 
        2
    ) as success_rate_percent,
    AVG(
        CASE 
            WHEN processing_metadata->>'segments_count' IS NOT NULL 
            THEN (processing_metadata->>'segments_count')::INTEGER 
        END
    ) as avg_segments_per_video
FROM ingest_state 
WHERE processing_method IS NOT NULL
GROUP BY processing_method;

-- Create monitoring table for daily processing runs
CREATE TABLE IF NOT EXISTS daily_processing_runs (
    id SERIAL PRIMARY KEY,
    run_date DATE NOT NULL,
    processing_mode VARCHAR(20) NOT NULL,
    videos_processed INTEGER DEFAULT 0,
    videos_skipped INTEGER DEFAULT 0,
    videos_failed INTEGER DEFAULT 0,
    total_cost_usd DECIMAL(8,4) DEFAULT 0.0,
    processing_time_seconds INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index for daily runs
CREATE INDEX IF NOT EXISTS idx_daily_runs_date 
ON daily_processing_runs(run_date DESC);

-- Sample queries for monitoring:

-- Daily cost tracking:
-- SELECT run_date, processing_mode, videos_processed, total_cost_usd 
-- FROM daily_processing_runs 
-- ORDER BY run_date DESC LIMIT 30;

-- Monthly cost summary:
-- SELECT 
--     DATE_TRUNC('month', run_date) as month,
--     SUM(total_cost_usd) as monthly_cost,
--     SUM(videos_processed) as monthly_videos
-- FROM daily_processing_runs 
-- GROUP BY DATE_TRUNC('month', run_date)
-- ORDER BY month DESC;

-- Processing method effectiveness:
-- SELECT * FROM processing_quality_analysis;
