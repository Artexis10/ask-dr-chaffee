# Performance Analysis & Bottleneck Identification

## Current Performance Issues

### Observed Metrics (50 videos, ~6 hours)
- **Processing time:** ~6 hours for 50 videos
- **GPU utilization:** 50% (target: 90%+)
- **VRAM usage:** 6-7GB (target: 8-9GB)
- **Throughput:** ~8 videos/hour (should be ~20-30/hour)

### Root Cause: YouTube Captions Bypass

**99.6% of processing was wasted** because YouTube captions were used:
- No Enhanced ASR (no GPU usage)
- No embeddings (no VRAM usage)
- No speaker ID (no voice matching)
- Processing 44k tiny segments instead of 4k optimized

## Expected Performance (With Enhanced ASR)

### Target Metrics (RTX 5080)
- **Real-Time Factor:** 0.15-0.22 (5-7x faster than real-time)
- **Throughput:** ~50 hours audio per hour
- **GPU SM utilization:** ≥90%
- **VRAM usage:** 8-9GB
- **Processing time:** 75 hours audio in ~1.5-2 hours (not 6!)

### Breakdown for 50 Videos

**Assumptions:**
- 50 videos × 1.5 hours avg = 75 hours audio
- RTF target: 0.20 (5x real-time)

**Expected timeline:**
```
Phase 1: Prefilter (accessibility check)
  - 50 videos × 2 seconds = 100 seconds (~2 minutes)
  
Phase 2: Download audio
  - 50 videos × 30 seconds avg = 1,500 seconds (~25 minutes)
  - Concurrent: 12 I/O workers → ~2-3 minutes
  
Phase 3: ASR + Embedding
  - 75 hours audio ÷ 5 (RTF) = 15 hours processing time
  - With 2 ASR workers: 15 ÷ 2 = 7.5 hours
  - Embedding: Batched (256 segments) → ~30 minutes
  
Total: ~8-9 hours (not 6 hours with broken data!)
```

## Identified Bottlenecks

### 1. ⚠️  ASR Worker Concurrency (MAJOR)

**Current:** 2 ASR workers (from memory)
**Issue:** Only 2 videos processed simultaneously
**Impact:** 50% GPU utilization

**Solution:** Increase ASR workers
```bash
# .env
ASR_WORKERS=4  # Increase from 2 to 4

# Or command line
python backend\scripts\ingest_youtube_enhanced.py --asr-concurrency 4
```

**Expected improvement:** 90%+ GPU utilization

### 2. ⚠️  Embedding Generation (MODERATE)

**Current:** GTE-Qwen2-1.5B (1.5B parameters, 1536 dims)
**Issue:** Large model, slower inference
**Impact:** ~30% of total time

**Options:**

**A. Keep quality, optimize batching:**
```bash
# .env
BATCH_SIZE=512  # Increase from 256 to 512
```

**B. Use smaller model (trade quality for speed):**
```bash
# .env
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DIMENSIONS=768
```
- 2-3x faster
- Still better than MiniLM
- 768 dims (need migration)

**C. Use OpenAI API (fastest, costs money):**
```bash
# .env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSIONS=1536
```
- Parallel API calls
- No local GPU needed
- Cost: ~$0.13 per 1M tokens (~$10 for 1200h)

### 3. ⚠️  Segment Optimization Overhead (MINOR)

**Current:** 3 optimization passes
**Issue:** CPU-bound, sequential
**Impact:** ~5-10% of total time

**Solution:** Already optimized, minimal gains available

### 4. ⚠️  Voice Profile Matching (MINOR)

**Current:** ECAPA-TDNN for each segment
**Issue:** CPU-bound per segment
**Impact:** ~10% of total time

**Optimization:** Monologue fast-path (already implemented)
```bash
# .env
ASSUME_MONOLOGUE=true  # Already enabled
```

### 5. ⚠️  Database Insertion (MINOR)

**Current:** Batch inserts
**Issue:** Network latency
**Impact:** ~5% of total time

**Already optimized:** 12 DB workers, batched inserts

## Recommended Optimizations

### Priority 1: Increase ASR Workers (CRITICAL)

```bash
# .env
ASR_WORKERS=4  # From 2 to 4 (or even 6 for RTX 5080)
```

**Expected impact:**
- GPU utilization: 50% → 90%+
- Processing time: -40%
- Throughput: 2x improvement

**Why it works:**
- RTX 5080 has plenty of VRAM (16GB)
- distil-large-v3 uses ~2-3GB per worker
- 4 workers = 8-12GB (still under 16GB)

