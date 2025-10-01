# Codebase Cleanup Plan

## Dependency Analysis for `ingest_youtube_enhanced.py`

### ✅ KEEP - Active Dependencies

#### Core Ingestion Modules
- `list_videos_yt_dlp.py` - Video listing from yt-dlp
- `list_videos_api.py` - Video listing from YouTube API
- `local_file_lister.py` - Local file processing
- `enhanced_transcript_fetch.py` - Main transcription orchestrator
- `database_upsert.py` - Database operations
- `segments_database.py` - Segment storage
- `embeddings.py` - Embedding generation
- `transcript_common.py` - Common transcript utilities
- `proxy_manager.py` - Proxy configuration

#### Transcription & ASR
- `transcript_fetch.py` - Base transcript fetcher (parent of enhanced)
- `enhanced_asr.py` - Enhanced ASR with speaker ID
- `enhanced_asr_config.py` - ASR configuration
- `multi_model_whisper.py` - Multi-model Whisper pool for RTX 5080
- `downloader.py` - Audio downloading with yt-dlp

#### Speaker Identification
- **`voice_enrollment_optimized.py`** ✅ ACTIVE - Used by enhanced_asr.py and ingest_youtube_enhanced.py
- `simple_diarization.py` - Speaker diarization
- `speaker_utils.py` - Speaker utilities

#### Optimization & Processing
- `segment_optimizer.py` - Segment optimization for search
- `db_optimization.py` - Database optimization utilities

---

## ⚠️ DEPRECATE/DELETE - Unused Files

### Voice Enrollment Duplicates (DELETE)
- ❌ `voice_enrollment.py` - Old version, replaced by optimized
- ❌ `voice_enrollment_fixed.py` - Intermediate fix, superseded
- ❌ `voice_enrollment_new.py` - Experimental version, not used
- ❌ `voice_storage.py` - Unused storage abstraction

**Action:** Delete these files. Only `voice_enrollment_optimized.py` is used.

### Transcript Processing Duplicates (DEPRECATE)
- ⚠️ `transcript_api.py` - Legacy API wrapper
- ⚠️ `transcript_processor.py` - Old processing logic
- ⚠️ `transcript_service_production.py` - Unused production service
- ⚠️ `transcripts.py` - Legacy transcript handling

**Action:** Move to `legacy/` or mark as deprecated.

### UTF-8 Fix Duplicates (DELETE)
- ❌ `simple_utf8_fix.py` - Superseded by fixes in main files
- ❌ `ultimate_utf8_fix.py` - Experimental, not used

**Action:** Delete - UTF-8 handling is now built into main files.

### Deprecated Modules
- ⚠️ `simple_diarization-deprecated.py` - Already marked deprecated
- ⚠️ `async_downloader.py` - Not used by enhanced pipeline
- ⚠️ `whisper_parallel.py` - Replaced by multi_model_whisper.py
- ⚠️ `monitoring.py` - Unused monitoring utilities
- ⚠️ `reranker.py` - Not used in current pipeline

**Action:** Move to `legacy/` directory.

### Utility Files (KEEP)
- ✅ `database.py` - Database utilities (may be used by other modules)
- ✅ `asr_output_formats.py` - ASR output formatting
- ✅ `__init__.py` - Package initialization

---

## Cleanup Actions

### Phase 1: Delete Obvious Duplicates (Safe)
```bash
# Voice enrollment duplicates
rm backend/scripts/common/voice_enrollment.py
rm backend/scripts/common/voice_enrollment_fixed.py
rm backend/scripts/common/voice_enrollment_new.py
rm backend/scripts/common/voice_storage.py

# UTF-8 fix duplicates
rm backend/scripts/common/simple_utf8_fix.py
rm backend/scripts/common/ultimate_utf8_fix.py

# Already deprecated
rm backend/scripts/common/simple_diarization-deprecated.py
```

### Phase 2: Move to Legacy (Preserve for Reference)
```bash
# Create legacy directory if needed
mkdir -p backend/scripts/common/legacy

# Move deprecated modules
mv backend/scripts/common/transcript_api.py backend/scripts/common/legacy/
mv backend/scripts/common/transcript_processor.py backend/scripts/common/legacy/
mv backend/scripts/common/transcript_service_production.py backend/scripts/common/legacy/
mv backend/scripts/common/transcripts.py backend/scripts/common/legacy/
mv backend/scripts/common/async_downloader.py backend/scripts/common/legacy/
mv backend/scripts/common/whisper_parallel.py backend/scripts/common/legacy/
mv backend/scripts/common/monitoring.py backend/scripts/common/legacy/
mv backend/scripts/common/reranker.py backend/scripts/common/legacy/
```

### Phase 3: Mark Deprecated in Code
Add deprecation warnings to files being moved to legacy.

---

## Final Active Module List (After Cleanup)

### Core (17 files)
1. `__init__.py`
2. `asr_output_formats.py`
3. `database.py`
4. `database_upsert.py`
5. `db_optimization.py`
6. `downloader.py`
7. `embeddings.py`
8. `enhanced_asr.py`
9. `enhanced_asr_config.py`
10. `enhanced_transcript_fetch.py`
11. `list_videos_api.py`
12. `list_videos_yt_dlp.py`
13. `local_file_lister.py`
14. `multi_model_whisper.py`
15. `proxy_manager.py`
16. `segment_optimizer.py`
17. `segments_database.py`

### Speaker & Transcription (5 files)
18. `simple_diarization.py`
19. `speaker_utils.py`
20. `transcript_common.py`
21. `transcript_fetch.py`
22. `voice_enrollment_optimized.py`

**Total: 22 active files** (down from 37)

---

## Benefits

1. **Clearer dependency chain** - Easy to see what's actually used
2. **Faster development** - No confusion about which version to use
3. **Easier maintenance** - Only maintain active code
4. **Better IDE performance** - Fewer files to index
5. **Reduced confusion** - One clear path for each functionality

---

## Validation

After cleanup, verify the main script still works:
```bash
python backend/scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 5 --voices-dir ./voices
```

If successful, the cleanup is safe.
