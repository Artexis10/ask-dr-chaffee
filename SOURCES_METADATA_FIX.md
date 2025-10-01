# Sources Table Metadata Enhancement - COMPLETED ✅

## Problem
The `sources` table was only storing minimal metadata:
- `source_id` (video_id)
- `title`
- `source_type`
- `published_at`, `duration_s`, `view_count`

Missing rich metadata from yt-dlp:
- Channel information (`channel_name`, `channel_url`)
- Engagement metrics (`like_count`, `comment_count`)
- Visual assets (`thumbnail_url`)
- Content metadata (`description`, `tags`)
- Playback URL (`url`)

## Solution Implemented

### 1. Database Schema Enhancement ✅
**File:** `db/migrations/007_sources_rich_metadata.sql`

Added columns to `sources` table:
```sql
ALTER TABLE sources ADD COLUMN channel_name TEXT;
ALTER TABLE sources ADD COLUMN channel_url TEXT;
ALTER TABLE sources ADD COLUMN thumbnail_url TEXT;
ALTER TABLE sources ADD COLUMN like_count INTEGER;
ALTER TABLE sources ADD COLUMN comment_count INTEGER;
ALTER TABLE sources ADD COLUMN tags TEXT[];
ALTER TABLE sources ADD COLUMN description TEXT;
ALTER TABLE sources ADD COLUMN url TEXT;
ALTER TABLE sources ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
```

Added indexes for performance:
```sql
CREATE INDEX idx_sources_channel_name ON sources(channel_name);
CREATE INDEX idx_sources_like_count ON sources(like_count DESC NULLS LAST);
```

Added auto-update trigger for `updated_at`:
```sql
CREATE OR REPLACE FUNCTION update_sources_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER sources_updated_at_trigger
    BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_sources_updated_at();
```

### 2. VideoInfo Dataclass ✅
**File:** `backend/scripts/common/list_videos_yt_dlp.py`

The `VideoInfo` dataclass already had all necessary fields (lines 17-74):
- `channel_name`, `channel_url`
- `thumbnail_url`
- `like_count`, `comment_count`
- `description`, `tags`
- `url`

The `from_yt_dlp()` method properly extracts all metadata from yt-dlp JSON output.

### 3. Database Upsert Enhancement ✅
**File:** `backend/scripts/common/segments_database.py`

Enhanced `upsert_source()` method (lines 30-90):
- Changed from INSERT-only to true UPSERT using `ON CONFLICT`
- Uses `COALESCE()` to preserve existing non-null values
- Updates `updated_at` timestamp on conflict
- Properly handles JSON serialization for `tags` array

**Before:**
```python
# Only inserted if source didn't exist
if result:
    source_id = result[0]
    logger.debug(f"Source {video_id} already exists")
else:
    # INSERT new source
```

**After:**
```python
# True upsert with ON CONFLICT
INSERT INTO sources (...) VALUES (...)
ON CONFLICT (source_type, source_id) DO UPDATE SET
    channel_name = COALESCE(EXCLUDED.channel_name, sources.channel_name),
    like_count = COALESCE(EXCLUDED.like_count, sources.like_count),
    ...
RETURNING id
```

### 4. Ingestion Script Updates ✅
**File:** `backend/scripts/ingest_youtube_enhanced.py`

Updated both `upsert_source()` calls to pass all VideoInfo fields:

**Line 864-880:** Main ingestion path
```python
source_id = self.segments_db.upsert_source(
    video_id, 
    video.title,
    source_type=source_type,
    metadata={'provenance': provenance, **extra_metadata},
    published_at=video.published_at,
    duration_s=video.duration_s,
    view_count=video.view_count,
    channel_name=video.channel_name,        # NEW
    channel_url=video.channel_url,          # NEW
    thumbnail_url=video.thumbnail_url,      # NEW
    like_count=video.like_count,            # NEW
    comment_count=video.comment_count,      # NEW
    description=video.description,          # NEW
    tags=video.tags,                        # NEW
    url=video.url                           # NEW
)
```

