# Segment Optimization Plan

## Problems Identified

### 1. Segments Too Short for RAG
**Current:** ~5-10 second segments (100 segments in ~40 seconds of processing)
**Issue:** Short segments lack context for effective RAG summarization
**Target:** 30-60 second segments with 400-1200 characters

### 2. Segment Optimizer Not Being Used
**Status:** `SegmentOptimizer` class exists but is never called
**Location:** `backend/scripts/common/segment_optimizer.py`
**Issue:** Segments go directly from Whisper → Database without optimization

### 3. Processing Speed Issue
**Observation:** Taking ~40 seconds to process 100 segments
**Likely Cause:** Speaker identification on every short segment (expensive)
**Solution:** Optimize segments BEFORE speaker ID to reduce processing

## Solutions Implemented

### 1. Environment Variables Added (`.env`)
```bash
# Segment Optimization for RAG (longer segments = better context)
ENABLE_SEGMENT_OPTIMIZATION=true
SEGMENT_MIN_CHARS=400          # Minimum 400 chars (~30 seconds)
SEGMENT_MAX_CHARS=1200         # Maximum 1200 chars (~90 seconds)
SEGMENT_MAX_GAP_SECONDS=3.0    # Merge segments within 3 seconds
SEGMENT_MAX_MERGE_DURATION=60.0 # Max 60 second merged segments
```

### 2. SegmentOptimizer Updated
- Now reads from environment variables
- Default values optimized for RAG (400-1200 chars)
- Logs configuration on initialization

### 3. Enhanced Embedding Model
**Changed:** `BAAI/bge-large-en-v1.5` (1024 dims)
**To:** `Alibaba-NLP/gte-Qwen2-1.5B-instruct` (1536 dims)
**Benefit:** State-of-the-art quality, Apache-2.0 license

## Implementation Needed

### Step 1: Apply Optimization in Pipeline
Need to call `segment_optimizer.optimize_segments()` after transcription but before speaker ID.

**Location:** `backend/scripts/common/enhanced_transcript_fetch.py`
**Method:** `fetch_transcript_with_speaker_id()` or similar

**Pseudocode:**
```python
# After getting segments from Whisper
segments = whisper_transcribe(audio)

# OPTIMIZE SEGMENTS (merge short ones)
if self.enable_segment_optimization:
    segments = self.segment_optimizer.optimize_segments(segments)
    logger.info(f"Optimized to {len(segments)} segments")

# Then do speaker ID on optimized (fewer) segments
if self.enable_speaker_id:
    segments = enhanced_asr.identify_speakers(segments)
```

### Step 2: Update Migration for 1536 Dimensions
**File:** `db/migrations/006_fix_segments_schema.sql`
**Status:** ✅ Already updated to 1536 dimensions

### Step 3: Re-run Migration
```bash
python run_migration.py
```

### Step 4: Restart Ingestion
```bash
# Kill current ingestion
# Clear database if needed
TRUNCATE TABLE segments CASCADE;
TRUNCATE TABLE sources CASCADE;

# Re-run with optimized settings
python backend\scripts\ingest_youtube_enhanced.py --source yt-dlp --limit 5 --skip-shorts --voices-dir .\voices
```

## Expected Results

### Before Optimization:
- 1000+ segments per 2-hour video
- 5-10 seconds per segment
- 50-100 characters per segment
- Heavy speaker ID processing

### After Optimization:
- 200-400 segments per 2-hour video
- 30-60 seconds per segment
- 400-1200 characters per segment
- 60-80% less speaker ID processing
- **Much better RAG context!**

## Performance Impact

### Speed Improvements:
1. **Fewer segments** = Less speaker ID processing
2. **Batch processing** = More efficient embeddings
3. **Better GPU utilization** = Fewer context switches

### Quality Improvements:
1. **Longer context** = Better semantic search
2. **Better summarization** = More coherent chunks
3. **Fewer boundary issues** = Less fragmented answers

## Next Steps

1. ✅ Update `.env` with segment optimization settings
2. ✅ Update `SegmentOptimizer` to use env vars
3. ✅ Update migration for 1536 dimensions
4. ⏳ Integrate optimizer into transcription pipeline
5. ⏳ Re-run migration
6. ⏳ Test with 5 videos
7. ⏳ Verify segment lengths in database

## Verification Queries

```sql
-- Check segment lengths
SELECT 
    AVG(LENGTH(text)) as avg_chars,
    MIN(LENGTH(text)) as min_chars,
    MAX(LENGTH(text)) as max_chars,
    AVG(end_sec - start_sec) as avg_duration,
    COUNT(*) as total_segments
FROM segments;

-- Should show:
-- avg_chars: 600-800
-- min_chars: 400+
-- max_chars: 1200+
-- avg_duration: 40-50 seconds
```
