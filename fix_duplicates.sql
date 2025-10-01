-- Fix duplicate segments and NULL speaker labels

-- 1. Create a temporary table with row numbers
CREATE TEMP TABLE segment_ranks AS
SELECT 
    id,
    video_id,
    text,
    ROW_NUMBER() OVER (PARTITION BY video_id, text ORDER BY id) as row_num
FROM segments;

-- 2. Delete duplicates (keeping the first occurrence)
DELETE FROM segments
WHERE id IN (
    SELECT id FROM segment_ranks WHERE row_num > 1
);

-- 3. Fix NULL speaker labels
UPDATE segments
SET speaker_label = 'Chaffee'
WHERE speaker_label IS NULL;

-- 4. Verify fix
SELECT 
    COUNT(*) as total_segments,
    COUNT(CASE WHEN speaker_label IS NULL THEN 1 END) as null_labels,
    COUNT(DISTINCT (video_id, text)) as unique_segments
FROM segments;
