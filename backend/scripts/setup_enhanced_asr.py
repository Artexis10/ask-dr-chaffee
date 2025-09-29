#!/usr/bin/env python3
"""
Setup script for Enhanced ASR system
Helps users get started with voice enrollment and system configuration
"""

import os
import sys
import logging
from pathlib import Path

def setup_logging():
    """Setup logging for setup script"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )

def check_dependencies():
    """Check if all required dependencies are installed"""
    print("🔍 Checking dependencies...")
    
    missing_deps = []
    optional_deps = []
    
    # Core dependencies
    try:
        import faster_whisper
        print("  ✅ faster-whisper")
    except ImportError:
        missing_deps.append("faster-whisper")
        print("  ❌ faster-whisper")
    
    try:
        import librosa
        print("  ✅ librosa")
    except ImportError:
        missing_deps.append("librosa")
        print("  ❌ librosa")
    
    try:
        import soundfile
        print("  ✅ soundfile")
    except ImportError:
        missing_deps.append("soundfile")
        print("  ❌ soundfile")
    
    # Enhanced ASR dependencies
    try:
        import speechbrain
        print("  ✅ speechbrain")
    except ImportError:
        missing_deps.append("speechbrain")
        print("  ❌ speechbrain")
    
    try:
        import whisperx
        print("  ✅ whisperx")
    except ImportError:
        optional_deps.append("whisperx")
        print("  ⚠️  whisperx (optional - for word alignment)")
    
    try:
        import pyannote.audio
        print("  ✅ pyannote.audio")
    except ImportError:
        missing_deps.append("pyannote.audio")
        print("  ❌ pyannote.audio")
    
    if missing_deps:
        print(f"\n❌ Missing required dependencies: {', '.join(missing_deps)}")
        print("Install with: pip install " + " ".join(missing_deps))
        return False
    
    if optional_deps:
        print(f"\n⚠️  Optional dependencies missing: {', '.join(optional_deps)}")
        print("Install with: pip install " + " ".join(optional_deps))
    
    print("\n✅ All required dependencies are installed!")
    return True

def setup_directories():
    """Create necessary directories"""
    print("\n📁 Setting up directories...")
    
    voices_dir = Path("voices")
    voices_dir.mkdir(exist_ok=True)
    print(f"  ✅ Created voices directory: {voices_dir.absolute()}")
    
    docs_dir = Path("backend/docs")
    docs_dir.mkdir(exist_ok=True, parents=True)
    print(f"  ✅ Ensured docs directory: {docs_dir.absolute()}")
    
    return str(voices_dir)

def check_gpu_support():
    """Check GPU support for models"""
    print("\n🖥️  Checking GPU support...")
    
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"  ✅ CUDA GPU available: {gpu_name} ({gpu_memory:.1f}GB)")
            return True
        else:
            print("  ⚠️  No CUDA GPU detected - will use CPU (slower)")
            return False
    except ImportError:
        print("  ❌ PyTorch not found")
        return False

def setup_environment_file():
    """Create example environment configuration"""
    print("\n⚙️  Setting up environment configuration...")
    
    env_example = """# Enhanced ASR Configuration
# Copy to .env and customize as needed

# Speaker Identification Thresholds
CHAFFEE_MIN_SIM=0.82
GUEST_MIN_SIM=0.82
ATTR_MARGIN=0.05
OVERLAP_BONUS=0.03

# Processing Options
ASSUME_MONOLOGUE=true
ALIGN_WORDS=true
UNKNOWN_LABEL=Unknown

# Models
WHISPER_MODEL=base.en
VOICES_DIR=voices

# Enable Enhanced ASR for ingestion
ENABLE_SPEAKER_ID=true

# HuggingFace token for pyannote models (required)
# Get from: https://huggingface.co/settings/tokens
# HF_TOKEN=your_token_here

# YouTube API (optional, for enrollment from videos)
# YOUTUBE_API_KEY=your_api_key_here

