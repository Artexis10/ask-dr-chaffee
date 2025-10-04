#!/usr/bin/env python3

import os
import sys
sys.path.append('backend')
import logging

# Set up logging to see more details
logging.basicConfig(level=logging.DEBUG)

def test_single_video():
    print("Testing single video with Enhanced ASR...")
    
    try:
        from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
        
        # Initialize the fetcher with speaker ID enabled
        fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=True,
            voices_dir="backend/voices",
            chaffee_min_sim=0.82
        )
        
        print(f"Fetcher initialized with speaker ID: {fetcher.enable_speaker_id}")
        
        # Test with a short video ID
        video_id = "3zW8BG4wYt0"  # The video we processed before
        
        print(f"Processing video: {video_id}")
        print("Calling fetch_transcript_with_speaker_id with force_enhanced_asr=True...")
        
        segments, method, metadata = fetcher.fetch_transcript_with_speaker_id(
            video_id,
            force_enhanced_asr=True,
            cleanup_audio=True
        )
        
        print(f"\nResults:")
        print(f"  Method: {method}")
        print(f"  Segments: {len(segments) if segments else 0}")
        print(f"  Metadata keys: {list(metadata.keys()) if metadata else 'None'}")
        
        if metadata:
            print(f"  Enhanced ASR used: {metadata.get('enhanced_asr_used', False)}")
            print(f"  Speaker identification: {metadata.get('speaker_identification', False)}")
            print(f"  Chaffee percentage: {metadata.get('chaffee_percentage', 'N/A')}")
            print(f"  Speaker distribution: {metadata.get('speaker_distribution', 'N/A')}")
        
        if segments and metadata.get('enhanced_asr_used'):
            print("\nSUCCESS: Enhanced ASR with speaker ID worked!")
            return True
        else:
            print("\nFAILED: Enhanced ASR was not used or failed")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("TESTING SINGLE VIDEO WITH ENHANCED ASR")
    print("=" * 50)
    
    success = test_single_video()
    
    print("\n" + "=" * 50)
    if success:
        print("SUCCESS: Enhanced ASR with speaker ID is working!")
    else:
        print("FAILED: Enhanced ASR with speaker ID needs fixing")
