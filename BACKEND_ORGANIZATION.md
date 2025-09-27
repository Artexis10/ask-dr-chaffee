# Backend Organization Guide

This document describes the cleaned-up backend structure for the Ask Dr. Chaffee project. The organization improves maintainability, reduces mistakes, and makes the codebase easier to navigate.

## Directory Structure

```
ask-dr-chaffee/
├── backend/
│   ├── scripts/
│   │   ├── common/           # Shared utilities and libraries
│   │   ├── legacy/           # Deprecated scripts (kept for reference)
│   │   ├── experimental/     # Experimental scripts and prototypes
│   │   └── [active scripts]  # Current production scripts
│   ├── api/                  # API service code
│   ├── docs/                 # Backend-specific documentation
│   └── requirements.txt      # Python dependencies
├── tests/
│   ├── unit/                 # Small, focused unit tests
│   ├── integration/          # Full pipeline integration tests
│   ├── performance/          # Speed and load tests
│   └── enhanced_asr/         # Enhanced ASR specific tests
├── utils/
│   ├── database/             # Database utilities and migrations
│   ├── monitoring/           # Monitoring and status checking tools
│   ├── debug/                # Debug utilities and troubleshooting tools
│   └── analysis/             # Analysis and reporting tools
└── [project files]          # Configuration, documentation, etc.
```

## Active Scripts (backend/scripts/)

### Primary Ingestion Scripts
- `ingest_youtube_enhanced.py` - Main ingestion pipeline with tiered transcript fetching
- `ingest_youtube_enhanced_asr.py` - Enhanced ASR ingestion with speaker identification
- `batch_ingestion.py` - Batch processing coordinator
- `ingest_to_production.py` - Production deployment ingestion

### ASR & Voice Processing
- `asr_cli.py` - Enhanced ASR command-line interface
- `setup_enhanced_asr.py` - Enhanced ASR system setup
- `test_enhanced_asr.py` - Enhanced ASR system testing

### Specialized Ingestion
- `ingest_zoom.py` - Zoom recording ingestion
- `get_channel_videos.py` - Channel video discovery
- `process_srt_files.py` - SRT file processing

### Services
- `rag_api_service.py` - RAG API service
- `monitor_ingestion.py` - Ingestion monitoring service

## Common Libraries (backend/scripts/common/)

### Core Infrastructure
- `database.py` - Database connection and utilities
- `database_upsert.py` - Database upsert operations
- `segments_database.py` - Segment-specific database operations

### Transcript Processing
- `transcript_fetch.py` - Main transcript fetching with tiered approach
- `enhanced_transcript_fetch.py` - Enhanced transcript fetching with local file support
- `transcript_api.py` - YouTube Data API transcript fetching
- `transcript_processor.py` - Transcript processing utilities
- `transcripts.py` - Legacy transcript utilities

### Enhanced ASR System
- `enhanced_asr.py` - Core Enhanced ASR engine
- `enhanced_asr_config.py` - Enhanced ASR configuration
- `voice_enrollment.py` - Voice profile enrollment system
- `asr_output_formats.py` - ASR output formatting
- `speaker_utils.py` - Speaker identification utilities
- `simple_diarization.py` - Simple speaker diarization

### Video Discovery & Download
- `list_videos_api.py` - YouTube Data API video discovery
- `list_videos_yt_dlp.py` - yt-dlp video discovery
- `local_file_lister.py` - Local file discovery and processing
- `downloader.py` - Video/audio downloading
- `async_downloader.py` - Asynchronous downloading

### Processing & Analysis
- `embeddings.py` - Text embedding generation
- `segment_optimizer.py` - Segment optimization
- `reranker.py` - Search result reranking
- `monitoring.py` - System monitoring utilities

### External Integrations
- `proxy_manager.py` - Proxy management for external APIs
- `whisper_parallel.py` - Parallel Whisper processing
- `multi_model_whisper.py` - Multi-model Whisper coordination

## Legacy Scripts (backend/scripts/legacy/)

These scripts are deprecated but kept for reference:
- `ingest_youtube.py` - Original ingestion script
- `ingest_youtube_optimized.py` - Early optimization attempt
- `ingest_youtube_robust.py` - Early robustness improvements
- `ingest_youtube_robust_optimized.py` - Combined early improvements
- `ingest_youtube_true_parallel.py` - Early parallelization attempt
- `ingest_youtube_with_speaker_id.py` - Early speaker ID integration
- `parallel_whisper_worker.py` - Original parallel worker
- `parallel_whisper_worker_fixed.py` - Fixed parallel worker

## Experimental Scripts (backend/scripts/experimental/)

Work-in-progress and experimental features:
- `ingest_youtube_maximum_gpu.py` - Maximum GPU utilization experiments
- `hybrid_orchestrator.py` - Hybrid processing orchestration
- `parallel_ingestion_orchestrator.py` - Advanced parallel processing
- `cloud_whisper_worker.py` - Cloud-based Whisper processing
- `cloud_daily_ingestion.py` - Cloud daily ingestion system

