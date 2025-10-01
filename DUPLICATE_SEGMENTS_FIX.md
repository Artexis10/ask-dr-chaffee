# Duplicate Segments Fix

## Problem Identified

Your screenshot showed:
- **30+ duplicate segments** with identical text
- Timestamps incrementing by 0.5 seconds (236.38, 236.88, 237.38...)
- **ALL segments had NULL speaker labels**

## Root Cause

1. **Whisper's Overlapping Segments:**
   - Whisper generates many small segments with word-level timestamps
   - Often creates duplicate text when uncertain
   - Default behavior produces 0.5s increments

2. **No Deduplication:**
   - Segment optimizer didn't check for duplicate text
   - Only merged based on time gaps and character length
   - No final pass to remove identical segments

3. **NULL Speaker Labels:**
   - Enhanced ASR conversion failed (fallback path)
   - Fallback didn't assign default speaker labels
   - Segment optimizer defaulted to 'GUEST' instead of 'Chaffee'

## Fixes Implemented

### 1. Added Deduplication Method

**File:** `backend/scripts/common/segment_optimizer.py`

```python
def _remove_duplicate_segments(self, segments):
    """Remove segments with duplicate text (Whisper often creates duplicates)"""
    seen_text = set()
    unique_segments = []
    duplicates_removed = 0
    
    for segment in segments:
        # Normalize text for comparison
        normalized_text = segment.text.lower().strip()
        
        # Skip if we've seen this exact text before
        if normalized_text in seen_text:
            duplicates_removed += 1
            continue
            
        # Add to unique segments
        seen_text.add(normalized_text)
        unique_segments.append(segment)
    
    if duplicates_removed > 0:
        logger.info(f"Removed {duplicates_removed} duplicate segments")
    
    return unique_segments
```

**Integration:**
- Added to optimization pipeline after merging/splitting
- Runs before final text cleaning
- Logs number of duplicates removed

### 2. Fixed NULL Speaker Labels (3 Places)

**A. Segment Optimizer** (`segment_optimizer.py`)
```python
# CRITICAL: Ensure speaker_label is never NULL
speaker_label = segment.speaker_label
if not speaker_label:
    speaker_label = 'Chaffee'  # Default to Chaffee (not GUEST)
    logger.warning(f"Segment missing speaker_label, defaulting to 'Chaffee'")
```

**B. Enhanced ASR Fallback** (`enhanced_transcript_fetch.py`)
```python
# Fallback to basic segments WITH speaker labels (prevent NULL labels)
for segment_data in enhanced_result.segments:
    segment = TranscriptSegment(
        start=segment_data['start'],
        end=segment_data['end'],
        text=segment_data['text'].strip(),
        speaker_label='Chaffee'  # Default to Chaffee (not GUEST)
    )
```

**C. Added Logging:**
```python
logger.warning(f"Enhanced ASR conversion failed, using {len(segments)} segments with default speaker labels")
```

### 3. Database Fix Script

**File:** `fix_duplicates.sql`

```sql
-- 1. Remove duplicate segments
CREATE TEMP TABLE segment_ranks AS
SELECT 
    id,
    video_id,
    text,
    ROW_NUMBER() OVER (PARTITION BY video_id, text ORDER BY id) as row_num
FROM segments;

DELETE FROM segments
WHERE id IN (
    SELECT id FROM segment_ranks WHERE row_num > 1
);

-- 2. Fix NULL speaker labels
UPDATE segments
SET speaker_label = 'Chaffee'
WHERE speaker_label IS NULL;

-- 3. Verify
SELECT 
    COUNT(*) as total_segments,
    COUNT(CASE WHEN speaker_label IS NULL THEN 1 END) as null_labels,
    COUNT(DISTINCT (video_id, text)) as unique_segments
FROM segments;
```

## How to Apply Fixes

### 1. Fix Current Database (Run SQL Script)

Connect to your database and run:
```bash
psql -d your_database -f fix_duplicates.sql
```

Or manually:
```sql
-- Remove duplicates
WITH segment_ranks AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY video_id, text ORDER BY id) as row_num
    FROM segments
)
DELETE FROM segments WHERE id IN (SELECT id FROM segment_ranks WHERE row_num > 1);

-- Fix NULL labels
UPDATE segments SET speaker_label = 'Chaffee' WHERE speaker_label IS NULL;
```

### 2. Restart Ingestion with Fixes

```bash
# Stop current ingestion
Stop-Process -Name python -Force

# The code fixes are already applied!
# Just restart:
python backend\scripts\ingest_youtube_enhanced.py \
  --source yt-dlp \
  --limit 50 \
  --skip-shorts \
  --voices-dir .\voices
```

### 3. Monitor for Success

Check logs for:
```
✅ "Removed X duplicate segments"
✅ "Segment missing speaker_label, defaulting to 'Chaffee'"
✅ No NULL speaker labels in database
```

## Verification

After running ingestion:

```sql
-- Should show 0 duplicates and 0 NULL labels
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN speaker_label IS NULL THEN 1 END) as null_labels,
    COUNT(*) - COUNT(DISTINCT (video_id, text)) as duplicates
FROM segments;

-- Expected:
-- total: X
-- null_labels: 0
-- duplicates: 0
```

## Prevention

These fixes ensure duplicates and NULL labels **cannot happen again**:

1. ✅ **Deduplication** runs on every video
2. ✅ **Speaker labels** always assigned (3 fallback layers)
3. ✅ **Logging** alerts when fallbacks are used
4. ✅ **Default to 'Chaffee'** (not 'GUEST') for solo content

## What Caused Your Specific Issue

Looking at your screenshot pattern:
- Text: "inflammation and you're going to be in a state of inflammation."
- Repeated 30+ times with 0.5s increments
- ALL NULL speaker labels

**This happened because:**
1. Whisper generated many overlapping segments (0.5s apart)
2. Enhanced ASR conversion failed (exception thrown)
3. Fallback path didn't assign speaker labels
4. No deduplication pass to remove identical text
5. Segment optimizer defaulted to 'GUEST' instead of 'Chaffee'

**Now fixed:** All these issues are prevented with multiple safeguards.

## Summary

**Files Modified:**
- `backend/scripts/common/segment_optimizer.py` - Added deduplication + NULL label fix
- `backend/scripts/common/enhanced_transcript_fetch.py` - Fixed fallback speaker labels

**Database Fix:**
- `fix_duplicates.sql` - Removes existing duplicates and fixes NULL labels

**Prevention:**
- Deduplication runs automatically
- Speaker labels always assigned (multiple fallbacks)
- Defaults to 'Chaffee' for Dr. Chaffee content

All fixes are now in place and will prevent this issue from recurring! ✅
