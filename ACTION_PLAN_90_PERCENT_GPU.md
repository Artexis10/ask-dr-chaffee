# Action Plan: Achieve 90% GPU Utilization

## Current State
- GPU: 50% utilization
- VRAM: 6.4GB / 16GB (9.6GB unused)
- Bottleneck: Sequential processing + Pyannote overhead

## Immediate Actions (No Code Changes)

### 1. Update Configuration

```bash
# .env (ALREADY UPDATED)
ASR_WORKERS=4        # 2 → 4 (now that I/O is fixed)
BATCH_SIZE=1024      # 768 → 1024 (use more VRAM)
```

**Expected improvement:** 50% → 65-70% GPU

### 2. Restart Ingestion

```bash
# Stop current
Stop-Process -Name python -Force

# Restart with new settings
python backend\scripts\ingest_youtube_enhanced.py \
  --source yt-dlp \
  --limit 50 \
  --skip-shorts \
  --voices-dir .\voices
```

### 3. Monitor Performance

```bash
# Watch GPU in real-time
nvidia-smi -l 1

# Look for:
✅ GPU: 65-75% (improvement from 50%)
✅ VRAM: 10-12GB (improvement from 6.4GB)
✅ io_q: 5-10 (down from 28)
✅ asr_q: 3-4 (up from 0)
```

## Medium-Term Actions (Code Investigation)

### 1. Check if Pyannote is the Bottleneck

**Your log showed:**
```
2025-10-01 11:05:58,028 - INFO - __main__ - 🎙️ Multi-speaker content detected
```

**This means Pyannote IS running!**

**Questions to investigate:**
1. Is Pyannote running on EVERY video?
2. How long does Pyannote take per video?
3. Can we skip it for monologues?

**Action:** Add timing logs to measure Pyannote overhead

### 2. Check Embedding Batching

**From memory:** Should batch 256 segments at once

**Questions:**
1. Are embeddings batched across videos?
2. Or per-video (slower)?

**Action:** Check logs for batch sizes

### 3. Profile Single Video

```bash
# Process one video with timing
python backend\scripts\ingest_youtube_enhanced.py \
  --source yt-dlp \
  --limit 1 \
  --verbose \
  --voices-dir .\voices \
  2>&1 | tee profile.log

# Analyze timing:
grep -E "Whisper|Pyannote|Embedding|Speaker" profile.log
```

## Long-Term Solution (Code Changes Required)

### Option 1: Skip Pyannote for Monologues

**From memory:** "Conditional diarization with monologue fast-path"

**Implementation:**
```python
# In Enhanced ASR
if assume_monologue and is_single_speaker(audio):
    # Skip Pyannote, use Whisper segments directly
    for segment in whisper_segments:
        segment.speaker_label = 'Chaffee'
    logger.info("✅ Monologue fast-path: Skipped Pyannote")
else:
    # Run Pyannote for multi-speaker
    diarized_segments = pyannote.diarize(audio)
    logger.info("🎙️ Multi-speaker: Running Pyannote")
```

**Expected improvement:** 30-40% faster for monologues

### Option 2: True Pipeline Parallelism

**From memory:** "3-phase pipeline: prefilter → bulk download → ASR+embedding"

**Implementation:**
```python
# Phase 1: Bulk download all audio files
audio_files = []
with ThreadPoolExecutor(max_workers=24) as io_pool:
    futures = [io_pool.submit(download_audio, v) for v in videos]
    for future in as_completed(futures):
        audio_files.append(future.result())

# Phase 2: ASR processing (4 workers, GPU maxed)
segments_queue = Queue()
with ThreadPoolExecutor(max_workers=4) as asr_pool:
    asr_futures = [asr_pool.submit(process_asr, audio) for audio in audio_files]
    
    # Phase 3: Embeddings (as ASR completes)
    with ThreadPoolExecutor(max_workers=2) as embed_pool:
        for future in as_completed(asr_futures):
            segments = future.result()
            embed_pool.submit(generate_embeddings, segments)
```

**Expected improvement:** 90%+ GPU utilization

### Option 3: Batch Embeddings Across Videos

**Current:** Generate embeddings per video
**Should be:** Accumulate segments, batch across videos

```python
# Accumulate segments from multiple videos
all_segments = []
for video in processed_videos:
    all_segments.extend(video.segments)
    
    # Batch every 1000 segments
    if len(all_segments) >= 1000:
        embeddings = embedder.generate_embeddings(
            [s.text for s in all_segments],
            batch_size=1024
        )
        all_segments = []
```

**Expected improvement:** 15-20% faster embeddings

## Performance Targets

### Current (50% GPU)
```
Throughput: ~18-25h audio per hour
50 videos: ~3-4 hours
1200h target: ~48-60 hours
```

### After Config Changes (65-75% GPU)
```
Throughput: ~30-35h audio per hour
50 videos: ~2-2.5 hours
1200h target: ~34-40 hours
```

### After Code Optimizations (90% GPU)
```
Throughput: ~45-55h audio per hour
50 videos: ~1.5-2 hours
1200h target: ~22-27 hours ✅
```

## Recommended Approach

### Phase 1: Quick Wins (NOW)
1. ✅ Update .env (ASR_WORKERS=4, BATCH_SIZE=1024)
2. ✅ Restart ingestion
3. ✅ Monitor improvement (50% → 65-75%)

### Phase 2: Investigation (NEXT)
1. Profile single video to find bottleneck
2. Measure Pyannote overhead
3. Check if embeddings are batched
4. Identify which phase takes longest

### Phase 3: Code Optimization (LATER)
1. Implement monologue fast-path (skip Pyannote)
2. Implement pipeline parallelism
3. Batch embeddings across videos
4. Target: 90% GPU utilization

## Monitoring Commands

### Real-time GPU monitoring
```bash
nvidia-smi -l 1
```

### Check queue states
```bash
# Look in logs for:
"queues: io=X asr=Y db=Z"

# Healthy state:
io=5-10   (not starved, not overloaded)
asr=3-4   (workers busy)
db=2-5    (processing continuously)
```

### Check processing rate
```sql
-- Run every 10 minutes
SELECT 
    COUNT(*) as videos,
    SUM(duration_s) / 3600.0 as hours,
    EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 3600.0 as elapsed,
    (SUM(duration_s) / 3600.0) / NULLIF(EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 3600.0, 0) as throughput
FROM sources
WHERE created_at > NOW() - INTERVAL '1 hour';

-- Target throughput: 45-55h audio per hour
```

## Summary

**Immediate actions:**
- ✅ Config updated (ASR_WORKERS=4, BATCH_SIZE=1024)
- ⏳ Restart and monitor
- 📊 Expect 65-75% GPU (up from 50%)

**Next steps:**
- Profile to find remaining bottlenecks
- Likely Pyannote overhead on every video
- Consider implementing monologue fast-path

**Long-term goal:**
- 90% GPU utilization
- 1200h in 22-27 hours
- Requires pipeline parallelism