# FFmpeg path (if not in PATH)
# FFMPEG_PATH=/usr/local/bin/ffmpeg
"""
    
    env_path = Path(".env.example")
    with open(env_path, 'w') as f:
        f.write(env_example)
    
    print(f"  ✅ Created example environment file: {env_path.absolute()}")
    print("  💡 Copy to '.env' and customize with your settings")

def create_example_scripts():
    """Create example usage scripts"""
    print("\n📝 Creating example scripts...")
    
    # Quick start script
    quick_start = """#!/usr/bin/env python3
# Quick start example for Enhanced ASR

import sys
sys.path.append('backend/scripts')

from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
from backend.scripts.common.enhanced_asr import EnhancedASR

# 1. Enroll Dr. Chaffee (replace with actual audio file)
print("1. Enrolling Dr. Chaffee...")
enrollment = VoiceEnrollment()
# profile = enrollment.enroll_speaker(
#     name="Chaffee",
#     audio_sources=["path/to/chaffee_audio.wav"],
#     min_duration=30.0
# )

# 2. Transcribe with speaker ID
print("2. Transcribing with speaker identification...")
asr = EnhancedASR()
# result = asr.transcribe_with_speaker_id("path/to/interview.wav")
# print(f"Result: {len(result.segments)} segments with speaker attribution")
"""
    
    Path("examples").mkdir(exist_ok=True)
    with open("examples/quick_start.py", 'w') as f:
        f.write(quick_start)
    
    print("  ✅ Created examples/quick_start.py")

def run_basic_test():
    """Run a basic system test"""
    print("\n🧪 Running basic system test...")
    
    try:
        # Test voice enrollment system
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        enrollment = VoiceEnrollment()
        print("  ✅ Voice enrollment system loaded")
        
        # Test Enhanced ASR config
        from backend.scripts.common.enhanced_asr import EnhancedASRConfig
        config = EnhancedASRConfig()
        print("  ✅ Enhanced ASR configuration loaded")
        
        # Test output formatters
        from backend.scripts.common.asr_output_formats import ASROutputFormatter
        formatter = ASROutputFormatter()
        print("  ✅ Output formatters loaded")
        
        print("\n✅ Basic system test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Basic system test failed: {e}")
        return False

def main():
    """Main setup routine"""
    print("🎤 Enhanced ASR System Setup")
    print("=" * 40)
    
    setup_logging()
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Setup failed - install missing dependencies first")
        return 1
    
    # Setup directories
    voices_dir = setup_directories()
    
    # Check GPU
    has_gpu = check_gpu_support()
    
    # Setup environment
    setup_environment_file()
    
    # Create examples
    create_example_scripts()
    
    # Run basic test
    if not run_basic_test():
        print("\n⚠️  Setup completed with warnings - system test failed")
        return 1
    
    # Final instructions
    print("\n🎉 Enhanced ASR System Setup Complete!")
    print("\nNext Steps:")
    print("1. Set up HuggingFace token for pyannote models:")
    print("   - Get token: https://huggingface.co/settings/tokens")
    print("   - Accept license: https://huggingface.co/pyannote/speaker-diarization-3.1")
    print("   - Add to .env: HF_TOKEN=your_token_here")
    print()
    print("2. Enroll Dr. Chaffee's voice:")
    print("   python asr_cli.py enroll --name Chaffee --audio chaffee_samples.wav")
    print()
    print("3. Test transcription:")
    print("   python asr_cli.py transcribe test_audio.wav --output results.json")
    print()
    print("4. View documentation:")
    print("   backend/docs/ENHANCED_ASR.md")
    
    if has_gpu:
        print("\n🚀 GPU acceleration available - expect fast processing!")
    else:
        print("\n🐌 CPU-only mode - consider GPU for faster processing")
    
    return 0

if __name__ == '__main__':
    exit(main())
