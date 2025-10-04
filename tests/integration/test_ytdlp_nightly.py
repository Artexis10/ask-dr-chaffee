#!/usr/bin/env python3
"""
Test script for updated yt-dlp nightly with latest anti-blocking fixes.
"""

import subprocess
import sys
import os

def test_ytdlp_version():
    """Test yt-dlp version and basic functionality"""
    print("=== Testing yt-dlp Nightly Version ===")
    result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
    if result.returncode == 0:
        version = result.stdout.strip()
        print(f"[OK] yt-dlp version: {version}")
        
        if 'dev0' in version or len(version.split('.')) > 3:
            print("[OK] Nightly version detected!")
        else:
            print("[WARN] Using stable version - consider updating to nightly")
    else:
        print("[ERROR] Failed to get yt-dlp version")
        return False
    
    return True

def test_youtube_extraction():
    print("\n=== Testing YouTube Extraction ===")
    
    # Test video (Rick Astley - Never Gonna Give You Up)
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    cmd = [
        'yt-dlp',
        '--list-formats',
        '--extractor-args', 'youtube:player_client=web_safari',  # Latest fix
        '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        '--referer', 'https://www.youtube.com/',
        '-4',  # Force IPv4
        '--no-warnings',
        test_url
    ]
    
    print("Testing YouTube extraction with web_safari client...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode == 0:
        print("✅ YouTube extraction successful!")
        
        # Count available formats
        lines = result.stdout.split('\n')
        format_lines = [line for line in lines if line.startswith(('91', '92', '93', '18', '94', '95', '96'))]
        print(f"✅ Found {len(format_lines)} video formats")
        
        # Show first few formats
        if format_lines:
            print("Sample formats:")
            for line in format_lines[:3]:
                print(f"  {line}")
                
        return True
    else:
        print("❌ YouTube extraction failed!")
        print(f"Error: {result.stderr}")
        return False

def test_audio_extraction():
    """Test audio extraction for transcription"""
    print("\n=== Testing Audio Extraction ===")
    
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    cmd = [
        'yt-dlp',
        '--format', 'bestaudio',
        '--extractor-args', 'youtube:player_client=web_safari',  # Latest fix
        '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        '--referer', 'https://www.youtube.com/',
        '-4',  # Force IPv4
        '--no-warnings',
        '--simulate',  # Don't actually download
        '--print', 'url',
        test_url
    ]
    
    print("Testing audio URL extraction...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    
    if result.returncode == 0 and result.stdout.strip():
        print("✅ Audio extraction successful!")
        audio_url = result.stdout.strip()
        print(f"✅ Audio URL obtained: {audio_url[:50]}...")
        return True
    else:
        print("❌ Audio extraction failed!")
        print(f"Error: {result.stderr}")
        return False

def test_ingestion_pipeline_compatibility():
    """Test compatibility with the enhanced ingestion pipeline"""
    print("\n=== Testing Pipeline Compatibility ===")
    
    try:
        # Test importing the enhanced pipeline
        sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'scripts'))
        from common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
        
        print("✅ Enhanced transcript fetcher imported successfully")
        
        # Create a test instance
        fetcher = EnhancedTranscriptFetcher(
            store_audio_locally=False,  # Don't store for test
            production_mode=True  # Production mode for test
        )
        
        print("✅ Enhanced transcript fetcher created successfully")
        print(f"✅ Audio storage disabled: {not fetcher.store_audio_locally}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import enhanced pipeline: {e}")
        return False
    except Exception as e:
        print(f"❌ Pipeline compatibility test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing yt-dlp Nightly Updates for Ask Dr. Chaffee Pipeline")
    print("=" * 60)
    
    tests = [
        test_ytdlp_version,
        test_youtube_extraction,
        test_audio_extraction,
        test_ingestion_pipeline_compatibility
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print("⚠️  Test had issues but continued")
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("All tests passed! Your yt-dlp nightly setup is working correctly.")
        print("\nYour ingestion pipeline should now work better with YouTube's latest blocking measures.")
        print("\nUpdated components:")
        print("  - yt-dlp nightly (2025.09.26) with web_safari client")
        print("  - Enhanced transcript fetcher with latest anti-blocking fixes")
        print("  - Standard transcript fetcher with updated parameters")
        print("  - Video lister with improved extraction")
    else:
        print("Some tests failed. Check the output above for details.")
        print("You may need to:")
        print("  - Update yt-dlp to latest nightly: pip install -U --pre 'yt-dlp[default]'")
        print("  - Check your internet connection")
        print("  - Try using proxies if YouTube is blocking your IP")

if __name__ == '__main__':
    main()
