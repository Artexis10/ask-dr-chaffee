# Real-Time Bottleneck Diagnosis

## Current State (CRITICAL)

```
io_q=28    ← 28 videos waiting to download
asr_q=0    ← ASR workers are IDLE (no work!)
db_q=0     ← DB workers are IDLE
SM=22%     ← GPU barely used
VRAM=35%   ← Only 5.6GB used (have 16GB available)
```

## Root Cause: I/O Bottleneck

**The problem:** Audio downloads are too slow!
- 28 videos queued for download
- ASR workers have nothing to process
- GPU sitting idle at 22%

**Why this happens:**
1. Network latency (YouTube throttling)
2. yt-dlp sequential downloads
3. Large video files (1.5h avg = 100-200MB each)

## The Real Bottleneck Hierarchy

```
Phase 1: Download Audio (BOTTLENECK!) ← 28 videos waiting
    ↓
Phase 2: ASR Processing (IDLE) ← 0 videos waiting
    ↓
Phase 3: Embeddings + DB (IDLE) ← 0 videos waiting
```

## Solutions (Priority Order)

### Priority 1: INCREASE I/O WORKERS (CRITICAL)

**Current:** 12 I/O workers
**Problem:** Not enough for YouTube's rate limits

```bash
# .env
IO_WORKERS=24  # Double from 12 to 24
```

**Why this works:**
- More concurrent downloads
- Better handling of YouTube throttling
- Keeps ASR queue fed

### Priority 2: Pre-download Audio Files

**Implement 3-phase pipeline** (from memory):
```
Phase 1: Bulk download all audio (parallel)
Phase 2: ASR + Speaker ID (GPU intensive)
Phase 3: Embeddings + DB (GPU intensive)
```

**Benefits:**
- Download once, process many times
- No GPU idle time
- Better error handling

### Priority 3: Reduce ASR Workers (Counter-intuitive!)

**Current:** 4 ASR workers
**Problem:** They're all idle anyway!

```bash
# .env
ASR_WORKERS=2  # Reduce from 4 to 2
```

**Why this works:**
- Frees up VRAM for larger batches
- ASR workers are waiting for I/O anyway
- Better memory efficiency

### Priority 4: Increase Embedding Batch Size

**Current:** 384 segments per batch
**Available VRAM:** 10GB unused!

```bash
# .env
BATCH_SIZE=768  # Double from 384 to 768
```

**Why this works:**
- Use available VRAM
- Faster embedding generation
- Better GPU utilization

## Recommended Configuration

### For Current Pipeline (Quick Fix)

```bash
# .env
IO_WORKERS=24        # Double I/O workers
ASR_WORKERS=2        # Reduce (they're idle anyway)
BATCH_SIZE=768       # Use available VRAM
DB_WORKERS=12        # Keep as is
```

**Expected improvement:**
- I/O queue: 28 → 5-10 (manageable)
- ASR queue: 0 → 2-4 (fed continuously)
- GPU: 22% → 70-80% (better, not perfect)

### For Optimal Pipeline (Requires Code Changes)

**Implement 3-phase bulk download:**

```python
# Phase 1: Bulk download (parallel)
audio_files = []
with ThreadPoolExecutor(max_workers=24) as executor:
    futures = [executor.submit(download_audio, video) for video in videos]
    for future in as_completed(futures):
        audio_files.append(future.result())

# Phase 2: ASR processing (now GPU can run continuously)
for audio_file in audio_files:
    asr_queue.put(audio_file)

# Phase 3: Embeddings + DB
```

**Expected improvement:**
- GPU: 90%+ utilization
- No I/O bottleneck
- Predictable processing time

## Why ASR_WORKERS=4 Didn't Help

**Theory:** More ASR workers = more GPU utilization
**Reality:** ASR workers are starved for input!

```
ASR Worker 1: Waiting for audio... 💤
ASR Worker 2: Waiting for audio... 💤
ASR Worker 3: Waiting for audio... 💤
ASR Worker 4: Waiting for audio... 💤

I/O Queue: [28 videos waiting to download...]
```

**The fix:** Feed the ASR workers faster (more I/O workers)

## Performance Estimate

### Current (Broken)

```
28 videos in queue
Download: ~2 minutes per video (sequential bottleneck)
ASR: Idle 80% of the time
Total: ~56 minutes just for downloads!
```

### After I/O Fix

```
28 videos in queue
Download: ~5 minutes total (24 parallel workers)
ASR: Continuous processing
Total: ~15-20 minutes for 28 videos
```

### After 3-Phase Pipeline

```
Phase 1: Bulk download (5 minutes)
Phase 2: ASR (10 minutes, GPU maxed)
Phase 3: Embeddings (5 minutes)
Total: ~20 minutes for 28 videos
```

## Immediate Action

```bash
# Stop current ingestion
Stop-Process -Name python -Force

# Update .env
IO_WORKERS=24
ASR_WORKERS=2
BATCH_SIZE=768

# Restart
python backend\scripts\ingest_youtube_enhanced.py --source yt-dlp --limit 50 --skip-shorts --voices-dir .\voices
```

## Long-Term Solution

Implement the 3-phase pipeline from memory:
1. Phase 1: Prefilter + bulk download (20 concurrent)
2. Phase 2: ASR + speaker ID (GPU intensive)
3. Phase 3: Embeddings + DB (GPU intensive)

This is the architecture that achieves 90%+ GPU utilization.
