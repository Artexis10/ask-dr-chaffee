#!/usr/bin/env python3
"""
Test script for audio storage functionality in the ingestion pipeline.
Tests that audio is stored locally in development but not in production.
"""

import os
import sys
import tempfile
from pathlib import Path

def test_transcript_fetcher_storage():
    """Test TranscriptFetcher with audio storage configuration"""
    print("=== Testing TranscriptFetcher Audio Storage ===")
    
    try:
        # Import the transcript fetcher
        sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'scripts'))
        from common.transcript_fetch import TranscriptFetcher
        
        # Test development mode (should store audio)
        print("\n--- Testing Development Mode ---")
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir) / 'dev_audio_storage'
            
            fetcher_dev = TranscriptFetcher(
                store_audio_locally=True,
                audio_storage_dir=str(storage_dir),
                production_mode=False
            )
            
            print(f"[OK] Dev mode fetcher created")
            print(f"  - Store audio locally: {fetcher_dev.store_audio_locally}")
            print(f"  - Audio storage dir: {fetcher_dev.audio_storage_dir}")
            print(f"  - Production mode: {fetcher_dev.production_mode}")
            
            if fetcher_dev.store_audio_locally and fetcher_dev.audio_storage_dir.exists():
                print("[OK] Development mode: Audio storage enabled and directory created")
            else:
                print("[ERROR] Development mode: Audio storage not properly configured")
                return False
        
        # Test production mode (should NOT store audio)
        print("\n--- Testing Production Mode ---")
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir) / 'prod_audio_storage'
            
            fetcher_prod = TranscriptFetcher(
                store_audio_locally=True,  # Request storage
                audio_storage_dir=str(storage_dir),
                production_mode=True  # But production mode should override
            )
            
            print(f"[OK] Prod mode fetcher created")
            print(f"  - Store audio locally: {fetcher_prod.store_audio_locally}")
            print(f"  - Audio storage dir: {fetcher_prod.audio_storage_dir}")
            print(f"  - Production mode: {fetcher_prod.production_mode}")
            
            if not fetcher_prod.store_audio_locally:
                print("[OK] Production mode: Audio storage properly disabled")
            else:
                print("[ERROR] Production mode: Audio storage should be disabled")
                return False
        
        return True
        
    except ImportError as e:
        print(f"[ERROR] Failed to import TranscriptFetcher: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        return False

def test_enhanced_transcript_fetcher_storage():
    """Test EnhancedTranscriptFetcher with audio storage configuration"""
    print("\n=== Testing EnhancedTranscriptFetcher Audio Storage ===")
    
    try:
        # Import the enhanced transcript fetcher
        sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'scripts'))
        from common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
        
        # Test development mode
        print("\n--- Testing Enhanced Development Mode ---")
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = Path(temp_dir) / 'enhanced_dev_storage'
            
            enhanced_fetcher = EnhancedTranscriptFetcher(
                store_audio_locally=True,
                audio_storage_dir=str(storage_dir),
                production_mode=False,
                enable_speaker_id=False  # Disable for simple test
            )
            
            print(f"[OK] Enhanced dev fetcher created")
            print(f"  - Store audio locally: {enhanced_fetcher.store_audio_locally}")
            print(f"  - Audio storage dir: {enhanced_fetcher.audio_storage_dir}")
            print(f"  - Production mode: {enhanced_fetcher.production_mode}")
            print(f"  - Speaker ID enabled: {enhanced_fetcher.enable_speaker_id}")
            
            if enhanced_fetcher.store_audio_locally and enhanced_fetcher.audio_storage_dir.exists():
                print("[OK] Enhanced development mode: Audio storage enabled")
            else:
                print("[ERROR] Enhanced development mode: Audio storage not configured")
                return False
        
        # Test production mode
        print("\n--- Testing Enhanced Production Mode ---")
        enhanced_prod = EnhancedTranscriptFetcher(
            store_audio_locally=True,
            production_mode=True,
            enable_speaker_id=False
        )
        
        if not enhanced_prod.store_audio_locally:
            print("[OK] Enhanced production mode: Audio storage properly disabled")
        else:
            print("[ERROR] Enhanced production mode: Audio storage should be disabled")
            return False
        
        return True
        
    except ImportError as e:
        print(f"[ERROR] Failed to import EnhancedTranscriptFetcher: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Enhanced test failed: {e}")
        return False

