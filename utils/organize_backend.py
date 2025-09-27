#!/usr/bin/env python3
"""
Backend cleanup and organization script for Ask Dr. Chaffee project.
Moves files to appropriate directories for better project structure.
"""

import os
import shutil
from pathlib import Path

# Define the root directory
ROOT_DIR = Path(__file__).parent

def create_directories():
    """Create necessary directories for organization"""
    directories = [
        "tests/unit",
        "tests/integration", 
        "tests/performance",
        "tests/enhanced_asr",
        "utils/database",
        "utils/monitoring",
        "utils/debug",
        "utils/analysis",
        "backend/scripts/legacy",
        "backend/scripts/experimental"
    ]
    
    for dir_path in directories:
        (ROOT_DIR / dir_path).mkdir(parents=True, exist_ok=True)
        print(f"* Created directory: {dir_path}")

def move_test_files():
    """Move test files to appropriate test directories"""
    
    # Unit tests (small, focused tests)
    unit_tests = [
        "test_embedding_model.py",
        "test_segmentation.py", 
        "test_similarity_directly.py",
        "test_speaker_simple.py",
        "test_db_insert.py",
        "test_hf_access.py",
        "test_hf_download.py",
        "test_huggingface_auth.py",
        "test_gated_access.py"
    ]
    
    # Integration tests (full pipeline tests)
    integration_tests = [
        "test_production_connection.py",
        "test_mvp_pipeline.py",
        "test_rag_frontend.py",
        "test_rag_retrieval.py",
        "test_search.py",
        "test_search_api.py",
        "test_real_youtube_audio.py",
        "test_single_video.py",
        "test_videos.py",
        "test_audio_quality.py",
        "test_audio_storage.py",
        "test_distil_ingestion.py",
        "test_yt_dlp_transcript.py",
        "test_ytdlp_nightly.py"
    ]
    
    # Performance tests  
    performance_tests = [
        "test_speed_comparison.py",
        "test_whisper_quick.py",
        "test_async_bulk_download.py",
        "test_enhanced_asr_batch.py"
    ]
    
    # Enhanced ASR tests
    enhanced_asr_tests = [
        "test_enhanced_asr_flow.py",
        "test_enhanced_prompts.py",
        "test_speaker_id_scenarios.py",
        "test_gpu_asr.py",
        "test_monologue_mode.py",
        "test_pyannote_direct.py",
        "test_pyannote_hardcoded.py",
        "test_pyannote_v2.py",
        "test_whisperx_diarization.py",
        "test_whisperx_diarization_updated.py"
    ]
    
    # Move files to appropriate directories
    file_mappings = [
        (unit_tests, "tests/unit"),
        (integration_tests, "tests/integration"),
        (performance_tests, "tests/performance"), 
        (enhanced_asr_tests, "tests/enhanced_asr")
    ]
    
    for file_list, target_dir in file_mappings:
        for filename in file_list:
            source = ROOT_DIR / filename
            if source.exists():
                target = ROOT_DIR / target_dir / filename
                shutil.move(str(source), str(target))
                print(f"* Moved {filename} -> {target_dir}/")

def move_utility_files():
    """Move utility and analysis files to utils directory"""
    
    # Database utilities
    database_utils = [
        "analyze_db_fields.py",
        "check_chunks.py",
        "check_db.py",
        "check_db_schema.py",
        "check_schema.py",
        "check_source_metadata.py",
        "check_speaker_data.py",
        "check_speaker_metadata.py",
        "database_cleanup_migration.py",
        "reset_database.py",
        "apply_migration.py"
    ]
    
    # Monitoring utilities
    monitoring_utils = [
        "check_ingestion_progress.py",
        "check_stuck_videos.py", 
        "monitor_gpu_direct.py",
        "monitor_gpu_ingestion.py",
        "monitor_ingestion_db.py",
        "monitor_test.py",
        "generate_report.py"
    ]
    
    # Debug utilities
    debug_utils = [
        "debug_audio_simple.py",
        "debug_embedding_extraction.py",
        "debug_embeddings.py",
        "debug_enhanced_asr_detailed.py",
        "debug_enhanced_asr_speakers.py",
        "debug_speaker_id.py",
        "debug_speaker_id_detailed.py",
        "debug_speaker_profiles.py"
    ]
    
    # Analysis utilities
    analysis_utils = [
        "check_pure_results.py",
        "full_chunk_analysis_3GlEPRo5yjY.py",
        "analyze_segments.py"
    ]
    
    # Move files to appropriate utils subdirectories
    utils_mappings = [
        (database_utils, "utils/database"),
        (monitoring_utils, "utils/monitoring"),
        (debug_utils, "utils/debug"),
        (analysis_utils, "utils/analysis")
    ]
    
    for file_list, target_dir in utils_mappings:
        for filename in file_list:
            source = ROOT_DIR / filename
            if source.exists():
                target = ROOT_DIR / target_dir / filename
                shutil.move(str(source), str(target))
                print(f"* Moved {filename} -> {target_dir}/")

