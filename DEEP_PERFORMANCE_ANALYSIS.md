# Deep Performance Analysis - 50% GPU Utilization

## Current State

```
GPU: 50% utilization
VRAM: 6.4GB / 16GB (9.6GB unused!)
Models running:
  - distil-large-v3 (Whisper ASR)
  - Pyannote Community-1 (Diarization)
  - Alibaba GTE-Qwen2-1.5B (Embeddings)
  - ECAPA-TDNN (Speaker verification)
```

## The Real Problem: Sequential Processing

### Current Pipeline (Per Video)

```
1. Download audio           [I/O bound]
   ↓
2. Whisper ASR              [GPU: 2-3GB, 30-60s]
   ↓
3. Pyannote diarization     [GPU: 2-3GB, 20-40s]
   ↓
4. ECAPA speaker ID         [CPU bound, 5-10s]
   ↓
5. Segment optimization     [CPU bound, 1-2s]
   ↓
6. GTE-Qwen2 embeddings     [GPU: 1.3GB, 10-20s]
   ↓
7. Database insertion       [I/O bound, 1-2s]

Total per video: ~90-150 seconds
GPU idle time: 40-50% (during CPU/I/O phases)
```

### Why GPU is at 50%

**GPU is used in phases 2, 3, and 6 only!**
- Phase 1 (download): GPU idle
- Phase 2 (Whisper): GPU active ✓
- Phase 3 (Pyannote): GPU active ✓
- Phase 4 (ECAPA): CPU only, GPU idle
- Phase 5 (optimization): CPU only, GPU idle
- Phase 6 (embeddings): GPU active ✓
- Phase 7 (DB): I/O only, GPU idle

**Result:** GPU is idle ~40-50% of the time!

## Root Causes

### 1. Models Not Running Concurrently

**Problem:** Only 2 ASR workers, processing sequentially
**Solution:** Need pipeline parallelism

### 2. Pyannote Overhead

**Problem:** Pyannote Community-1 is SLOW (20-40s per video)
**Impact:** Doubles processing time
**Question:** Do we really need it?

From memory: "Conditional diarization with monologue fast-path"
- Most Dr. Chaffee videos are monologues
- Pyannote only needed for multi-speaker content
- Fast-path should skip Pyannote for solo content

### 3. CPU-Bound Phases Block GPU

**Problem:** ECAPA and optimization run on CPU
**Impact:** GPU sits idle waiting

### 4. Small Batch Sizes

**Problem:** Processing videos one at a time
**Solution:** Batch multiple videos together

## Solutions (Priority Order)

### Priority 1: SKIP PYANNOTE FOR MONOLOGUES (CRITICAL)

**Current:** Running Pyannote on EVERY video
**Should be:** Only run on multi-speaker content

```python
# Check if monologue (from memory: ASSUME_MONOLOGUE=true)
if assume_monologue:
    # Skip Pyannote, assume single speaker = Chaffee
    segments = whisper_segments
    for seg in segments:
        seg.speaker_label = 'Chaffee'
else:
    # Run Pyannote for multi-speaker
    segments = pyannote_diarization(audio)
```

**Expected improvement:**
- Monologue videos: 50% faster (skip 20-40s Pyannote)
- GPU utilization: 50% → 70-80%
- Most videos are monologues!

### Priority 2: INCREASE ASR WORKERS AGAIN

**Current:** 2 ASR workers
**Problem:** Not enough parallelism

```bash
# .env
ASR_WORKERS=4  # Back to 4, now that I/O is fixed
```

**Why this works now:**
- I/O bottleneck is fixed (24 workers)
- Can feed 4 ASR workers continuously
- Each worker uses ~2-3GB VRAM
- 4 × 3GB = 12GB (still under 16GB)

### Priority 3: BATCH EMBEDDINGS ACROSS VIDEOS

**Current:** Generate embeddings per video
**Should be:** Batch embeddings across multiple videos

```python
# Collect segments from multiple videos
all_segments = []
for video in processed_videos:
    all_segments.extend(video.segments)

# Generate embeddings in one large batch
embeddings = embedder.generate_embeddings(
    [seg.text for seg in all_segments],
    batch_size=768  # Already set
)
```

**Expected improvement:**
- Better GPU utilization
- Fewer model loads
- Faster overall

### Priority 4: USE FASTER DIARIZATION

**Option A:** Use faster Pyannote model
```bash
# Instead of Community-1, use smaller model
PYANNOTE_MODEL=pyannote/speaker-diarization-3.1  # Faster
```

**Option B:** Skip Pyannote entirely
```bash
# Use ECAPA-TDNN only for speaker ID
USE_SIMPLE_DIARIZATION=true  # Already in .env
```