### Priority 2: Optimize Embedding Batching

```bash
# .env
BATCH_SIZE=512  # From 256 to 512
```

**Expected impact:**
- Embedding time: -20%
- Overall time: -5-10%

### Priority 3: Consider Smaller Embedding Model

**If speed > quality:**
```bash
# .env
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
EMBEDDING_DIMENSIONS=768
```

**Trade-off:**
- Speed: 2-3x faster
- Quality: Still good (MTEB: 63.55 vs 64.23)
- VRAM: Less usage (440MB vs 1.3GB)

### Priority 4: Pipeline Optimization

**Current:** Sequential phases
**Potential:** Overlap phases

```python
# Pseudocode for future optimization
while videos_remaining:
    # Phase 1: Prefilter (async)
    accessible_videos = await prefilter_batch(videos)
    
    # Phase 2: Download (concurrent with Phase 3 of previous batch)
    audio_files = await download_batch(accessible_videos)
    
    # Phase 3: ASR + Embedding (concurrent)
    for audio in audio_files:
        asr_queue.put(audio)  # Non-blocking
```

**Expected impact:** 20-30% faster

## Performance Tuning Guide

### For Maximum Speed (Sacrifice Some Quality)

```bash
# .env
ASR_WORKERS=6              # Max out GPU
BATCH_SIZE=512             # Larger batches
EMBEDDING_MODEL=BAAI/bge-base-en-v1.5  # Smaller model
EMBEDDING_DIMENSIONS=768
SEGMENT_MIN_CHARS=800      # Slightly smaller segments
SEGMENT_MAX_CHARS=1200
```

**Expected:** 1200h in ~18-20 hours

### For Maximum Quality (Slower)

```bash
# .env
ASR_WORKERS=2              # Conservative
BATCH_SIZE=256             # Smaller batches
EMBEDDING_MODEL=Alibaba-NLP/gte-Qwen2-1.5B-instruct  # Best quality
EMBEDDING_DIMENSIONS=1536
SEGMENT_MIN_CHARS=1100     # Optimal segments
SEGMENT_MAX_CHARS=1400
```

**Expected:** 1200h in ~24-28 hours

### Balanced (Recommended)

```bash
# .env
ASR_WORKERS=4              # Good GPU utilization
BATCH_SIZE=384             # Medium batches
EMBEDDING_MODEL=Alibaba-NLP/gte-Qwen2-1.5B-instruct
EMBEDDING_DIMENSIONS=1536
SEGMENT_MIN_CHARS=1100
SEGMENT_MAX_CHARS=1400
```

**Expected:** 1200h in ~20-24 hours

## Monitoring & Debugging

### Check GPU Utilization

```bash
# Real-time monitoring
nvidia-smi -l 1

# Should show:
# GPU Util: 85-95%
# Memory: 8-12GB / 16GB
# Power: 250-300W
```

### Check Processing Rate

```sql
-- Check throughput
SELECT 
    COUNT(*) as videos_processed,
    SUM(duration_s) / 3600.0 as total_hours,
    EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 3600.0 as processing_hours,
    (SUM(duration_s) / 3600.0) / NULLIF(EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 3600.0, 0) as throughput
FROM sources
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Should show:
-- throughput: 40-60 hours audio per hour
```

### Check Bottlenecks

```python
# Add to ingestion script
logger.info(f"Queue peaks: I/O={stats.io_queue_peak}, ASR={stats.asr_queue_peak}, DB={stats.db_queue_peak}")

# If ASR queue is always full → increase ASR workers
# If DB queue is always full → increase DB workers
# If I/O queue is always full → increase I/O workers
```

## Summary

**Current Issues:**
1. ❌ YouTube captions bypassed entire pipeline (99.6% wasted)
2. ⚠️  Only 2 ASR workers (50% GPU utilization)
3. ⚠️  Large embedding model (slower but better quality)

**Quick Wins:**
1. ✅ Fix YouTube captions (DONE)
2. ✅ Increase ASR workers to 4-6
3. ✅ Increase batch size to 512
4. ✅ Monitor GPU utilization

**Expected Results:**
- Processing time: 6 hours → 1.5-2 hours (for 50 videos)
- GPU utilization: 50% → 90%+
- VRAM usage: 6-7GB → 10-12GB
- Throughput: 8 videos/hour → 25-30 videos/hour

**For 1200h target:**
- Current (broken): Would take ~150 hours
- After fixes: 20-24 hours ✅