def organize_backend_scripts():
    """Organize backend scripts by moving less-used ones to subdirectories"""
    
    backend_scripts_dir = ROOT_DIR / "backend" / "scripts"
    
    # Legacy/deprecated scripts
    legacy_scripts = [
        "ingest_youtube.py",  # Replaced by enhanced version
        "ingest_youtube_optimized.py",  # Old optimization
        "ingest_youtube_robust.py",  # Old robust version
        "ingest_youtube_robust_optimized.py",  # Old version
        "ingest_youtube_true_parallel.py",  # Experimental
        "ingest_youtube_with_speaker_id.py",  # Replaced by enhanced_asr version
        "parallel_whisper_worker.py",  # Old parallel implementation
        "parallel_whisper_worker_fixed.py"  # Old version
    ]
    
    # Experimental scripts
    experimental_scripts = [
        "ingest_youtube_maximum_gpu.py",
        "hybrid_orchestrator.py",
        "parallel_ingestion_orchestrator.py",
        "cloud_whisper_worker.py",
        "cloud_daily_ingestion.py"
    ]
    
    # Move legacy scripts
    for script in legacy_scripts:
        source = backend_scripts_dir / script
        if source.exists():
            target = backend_scripts_dir / "legacy" / script
            shutil.move(str(source), str(target))
            print(f"* Moved {script} -> backend/scripts/legacy/")
    
    # Move experimental scripts
    for script in experimental_scripts:
        source = backend_scripts_dir / script
        if source.exists():
            target = backend_scripts_dir / "experimental" / script
            shutil.move(str(source), str(target))
            print(f"* Moved {script} -> backend/scripts/experimental/")

def create_init_files():
    """Create __init__.py files for Python packages"""
    init_dirs = [
        "tests",
        "tests/unit",
        "tests/integration", 
        "tests/performance",
        "tests/enhanced_asr",
        "utils",
        "utils/database",
        "utils/monitoring",
        "utils/debug",
        "utils/analysis"
    ]
    
    for dir_path in init_dirs:
        init_file = ROOT_DIR / dir_path / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# Package initialization file\n")
            print(f"* Created __init__.py in {dir_path}")

def clean_root_directory():
    """Remove remaining clutter from root directory"""
    
    # Files that can be moved to utils or removed
    files_to_clean = [
        "check_dotenv.py",
        "check_env.py", 
        "check_env_in_test.py",
        "download_model.py",
        "download_model_explicit.py",
        "fix_chaffee_threshold.py",
        "speed_test_simple.py"
    ]
    
    for filename in files_to_clean:
        source = ROOT_DIR / filename
        if source.exists():
            # Move to utils/debug
            target = ROOT_DIR / "utils" / "debug" / filename
            shutil.move(str(source), str(target))
            print(f"* Moved {filename} -> utils/debug/")

def main():
    """Main organization function"""
    print("Starting backend cleanup and organization...")
    print()
    
    # Create directory structure
    print("Creating directory structure...")
    create_directories()
    print()
    
    # Move test files
    print("Organizing test files...")
    move_test_files()
    print()
    
    # Move utility files  
    print("Organizing utility files...")
    move_utility_files()
    print()
    
    # Organize backend scripts
    print("Organizing backend scripts...")
    organize_backend_scripts()
    print()
    
    # Create __init__.py files
    print("Creating package initialization files...")
    create_init_files()
    print()
    
    # Clean root directory
    print("Cleaning root directory...")
    clean_root_directory()
    print()
    
    print("Backend cleanup and organization complete!")
    print()
    print("New structure:")
    print("- tests/")
    print("  - unit/           # Small, focused tests")
    print("  - integration/    # Full pipeline tests")
    print("  - performance/    # Speed and load tests")
    print("  - enhanced_asr/   # ASR-specific tests")
    print("- utils/")
    print("  - database/       # Database utilities")
    print("  - monitoring/     # Monitoring tools")
    print("  - debug/          # Debug utilities")
    print("  - analysis/       # Analysis tools")
    print("- backend/scripts/")
    print("  - legacy/         # Deprecated scripts")
    print("  - experimental/   # Experimental scripts")

if __name__ == "__main__":
    main()
