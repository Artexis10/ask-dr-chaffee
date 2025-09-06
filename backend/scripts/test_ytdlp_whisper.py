#!/usr/bin/env python3
"""
Test yt-dlp + Whisper pipeline for hosted environments
"""

import os
import sys
import tempfile
import subprocess
import logging
from pathlib import Path

# Add parent directory to path for imports  
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_ytdlp_installation():
    """Test if yt-dlp is properly installed and working"""
    try:
        result = subprocess.run(['yt-dlp', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info(f"✅ yt-dlp version: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"❌ yt-dlp failed: {result.stderr}")
            return False
    except FileNotFoundError:
        logger.error("❌ yt-dlp not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        logger.error("❌ yt-dlp version check timed out")
        return False

def test_ffmpeg_installation():
    """Test if ffmpeg is properly installed"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            logger.info(f"✅ {version_line}")
            return True
        else:
            logger.error(f"❌ ffmpeg failed: {result.stderr}")
            return False
    except FileNotFoundError:
        logger.error("❌ ffmpeg not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        logger.error("❌ ffmpeg version check timed out")
        return False

def test_whisper_import():
    """Test if faster-whisper can be imported"""
    try:
        import faster_whisper
        logger.info(f"✅ faster-whisper imported successfully")
        return True
    except ImportError as e:
        logger.error(f"❌ faster-whisper import failed: {e}")
        return False

def test_audio_download(video_id="1-Jhm9njwKA", max_duration=60):
    """Test downloading audio with yt-dlp"""
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / f"{video_id}.%(ext)s"
            
            cmd = [
                'yt-dlp',
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '0',  # Best quality
                '--no-playlist',
                '--max-duration', str(max_duration),
                '-o', str(output_path),
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            
            logger.info(f"Testing audio download for video {video_id}...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                # Check if audio file was created
                audio_files = list(Path(temp_dir).glob(f"{video_id}.*"))
                if audio_files:
                    audio_file = audio_files[0]
                    size_mb = audio_file.stat().st_size / (1024 * 1024)
                    logger.info(f"✅ Audio download successful: {audio_file.name} ({size_mb:.1f} MB)")
                    return True, str(audio_file)
                else:
                    logger.error("❌ Audio file not found after download")
                    return False, None
            else:
                logger.error(f"❌ yt-dlp download failed: {result.stderr}")
                return False, None
                
    except subprocess.TimeoutExpired:
        logger.error("❌ Audio download timed out")
        return False, None
    except Exception as e:
        logger.error(f"❌ Audio download error: {e}")
        return False, None

def test_whisper_transcription(audio_path, model="tiny"):
    """Test Whisper transcription on audio file"""
    try:
        import faster_whisper
        
        logger.info(f"Loading Whisper model: {model}")
        whisper_model = faster_whisper.WhisperModel(
            model, 
            device="cpu",
            compute_type="int8"
        )
        
        logger.info(f"Transcribing audio: {Path(audio_path).name}")
        segments, info = whisper_model.transcribe(
            audio_path,
            beam_size=5,
            language="en"
        )
        
        segment_list = list(segments)
        
        if segment_list:
            total_text = ' '.join([seg.text.strip() for seg in segment_list])
            logger.info(f"✅ Whisper transcription successful:")
            logger.info(f"   Language: {info.language}")
            logger.info(f"   Segments: {len(segment_list)}")
            logger.info(f"   Sample text: {total_text[:100]}...")
            return True
        else:
            logger.error("❌ No transcription segments generated")
            return False
            
    except Exception as e:
        logger.error(f"❌ Whisper transcription failed: {e}")
        return False

def test_full_pipeline(video_id="1-Jhm9njwKA"):
    """Test complete yt-dlp + Whisper pipeline"""
    logger.info("=" * 60)
    logger.info("TESTING COMPLETE YT-DLP + WHISPER PIPELINE")
    logger.info("=" * 60)
    
    # Test 1: Component availability
    logger.info("\n1. Testing component availability...")
    ytdlp_ok = test_ytdlp_installation()
    ffmpeg_ok = test_ffmpeg_installation()
    whisper_ok = test_whisper_import()
    
    if not all([ytdlp_ok, ffmpeg_ok, whisper_ok]):
        logger.error("❌ Missing required components")
        return False
    
    # Test 2: Audio download
    logger.info("\n2. Testing audio download...")
    download_ok, audio_path = test_audio_download(video_id)
    
    if not download_ok:
        logger.error("❌ Audio download failed")
        return False
    
    # Test 3: Whisper transcription
    logger.info("\n3. Testing Whisper transcription...")
    transcribe_ok = test_whisper_transcription(audio_path)
    
    if not transcribe_ok:
        logger.error("❌ Whisper transcription failed")
        return False
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ COMPLETE PIPELINE TEST SUCCESSFUL!")
    logger.info("✅ yt-dlp + Whisper ready for hosted deployment")
    logger.info("=" * 60)
    
    return True

def main():
    """Main test function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test yt-dlp + Whisper pipeline')
    parser.add_argument('--video-id', default='1-Jhm9njwKA', 
                       help='YouTube video ID to test with')
    parser.add_argument('--components-only', action='store_true',
                       help='Test only component availability')
    
    args = parser.parse_args()
    
    if args.components_only:
        logger.info("Testing component availability only...")
        ytdlp_ok = test_ytdlp_installation()
        ffmpeg_ok = test_ffmpeg_installation()
        whisper_ok = test_whisper_import()
        
        if all([ytdlp_ok, ffmpeg_ok, whisper_ok]):
            logger.info("✅ All components available")
            return 0
        else:
            logger.error("❌ Missing components")
            return 1
    else:
        success = test_full_pipeline(args.video_id)
        return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
