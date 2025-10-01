-- Fix embedding dimensions from 384 to 1536
-- This is needed because we switched to GTE-Qwen2-1.5B-instruct (1536-dim)

-- Drop the old index
DROP INDEX IF EXISTS segments_embedding_idx;

-- Alter the column type
ALTER TABLE segments ALTER COLUMN embedding TYPE vector(1536);

-- Recreate the index with correct dimensions
CREATE INDEX segments_embedding_idx 
ON segments USING ivfflat (embedding vector_l2_ops) 
WITH (lists = 100);

-- Verify
SELECT 
    column_name,
    data_type,
    udt_name
FROM information_schema.columns 
WHERE table_name = 'segments' AND column_name = 'embedding';
