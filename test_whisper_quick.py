#!/usr/bin/env python3
import sys
import os
sys.path.append('backend/scripts')

from common.transcript_fetch import TranscriptFetcher, WHISPER_AVAILABLE

print("="*50)
print("WHISPER TRANSCRIPTION TEST")
print("="*50)

print(f"Whisper available: {WHISPER_AVAILABLE}")

if WHISPER_AVAILABLE:
    print("Testing Whisper transcription (this may take 1-2 minutes)...")
    
    try:
        fetcher = TranscriptFetcher()
        # Use a very short video to minimize processing time
        video_id = "dQw4w9WgXcQ"  # Rick Roll - short segment test
        
        segments, method, metadata = fetcher.fetch_transcript(
            video_id, 
            force_whisper=True, 
            max_duration_s=30  # Very short for testing
        )
        
        if segments and len(segments) > 0:
            print("SUCCESS!")
            print(f"Method: {method}")
            print(f"Segments: {len(segments)}")
            print(f"Sample text: {segments[0].text}")
            print(f"Model used: {metadata.get('model', 'Unknown')}")
            if 'quality_assessment' in metadata:
                quality = metadata['quality_assessment']
                print(f"Quality score: {quality.get('score', 'N/A')}")
        else:
            print("FAILED to generate transcript")
            print(f"Method: {method}")
            print(f"Error: {metadata.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"ERROR during Whisper test: {str(e)}")
        
else:
    print("Whisper not available - install with: pip install faster-whisper")
    print("This would be needed for videos without YouTube captions")

print("="*50)