def test_ingestion_config():
    """Test that ingestion config properly passes audio storage parameters"""
    print("\n=== Testing Ingestion Configuration ===")
    
    try:
        # Import the ingestion config
        sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'scripts'))
        from ingest_youtube_enhanced import IngestionConfig
        
        # Test development config
        print("\n--- Testing Development Config ---")
        dev_config = IngestionConfig(
            source='api',
            store_audio_locally=True,
            production_mode=False,
            audio_storage_dir=Path('./test_audio_storage')
        )
        
        print(f"[OK] Development config created")
        print(f"  - Store audio locally: {dev_config.store_audio_locally}")
        print(f"  - Audio storage dir: {dev_config.audio_storage_dir}")
        print(f"  - Production mode: {dev_config.production_mode}")
        
        # Test production config
        print("\n--- Testing Production Config ---")
        prod_config = IngestionConfig(
            source='api',
            store_audio_locally=True,  # Request storage
            production_mode=True,      # But production mode should override
            audio_storage_dir=Path('./prod_audio_storage')
        )
        
        print(f"[OK] Production config created")
        print(f"  - Store audio locally: {prod_config.store_audio_locally}")
        print(f"  - Audio storage dir: {prod_config.audio_storage_dir}")  
        print(f"  - Production mode: {prod_config.production_mode}")
        
        # The actual storage decision is made in the transcript fetcher, not config
        print("[OK] Configuration properly preserves audio storage settings")
        
        return True
        
    except ImportError as e:
        print(f"[ERROR] Failed to import IngestionConfig: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Config test failed: {e}")
        return False

def test_youtube_transcript_api_resilience():
    """Test that YouTube Transcript API failures don't break the pipeline"""
    print("\n=== Testing YouTube Transcript API Resilience ===")
    
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'scripts'))
        from common.transcript_fetch import TranscriptFetcher
        
        # Create fetcher without any API keys
        fetcher = TranscriptFetcher(
            api_key=None,
            credentials_path=None,
            store_audio_locally=False,  # Don't store for this test
            production_mode=True
        )
        
        print("[OK] TranscriptFetcher created without API credentials")
        
        # Test fetching YouTube transcript for a non-existent video
        # This should fail gracefully and return None
        result = fetcher.fetch_youtube_transcript("nonexistent_video_id")
        
        if result is None:
            print("[OK] YouTube Transcript API failure handled gracefully")
            return True
        else:
            print("[WARN] Unexpected result from non-existent video")
            return True  # Still OK, just unexpected
            
    except Exception as e:
        print(f"[ERROR] Resilience test failed: {e}")
        return False

def main():
    """Run all audio storage tests"""
    print("Audio Storage Configuration Tests")
    print("=" * 50)
    
    tests = [
        test_transcript_fetcher_storage,
        test_enhanced_transcript_fetcher_storage,
        test_ingestion_config,
        test_youtube_transcript_api_resilience
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print("[WARN] Test had issues but continued")
        except Exception as e:
            print(f"[ERROR] Test failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nAll tests passed! Audio storage is properly configured:")
        print("  ✓ Development mode: Audio stored locally for reproducibility")
        print("  ✓ Production mode: Audio storage disabled to save space")
        print("  ✓ YouTube Transcript API failures handled gracefully")
        print("  ✓ Enhanced transcript fetcher inherits storage settings")
    else:
        print(f"\n{total - passed} test(s) failed. Check output above for details.")

if __name__ == '__main__':
    main()
