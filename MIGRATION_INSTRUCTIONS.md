# Database Migration Instructions

## Critical Issues Found

### 1. **Segments Table Schema Mismatch**
- ❌ Embedding dimension: 1536 (wrong) → Should be 384 (all-MiniLM-L6-v2)
- ❌ Speaker labels: 'CH', 'G1', 'G2' → Should be 'Chaffee' and 'GUEST' only
- ❌ Missing source_id foreign key to link segments to sources table

### 2. **Sources Table Not Being Populated**
- Segments were being inserted without creating source entries first
- Fixed in code: `_batch_insert_video_segments` now calls `upsert_source` first

### 3. **Chunks Table is Deprecated**
- Old schema uses `chunks` table
- New schema uses `segments` table
- Migration marks `chunks` as deprecated

---

## How to Apply Migration

### Step 1: Backup Your Database
```bash
# Get DATABASE_URL from .env
$env:DATABASE_URL = (Get-Content .env | Select-String "^DATABASE_URL=" | ForEach-Object { $_ -replace "^DATABASE_URL=", "" })

# Create backup
pg_dump $env:DATABASE_URL > backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql
```

### Step 2: Run Migration
```bash
# Apply migration 006
psql $env:DATABASE_URL -f db\migrations\006_fix_segments_schema.sql
```

### Step 3: Verify Migration
```sql
-- Check embedding dimension
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'segments' AND column_name = 'embedding';
-- Should show: vector(384)

-- Check speaker labels
SELECT DISTINCT speaker_label FROM segments;
-- Should only show: Chaffee, GUEST

-- Check source_id exists
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'segments' AND column_name = 'source_id';
-- Should show: integer

-- Verify sources are populated
SELECT COUNT(*) FROM sources;
-- Should show count of videos

-- Verify segments link to sources
SELECT COUNT(*) FROM segments WHERE source_id IS NOT NULL;
-- Should match total segment count
```

---

## What the Migration Does

### 1. Fix Embedding Dimension
```sql
ALTER TABLE segments DROP COLUMN IF EXISTS embedding CASCADE;
ALTER TABLE segments ADD COLUMN embedding VECTOR(384);
```

### 2. Normalize Speaker Labels
```sql
-- Convert old labels to new standard
UPDATE segments SET speaker_label = 'Chaffee' WHERE speaker_label IN ('CH', 'CHAFFEE');
UPDATE segments SET speaker_label = 'GUEST' WHERE speaker_label IN ('G1', 'G2');

-- Enforce only 'Chaffee' and 'GUEST'
ALTER TABLE segments ADD CONSTRAINT segments_speaker_label_check 
    CHECK (speaker_label IN ('Chaffee', 'GUEST'));
```

### 3. Add Source Reference
```sql
-- Add source_id column
ALTER TABLE segments ADD COLUMN IF NOT EXISTS source_id INTEGER;

-- Link existing segments to sources
UPDATE segments s
SET source_id = src.id
FROM sources src
WHERE s.video_id = src.source_id AND s.source_id IS NULL;

-- Add foreign key
ALTER TABLE segments ADD CONSTRAINT segments_source_id_fkey 
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE;
```

### 4. Update Indexes
```sql
-- Recreate pgvector index for 384 dimensions
DROP INDEX IF EXISTS segments_embedding_idx;
CREATE INDEX segments_embedding_idx 
    ON segments USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Add source_id index
CREATE INDEX segments_source_id_idx ON segments(source_id);
```

### 5. Mark Chunks as Deprecated
```sql
COMMENT ON TABLE chunks IS 'DEPRECATED: Use segments table instead.';
```

---

## After Migration

### Re-run Failed Ingestion
The ingestion that failed should now work correctly:

```bash
python backend\scripts\ingest_youtube_enhanced.py --source yt-dlp --limit 15 --voices-dir .\voices
```

### Verify Data Integrity
```sql
-- Check that all segments have sources
SELECT 
    COUNT(*) as total_segments,
    COUNT(source_id) as segments_with_source,
    COUNT(*) - COUNT(source_id) as orphaned_segments
FROM segments;
-- orphaned_segments should be 0

-- Check sources table is populated
SELECT 
    s.source_id as video_id,
    s.title,
    COUNT(seg.seg_id) as segment_count
FROM sources s
LEFT JOIN segments seg ON s.id = seg.source_id
GROUP BY s.id, s.source_id, s.title
ORDER BY s.created_at DESC
LIMIT 10;
```

---

## Code Changes Made

### 1. Fixed `_batch_insert_video_segments` in `ingest_youtube_enhanced.py`
**Before:**
```python
def _batch_insert_video_segments(self, video, segments, method, metadata, stats_lock):
    # Directly inserted segments without creating source
    segment_count = self.segments_db.batch_insert_segments(...)
```

**After:**
```python
def _batch_insert_video_segments(self, video, segments, method, metadata, stats_lock):
    # First create/update source
    self.segments_db.upsert_source(
        video_id=video.video_id,
        title=video.title,
        source_type='youtube',
        metadata=metadata,
        published_at=getattr(video, 'published_at', None),
        duration_s=getattr(video, 'duration', None),
        view_count=getattr(video, 'view_count', None)
    )
    
    # Then insert segments
    segment_count = self.segments_db.batch_insert_segments(...)
```

### 2. Fixed `batch_insert_segments` in `segments_database.py`
- Added `get_attr()` helper to handle both dict and TranscriptSegment objects
- Now properly extracts attributes from dataclass instances

---

## Summary

**Issues Fixed:**
1. ✅ Embedding dimension corrected (1536 → 384)
2. ✅ Speaker labels normalized ('Chaffee' and 'GUEST' only)
3. ✅ Source entries now created before segments
4. ✅ source_id foreign key added to segments table
5. ✅ Chunks table marked as deprecated

**Next Steps:**
1. Run migration: `psql $env:DATABASE_URL -f db\migrations\006_fix_segments_schema.sql`
2. Re-run ingestion to populate data correctly
3. Verify data integrity with SQL queries above