## Test Organization

### Unit Tests (tests/unit/)
Small, focused tests for individual components:
- `test_embedding_model.py` - Embedding model tests
- `test_segmentation.py` - Segmentation logic tests
- `test_similarity_directly.py` - Similarity computation tests
- `test_speaker_simple.py` - Basic speaker identification tests
- `test_db_insert.py` - Database insertion tests

### Integration Tests (tests/integration/)
Full pipeline and system integration tests:
- `test_production_connection.py` - Production system connectivity
- `test_mvp_pipeline.py` - MVP pipeline end-to-end tests
- `test_rag_frontend.py` - RAG frontend integration
- `test_search.py` - Search functionality tests
- `test_real_youtube_audio.py` - Real YouTube audio processing
- `test_audio_quality.py` - Audio quality validation

### Performance Tests (tests/performance/)
Speed, load, and performance validation:
- `test_speed_comparison.py` - Processing speed comparisons
- `test_whisper_quick.py` - Whisper performance tests
- `test_async_bulk_download.py` - Bulk download performance
- `test_enhanced_asr_batch.py` - Enhanced ASR batch performance

### Enhanced ASR Tests (tests/enhanced_asr/)
Specialized tests for Enhanced ASR functionality:
- `test_enhanced_asr_flow.py` - Enhanced ASR workflow tests
- `test_speaker_id_scenarios.py` - Speaker identification scenarios
- `test_gpu_asr.py` - GPU-accelerated ASR tests
- `test_pyannote_direct.py` - PyAnnote integration tests
- `test_whisperx_diarization.py` - WhisperX diarization tests

## Utilities Organization

### Database Utilities (utils/database/)
Database management and analysis tools:
- `analyze_db_fields.py` - Database field usage analysis
- `check_*.py` - Various database integrity checks
- `database_cleanup_migration.py` - Database cleanup operations
- `reset_database.py` - Database reset utilities

### Monitoring Tools (utils/monitoring/)
System monitoring and status checking:
- `check_ingestion_progress.py` - Ingestion progress monitoring
- `monitor_*.py` - Various system monitoring tools
- `generate_report.py` - Report generation

### Debug Utilities (utils/debug/)
Debugging and troubleshooting tools:
- `debug_*.py` - Various debugging utilities
- `check_env*.py` - Environment checking tools
- `download_model*.py` - Model download utilities

### Analysis Tools (utils/analysis/)
Data analysis and reporting:
- `check_pure_results.py` - Result purity analysis
- `full_chunk_analysis_*.py` - Detailed chunk analysis
- `analyze_segments.py` - Segment analysis

## Usage Guidelines

### Running Tests
```bash
# Unit tests
python -m pytest tests/unit/ -v

# Integration tests  
python -m pytest tests/integration/ -v

# Performance tests
python -m pytest tests/performance/ -v

# Enhanced ASR tests
python -m pytest tests/enhanced_asr/ -v
```

### Using Utilities
```bash
# Database analysis
python utils/database/analyze_db_fields.py

# Monitor ingestion
python utils/monitoring/check_ingestion_progress.py

# Debug issues
python utils/debug/debug_enhanced_asr_detailed.py
```

### Active Development
Focus development on scripts in:
- `backend/scripts/` (main directory)
- `backend/scripts/common/` (shared libraries)

Avoid modifying files in:
- `backend/scripts/legacy/` (deprecated)
- `backend/scripts/experimental/` (unstable)

## Benefits of Organization

### 1. Reduced Mistakes
- Clear separation of active vs deprecated code
- Organized test suites prevent testing wrong versions
- Utilities are easy to find and don't clutter main directories

### 2. Easier Navigation
- Logical grouping by functionality
- Clear naming conventions
- Comprehensive documentation

### 3. Better Maintenance
- Easy identification of what's currently used
- Simplified dependency management
- Clear upgrade paths

### 4. Improved Development Workflow
- Focused test execution
- Easy debugging with organized utilities
- Clear separation of concerns

## Migration Notes

All file moves preserve git history. If you have local changes in moved files, update your paths accordingly:

```bash
# Old location -> New location examples:
test_enhanced_asr_flow.py -> tests/enhanced_asr/test_enhanced_asr_flow.py
debug_speaker_id.py -> utils/debug/debug_speaker_id.py  
check_db.py -> utils/database/check_db.py
ingest_youtube.py -> backend/scripts/legacy/ingest_youtube.py
```

## Future Improvements

1. **Documentation**: Add README files to each utils subdirectory
2. **Testing**: Implement automated test discovery and execution
3. **Monitoring**: Enhanced monitoring dashboard using utils/monitoring tools
4. **CI/CD**: Automated testing pipeline using organized test structure
5. **Packaging**: Consider packaging common utilities as installable modules
