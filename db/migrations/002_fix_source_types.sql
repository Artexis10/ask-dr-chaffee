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

COMMIT;
