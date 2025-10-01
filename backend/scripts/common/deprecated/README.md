# Deprecated Modules

This directory contains deprecated modules that are no longer used by the active ingestion pipeline (`ingest_youtube_enhanced.py`).

**These files are kept for reference only and can be safely deleted when confirmed they are not needed.**

## Files Moved to Deprecated (2025-10-01)

### Voice Enrollment Duplicates
- `voice_enrollment.py` - Old version, replaced by `voice_enrollment_optimized.py`
- `voice_enrollment_fixed.py` - Intermediate fix, superseded
- `voice_enrollment_new.py` - Experimental version, not used
- `voice_storage.py` - Unused storage abstraction

### Transcript Processing Duplicates
- `transcript_api.py` - Legacy API wrapper
- `transcript_processor.py` - Old processing logic
- `transcript_service_production.py` - Unused production service
- `transcripts.py` - Legacy transcript handling

### UTF-8 Fix Duplicates
- `simple_utf8_fix.py` - Superseded by fixes in main files
- `ultimate_utf8_fix.py` - Experimental, not used

### Other Deprecated Modules
- `simple_diarization-deprecated.py` - Already marked deprecated
- `async_downloader.py` - Not used by enhanced pipeline
- `whisper_parallel.py` - Replaced by `multi_model_whisper.py`
- `monitoring.py` - Unused monitoring utilities
- `reranker.py` - Not used in current pipeline

## Active Modules (Still in Use)

See `backend/scripts/README.md` for the list of active modules used by `ingest_youtube_enhanced.py`.

## When to Delete

These files can be deleted when:
1. The main ingestion pipeline has been running successfully for several weeks
2. No other scripts reference these modules
3. You've confirmed you don't need them for reference

**Recommendation:** Keep for 30 days, then delete if no issues arise.
