# Ingestion Scripts Guide

## Active Scripts (Use These)

### **`ingest_youtube_enhanced.py`** ⭐ PRIMARY INGESTION SCRIPT
**RTX 5080 optimized for 1200h audio processing in ≤24h**

The main production ingestion script with comprehensive optimizations:
- 3-phase pipeline: prefilter → bulk download → ASR+embedding
- Optimized concurrency: 12 I/O, 2 ASR, 12 DB workers
- Conditional diarization with monologue fast-path
- Real-time factor: 0.15-0.22 (5-7x faster than real-time)
- Mandatory speaker identification (Chaffee voice profile)

**Usage:**
```bash
# Standard ingestion with speaker ID
python backend\scripts\ingest_youtube_enhanced.py --source yt-dlp --limit 50 --update-profile --skip-shorts --voices-dir .\voices

# Production mode (no audio storage)
python backend\scripts\ingest_youtube_enhanced.py --source yt-dlp --production-mode --skip-shorts

# Local files
python backend\scripts\ingest_youtube_enhanced.py --source local --local-dir .\audio_files
```

**Key Features:**
- Phase 1 accessibility prefiltering (20 concurrent checks)
- Members-only content detection
- Content hash deduplication
- GPU telemetry with performance warnings
- Batched embeddings (256 segments per batch)

---

## Utility Scripts

### `voice_bootstrap.py`
Create/update Chaffee voice profile from seed videos.

**Usage:**
```bash
python backend\scripts\voice_bootstrap.py --voices-dir .\voices --overwrite
```

### `cleanup_audio.py`
Manage audio storage disk space.

**Usage:**
```bash
# Show statistics
python cleanup_audio.py stats

# Delete files older than 7 days
python cleanup_audio.py older-than --days 7

# Delete largest files
python cleanup_audio.py largest --count 20
```

---

## Deprecated Scripts (Do Not Use)

### ⚠️ `ingest_youtube_enhanced_asr.py`
**DEPRECATED** - Use `ingest_youtube_enhanced.py` instead.
Earlier version before RTX 5080 optimizations were merged.

### ⚠️ `ingest_to_production.py`
**DEPRECATED** - Use `ingest_youtube_enhanced.py` with `--production-mode` instead.
Functionality merged into main script.

### ⚠️ `ingest_zoom.py`
**DEPRECATED** - Zoom ingestion not currently in use.
May be revived if Zoom content is needed.

### ⚠️ `legacy/` directory
Contains old ingestion scripts kept for reference:
- `ingest_youtube.py` - Original basic ingestion
- `ingest_youtube_optimized.py` - Early optimization attempt
- `ingest_youtube_robust.py` - Robustness improvements
- `ingest_youtube_robust_optimized.py` - Combined approach
- `ingest_youtube_true_parallel.py` - Parallel processing experiment
- `ingest_youtube_with_speaker_id.py` - Early speaker ID integration

---

## Audio Storage

Downloaded audio files are stored in `audio_storage/` directory.

**Purpose:**
- Voice profile creation/enrollment (extracting speaker embeddings)
- Debugging/re-processing with different settings
- **NOT stored in database** - only kept locally

**Cleanup Options:**

1. **Automatic cleanup** (recommended for one-time ingestion):
   ```bash
   # Add to .env
   CLEANUP_AUDIO_AFTER_PROCESSING=true
   ```

2. **Manual cleanup** (recommended for development):
   ```bash
   python cleanup_audio.py older-than --days 7
   ```

3. **Production mode** (no audio storage):
   ```bash
   python backend\scripts\ingest_youtube_enhanced.py --production-mode
   ```

**Disk Space Estimates:**
- WAV (uncompressed): ~10MB per minute
- 1 hour video: ~600MB (WAV)
- 20 videos @ 1h each: ~12GB

See `AUDIO_CLEANUP.md` for detailed cleanup guide.

---

## Configuration

Key environment variables in `.env`:

```bash
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/askdrchaffee

# YouTube
YOUTUBE_CHANNEL_URL=https://www.youtube.com/@anthonychaffeemd

# Whisper (RTX 5080 optimized)
WHISPER_MODEL=distil-large-v3

# Speaker Identification (MANDATORY)
ENABLE_SPEAKER_ID=true
VOICES_DIR=voices
CHAFFEE_MIN_SIM=0.62

# Audio Storage
AUDIO_STORAGE_DIR=./audio_storage
CLEANUP_AUDIO_AFTER_PROCESSING=false

# yt-dlp Configuration
YTDLP_OPTS=--sleep-requests 1 --max-sleep-interval 3 --retries 10 --fragment-retries 10 --socket-timeout 20
```

---

## Performance Targets (RTX 5080)

- **Real-Time Factor:** 0.15-0.22 (5-7x faster than real-time)
- **Throughput:** ~50h audio per hour → 1200h in ~24h
- **GPU SM utilization:** ≥90% sustained
- **VRAM usage:** ≤9GB
- **Accuracy:** ≤0.5% WER vs large-v3

---

## Troubleshooting

### "Members-only content" errors
Normal - script automatically filters these out. Phase 1 prefiltering catches most, but some may slip through.

### "yt-dlp download failed"
Check:
1. Video is not private/deleted
2. Internet connection is stable
3. yt-dlp is up to date: `pip install -U yt-dlp`

### Low GPU utilization
Increase concurrency:
```bash
python backend\scripts\ingest_youtube_enhanced.py --io-workers 16 --asr-workers 3
```

### Out of VRAM
Reduce ASR workers:
```bash
python backend\scripts\ingest_youtube_enhanced.py --asr-workers 1
```

### Audio storage filling up disk
Enable automatic cleanup or run manual cleanup:
```bash
python cleanup_audio.py older-than --days 7
```
