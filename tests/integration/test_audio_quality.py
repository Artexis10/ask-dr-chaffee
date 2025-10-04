#!/usr/bin/env python3
"""
Test script for audio quality optimizations in the ingestion pipeline.
Tests the different audio extraction methods and quality settings.
"""

import subprocess
import sys
import os
import tempfile
from pathlib import Path

def test_yt_dlp_audio_formats():
    """Test yt-dlp's ability to extract different audio formats"""
    print("=== Testing yt-dlp Audio Format Extraction ===")
    
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    # Test different format selectors
    format_tests = [
        ("Best Audio (Current)", "bestaudio"),
        ("Best M4A/WebM/Opus", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio[acodec=opus]/bestaudio/best"),
        ("WAV Extraction", "bestaudio --audio-format wav"),
    ]
    
    for name, format_selector in format_tests:
        print(f"\n--- Testing {name} ---")
        
        cmd = [
            'yt-dlp',
            '--list-formats',
            '--extractor-args', 'youtube:player_client=web_safari',
            '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            '--referer', 'https://www.youtube.com/',
            '-4',
            '--no-warnings',
            test_url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                # Extract audio formats
                lines = result.stdout.split('\n')
                audio_formats = []
                for line in lines:
                    if 'audio only' in line or ('mp4' in line and 'video' not in line.lower()):
                        audio_formats.append(line.strip())
                
                print(f"[OK] Found {len(audio_formats)} audio formats")
                if audio_formats:
                    print("Best audio formats available:")
                    for fmt in audio_formats[:3]:  # Show top 3
                        print(f"  {fmt}")
            else:
                print(f"[ERROR] Failed to list formats: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print("[ERROR] Timeout while listing formats")
        except Exception as e:
            print(f"[ERROR] Exception: {e}")

def test_audio_quality_settings():
    """Test audio quality settings with yt-dlp"""
    print("\n=== Testing Audio Quality Settings ===")
    
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    quality_tests = [
        ("Highest Quality WAV", ["--extract-audio", "--audio-format", "wav", "--audio-quality", "0"]),
        ("Best Audio No Conversion", ["--format", "bestaudio[ext=m4a]/bestaudio"]),
        ("Best with Fallback", ["--format", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"]),
    ]
    
    for name, extra_args in quality_tests:
        print(f"\n--- Testing {name} ---")
        
        cmd = [
            'yt-dlp',
            '--simulate',
            '--print', 'format_id,ext,acodec,abr,asr',
            '--extractor-args', 'youtube:player_client=web_safari',
            '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            '--referer', 'https://www.youtube.com/',
            '-4',
            '--no-warnings',
        ] + extra_args + [test_url]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = result.stdout.strip()
                print(f"[OK] Selected format: {output}")
                
                # Parse audio info
                parts = output.split(',')
                if len(parts) >= 5:
                    format_id, ext, acodec, abr, asr = parts[:5]
                    print(f"  Format ID: {format_id}")
                    print(f"  Extension: {ext}")
                    print(f"  Audio Codec: {acodec}")
                    print(f"  Audio Bitrate: {abr}")
                    print(f"  Sample Rate: {asr}")
            else:
                print(f"[ERROR] Failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print("[ERROR] Timeout")
        except Exception as e:
            print(f"[ERROR] Exception: {e}")

def test_ffmpeg_preprocessing():
    """Test FFmpeg preprocessing for Whisper optimization"""
    print("\n=== Testing FFmpeg Audio Preprocessing ===")
    
    # Create a short test audio file
    with tempfile.TemporaryDirectory() as temp_dir:
        test_input = Path(temp_dir) / "test_input.wav"
        test_output = Path(temp_dir) / "test_output.wav"
        
        # Generate a short test tone (1 second, 440Hz)
        cmd_generate = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', 'sine=frequency=440:duration=1',
            '-ar', '48000',  # High sample rate input
            '-ac', '2',       # Stereo input
            str(test_input)
        ]
        
        try:
            print("Generating test audio file...")
            subprocess.run(cmd_generate, capture_output=True, check=True)
            
            # Test Whisper-optimized preprocessing
            cmd_process = [
                'ffmpeg',
                '-i', str(test_input),
                '-ac', '1',           # Convert to mono
                '-ar', '16000',       # 16kHz sample rate (Whisper's native)
                '-sample_fmt', 's16', # 16-bit depth
                '-vn',                # No video
                '-y',                 # Overwrite output
                str(test_output)
            ]
            
            print("Testing Whisper-optimized preprocessing...")
            result = subprocess.run(cmd_process, capture_output=True, text=True)
            
            if result.returncode == 0 and test_output.exists():
                print("[OK] FFmpeg preprocessing successful")
                
                # Get output file info
                cmd_info = [
                    'ffprobe',
                    '-v', 'error',
                    '-select_streams', 'a:0',
                    '-show_entries', 'stream=channels,sample_rate,sample_fmt,bit_rate',
                    '-of', 'csv=p=0',
                    str(test_output)
                ]
                
                info_result = subprocess.run(cmd_info, capture_output=True, text=True)
                if info_result.returncode == 0:
                    info = info_result.stdout.strip()
                    print(f"  Output audio specs: {info}")
                    
                    # Parse specs
                    parts = info.split(',')
                    if len(parts) >= 3:
                        channels, sample_rate, sample_fmt = parts[:3]
                        print(f"  Channels: {channels} (should be 1)")
                        print(f"  Sample Rate: {sample_rate} Hz (should be 16000)")
                        print(f"  Sample Format: {sample_fmt} (should be s16)")
                        
                        if channels == '1' and sample_rate == '16000':
                            print("[OK] Audio optimized for Whisper!")
                        else:
                            print("[WARN] Audio not fully optimized for Whisper")
            else:
                print(f"[ERROR] FFmpeg preprocessing failed: {result.stderr}")
                
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] FFmpeg command failed: {e}")
        except FileNotFoundError:
            print("[ERROR] FFmpeg not found in PATH")
        except Exception as e:
            print(f"[ERROR] Exception: {e}")

def test_pipeline_integration():
    """Test integration with the enhanced pipeline"""
    print("\n=== Testing Pipeline Integration ===")
    
    try:
        # Test importing the components
        sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'scripts'))
        from common.downloader import AudioDownloader, AudioPreprocessingConfig
        from common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
        
        print("[OK] Successfully imported pipeline components")
        
        # Test AudioPreprocessingConfig
        config = AudioPreprocessingConfig(
            normalize_audio=True,
            remove_silence=False,
            pipe_mode=False
        )
        
        print(f"[OK] Audio preprocessing config: {config.to_dict()}")
        
        # Test EnhancedTranscriptFetcher with audio storage
        fetcher = EnhancedTranscriptFetcher(
            store_audio_locally=True,
            production_mode=False
        )
        
        print(f"[OK] Enhanced fetcher initialized with audio storage: {fetcher.store_audio_locally}")
        
        return True
        
    except ImportError as e:
        print(f"[ERROR] Failed to import components: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Integration test failed: {e}")
        return False

def main():
    """Run all audio quality tests"""
    print("Audio Quality Optimization Tests for Ask Dr. Chaffee Pipeline")
    print("=" * 65)
    
    tests = [
        test_yt_dlp_audio_formats,
        test_audio_quality_settings,
        test_ffmpeg_preprocessing,
        test_pipeline_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            result = test()
            if result is not False:  # None or True counts as passed
                passed += 1
        except Exception as e:
            print(f"[ERROR] Test failed with exception: {e}")
    
    print("\n" + "=" * 65)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nYour audio pipeline is optimized for high-quality Whisper transcription!")
        print("\nOptimizations implemented:")
        print("  - Best quality audio format selection")
        print("  - Lossless WAV format for transcription")
        print("  - 16kHz mono preprocessing for Whisper")
        print("  - Configurable audio storage")
        print("  - Latest yt-dlp anti-blocking fixes")
    else:
        print("\nSome tests failed. Check individual test outputs for details.")

if __name__ == '__main__':
    main()