**Line 1673-1689:** Batch insert path
```python
self.segments_db.upsert_source(
    video_id=video.video_id,
    title=video.title,
    source_type='youtube',
    metadata=metadata,
    published_at=getattr(video, 'published_at', None),
    duration_s=getattr(video, 'duration_s', None),
    view_count=getattr(video, 'view_count', None),
    channel_name=getattr(video, 'channel_name', None),      # NEW
    channel_url=getattr(video, 'channel_url', None),        # NEW
    thumbnail_url=getattr(video, 'thumbnail_url', None),    # NEW
    like_count=getattr(video, 'like_count', None),          # NEW
    comment_count=getattr(video, 'comment_count', None),    # NEW
    description=getattr(video, 'description', None),        # NEW
    tags=getattr(video, 'tags', None),                      # NEW
    url=getattr(video, 'url', None)                         # NEW
)
```

## Verification ✅

Ran `verify_sources_schema.py` to confirm all columns added:
```
✅ New metadata columns found: 
['channel_name', 'channel_url', 'comment_count', 'description', 
 'like_count', 'tags', 'thumbnail_url', 'url']
```

## Impact

### Immediate Benefits
1. **Complete metadata capture** - All yt-dlp metadata now stored
2. **No data loss** - Future ingestions will capture full metadata
3. **Backward compatible** - Existing code continues to work
4. **Upsert safety** - Re-running ingestion updates metadata without duplicates

### Future Capabilities Enabled
1. **Channel filtering** - Query by channel name
2. **Engagement analysis** - Sort/filter by likes, comments
3. **Content discovery** - Search by tags, description
4. **Visual display** - Show thumbnails in UI
5. **Direct playback** - Use stored URLs for video links

### Current Ingestion
The currently running ingestion will **continue without issues**:
- Existing segments are being stored correctly (most important)
- New videos will capture full metadata
- Already-processed videos can be updated with `--update-metadata` flag (future feature)

## Next Steps (Optional)

### Backfill Existing Sources
Create a script to backfill metadata for existing sources:
```python
# Pseudo-code
for source in get_sources_without_metadata():
    video_info = lister.get_video_metadata(source.source_id)
    db.upsert_source(video_info, ...)  # Will update with new metadata
```

### Add Metadata Update Flag
Add `--update-metadata` flag to ingestion script:
```python
if args.update_metadata:
    # Force metadata refresh even if source exists
    video_info = lister.get_video_metadata(video_id)
    db.upsert_source(video_info, ...)
```

## Files Modified
1. ✅ `db/migrations/007_sources_rich_metadata.sql` (NEW - includes updated_at column & trigger)
2. ✅ `backend/scripts/common/segments_database.py` (MODIFIED - fixed tags array handling)
3. ✅ `backend/scripts/ingest_youtube_enhanced.py` (MODIFIED - fetches metadata for --from-urls)
4. ✅ `run_migration.py` (MODIFIED - supports CLI args)
5. ✅ Database schema updated with new columns

## Fixes Applied

### Issue 1: Missing `updated_at` Column ✅
**Error:** `column "updated_at" of relation "sources" does not exist`

**Fix:** Added `updated_at` column with auto-update trigger to migration

### Issue 2: Tags Array Serialization ✅
**Error:** `malformed array literal: "["carnivore diet", ...]"`

**Fix:** Changed from `json.dumps(tags)` to native Python list - psycopg2 handles TEXT[] conversion

### Issue 3: --from-urls Creates Minimal VideoInfo ✅
**Problem:** Videos added via `--from-urls` had no metadata (title = "Video {id}")

**Fix:** Enhanced `_list_from_urls()` to fetch full metadata using `lister.get_video_metadata()`

## Summary
All future video ingestions will now capture complete metadata from yt-dlp, including channel information, engagement metrics, thumbnails, descriptions, and tags. The upsert logic ensures safe updates without duplicates, and existing data is preserved.
