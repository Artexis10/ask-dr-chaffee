# URGENT: Ingestion Pipeline Broken

## Critical Issues Found

### 1. **99.6% of Data is Broken**
- 44,156 / 44,328 segments have NO embeddings
- 44,156 / 44,328 segments have NULL speaker labels
- Average segment: 54 chars (should be 1100+)
- Average duration: 1.6s (should be 60-90s)

### 2. **Enhanced ASR Not Running**
- All videos show Method: UNKNOWN
- No whisper model recorded
- No speaker identification
- No segment optimization
- No embeddings generated

### 3. **Performance Impact**
- Processing 44k tiny segments instead of ~4k optimized
- GPU only 50% utilized (not doing embeddings)
- VRAM only 6-7GB (not loading embedding model)
- Taking hours for 50 videos (should be ~1 hour)

## Root Cause

**YouTube captions are being used instead of Enhanced ASR**

Despite our fix yesterday, the ingestion is still using YouTube captions. Possible reasons:

1. **`--force-whisper` flag not passed** to ingestion command
2. **YouTube captions available** and being preferred
3. **Enhanced ASR initialization failing silently**
4. **Voice profile not loading correctly**

## Immediate Actions Required

### 1. Stop Current Ingestion
```bash
Stop-Process -Name python -Force
```

### 2. Clear Broken Data
```bash
python -c "import psycopg2; import os; from dotenv import load_dotenv; load_dotenv(); conn = psycopg2.connect(os.getenv('DATABASE_URL')); cur = conn.cursor(); cur.execute('TRUNCATE TABLE segments CASCADE'); cur.execute('TRUNCATE TABLE sources CASCADE'); conn.commit(); print('Database cleared')"
```

### 3. Verify Configuration
Check `.env`:
```bash
ENABLE_SPEAKER_ID=true
VOICES_DIR=voices
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=Alibaba-NLP/gte-Qwen2-1.5B-instruct
EMBEDDING_DIMENSIONS=1536
```

### 4. Verify Voice Profile Exists
```bash
Get-ChildItem voices\chaffee.json
```

### 5. Run with Correct Flags
```bash
python backend\scripts\ingest_youtube_enhanced.py \
  --source yt-dlp \
  --limit 5 \
  --skip-shorts \
  --voices-dir .\voices \
  --force-whisper \
  --channel-url "https://www.youtube.com/@anthonychaffeemd"
```

**CRITICAL:** Must include `--force-whisper` flag!

## What Went Wrong

Yesterday's fix to `enhanced_transcript_fetch.py` line 268 should have worked:

```python
if not force_enhanced_asr and not use_enhanced_asr and not is_local_file and not self.enable_speaker_id:
```

But the ingestion command likely **didn't include `--force-whisper`**, so:
- `force_enhanced_asr = False`
- YouTube captions were used
- Enhanced ASR never ran

## Expected vs Actual

### Expected (with Enhanced ASR):
- Method: `enhanced_asr` or `enhanced_asr_monologue`
- Model: `distil-large-v3`
- Segments: ~4,000 (optimized)
- Avg chars: 1100-1400
- Avg duration: 60-90s
- Speaker labels: 100% labeled
- Embeddings: 100% embedded
- GPU: 90%+ utilization
- VRAM: 8-9GB

### Actual (YouTube captions):
- Method: `UNKNOWN` (YouTube captions)
- Model: `N/A`
- Segments: 44,328 (raw)
- Avg chars: 54
- Avg duration: 1.6s
- Speaker labels: 0.4% labeled
- Embeddings: 0.4% embedded
- GPU: 50% utilization
- VRAM: 6-7GB

## Verification After Fix

After re-running ingestion, check:

```sql
SELECT 
    metadata->>'transcript_method' as method,
    metadata->>'whisper_model' as model,
    COUNT(*) as videos,
    SUM((SELECT COUNT(*) FROM segments WHERE video_id = source_id)) as total_segments,
    AVG((SELECT AVG(LENGTH(text)) FROM segments WHERE video_id = source_id)) as avg_chars
FROM sources
GROUP BY 1, 2;
```

Should show:
- Method: `enhanced_asr` or `enhanced_asr_monologue`
- Model: `distil-large-v3`
- Avg chars: 1000+

## Performance Estimate

**With correct Enhanced ASR:**
- 50 videos × 1.5 hours avg = 75 hours audio
- RTF target: 0.15-0.22 (5-7x real-time)
- Processing time: 75 / 5 = **~15 hours** (not 6+ hours!)
- Segments: ~7,500 (not 44,000)
- All with embeddings and speaker labels

**Why it's slower than target:**
- Embedding generation (GTE-Qwen2-1.5B is large)
- Speaker identification overhead
- Disk I/O for audio storage
- Network delays for downloads

**Target is achievable with:**
- Batch processing optimizations
- Concurrent workers (already configured)
- GPU optimization (already done)