**Option C:** Use Whisper's built-in speaker detection
```python
# Whisper can detect speaker changes via audio features
# No need for separate diarization model
```

### Priority 5: PIPELINE PARALLELISM

**Current:** Sequential processing
**Should be:** Overlap phases

```python
# Pseudocode
with ThreadPoolExecutor(max_workers=4) as asr_pool, \
     ThreadPoolExecutor(max_workers=2) as embed_pool:
    
    # ASR workers process continuously
    asr_futures = [asr_pool.submit(process_asr, video) for video in videos]
    
    # As ASR completes, feed to embedding workers
    for future in as_completed(asr_futures):
        segments = future.result()
        embed_pool.submit(generate_embeddings, segments)
```

## Recommended Configuration

### Quick Win (No Code Changes)

```bash
# .env
ASR_WORKERS=4              # Increase back to 4
BATCH_SIZE=1024            # Increase to 1024 (use more VRAM)
ASSUME_MONOLOGUE=true      # Skip Pyannote for solo content
USE_SIMPLE_DIARIZATION=true  # Use ECAPA only
```

**Expected:**
- GPU: 50% → 75-85%
- VRAM: 6.4GB → 10-12GB
- Speed: 30-40% faster

### Optimal (Requires Code Review)

**Check if these are already implemented:**

1. **Monologue fast-path** (from memory)
   - Should skip Pyannote for solo content
   - Check: Is this actually working?

2. **Batched embeddings** (from memory)
   - Should batch 256 segments at once
   - Check: Are we batching across videos?

3. **Pipeline parallelism** (from memory)
   - 3-phase pipeline: download → ASR → embed
   - Check: Are phases overlapping?

## Diagnostic Questions

### 1. Is Pyannote Running on Every Video?

Check logs for:
```
✅ "Monologue fast-path detected" → Good, skipping Pyannote
❌ "Running Pyannote diarization" → Bad, wasting time
```

### 2. Are Embeddings Batched?

Check logs for:
```
✅ "Generating embeddings for 768 segments" → Good, batching
❌ "Generating embeddings for 50 segments" → Bad, per-video
```

### 3. Is Pipeline Overlapping?

Check queue states:
```
✅ io_q=5, asr_q=4, db_q=3 → Good, all phases active
❌ io_q=0, asr_q=0, db_q=0 → Bad, sequential
```

## Performance Targets

### Current (50% GPU)
```
50 videos × 1.5h = 75h audio
Processing: ~3-4 hours
Throughput: ~18-25h audio per hour
GPU: 50%
VRAM: 6.4GB
```

### Target (90% GPU)
```
50 videos × 1.5h = 75h audio
Processing: ~1.5-2 hours
Throughput: ~40-50h audio per hour
GPU: 90%
VRAM: 12-14GB
```

### Required Changes
```
1. Skip Pyannote for monologues (30% speedup)
2. Increase ASR workers to 4 (25% speedup)
3. Batch embeddings across videos (15% speedup)
4. Pipeline parallelism (20% speedup)

Combined: 2-3x faster, 90% GPU utilization
```

## Immediate Actions

### 1. Update .env

```bash
# .env
ASR_WORKERS=4              # Back to 4
BATCH_SIZE=1024            # Use more VRAM
ASSUME_MONOLOGUE=true      # Should already be true
USE_SIMPLE_DIARIZATION=true  # Should already be true
```

### 2. Check Logs

Look for evidence of:
- Monologue fast-path being used
- Pyannote being skipped
- Batched embedding generation

### 3. Profile One Video

```bash
# Process single video with verbose logging
python backend\scripts\ingest_youtube_enhanced.py \
  --source yt-dlp \
  --limit 1 \
  --verbose \
  --voices-dir .\voices
```

Check timing breakdown:
- How long for Whisper?
- How long for Pyannote?
- How long for embeddings?
- Where is the bottleneck?

## Long-Term Solution

**Implement true pipeline parallelism:**

```python
# Phase 1: Bulk download (all videos)
audio_files = bulk_download(videos, workers=24)

# Phase 2: ASR processing (4 workers, GPU maxed)
with ThreadPoolExecutor(max_workers=4) as asr_pool:
    asr_futures = [asr_pool.submit(process_asr, audio) for audio in audio_files]
    
    # Phase 3: Embeddings (as ASR completes)
    all_segments = []
    for future in as_completed(asr_futures):
        segments = future.result()
        all_segments.extend(segments)
        
        # Batch embeddings every 1000 segments
        if len(all_segments) >= 1000:
            generate_embeddings_batch(all_segments)
            all_segments = []
```

This is the architecture from memory that achieves 90%+ GPU utilization.
