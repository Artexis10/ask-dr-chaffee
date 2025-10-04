#!/usr/bin/env python3

import os
import sys
sys.path.append('backend')

def test_enhanced_asr_flow():
    print("Testing Enhanced ASR Flow...")
    
    try:
        from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
        
        # Initialize the fetcher with speaker ID enabled
        fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=True,
            voices_dir="backend/voices",
            chaffee_min_sim=0.82
        )
        
        print(f"OK: EnhancedTranscriptFetcher initialized")
        print(f"  enable_speaker_id: {fetcher.enable_speaker_id}")
        print(f"  voices_dir: {fetcher.voices_dir}")
        
        # Test the conditions that determine if Enhanced ASR should be used
        print("\n--- Testing Enhanced ASR conditions ---")
        
        # Check speaker profiles
        profiles_available = fetcher._check_speaker_profiles_available()
        print(f"Speaker profiles available: {profiles_available}")
        
        # Test with force_enhanced_asr = True
        force_enhanced_asr = True
        use_enhanced_asr = (
            fetcher.enable_speaker_id and 
            (force_enhanced_asr or profiles_available)
        )
        print(f"use_enhanced_asr (with force=True): {use_enhanced_asr}")
        
        # Test Enhanced ASR initialization
        if use_enhanced_asr:
            enhanced_asr = fetcher._get_enhanced_asr()
            print(f"Enhanced ASR initialized: {enhanced_asr is not None}")
            
            if enhanced_asr:
                print("SUCCESS: Enhanced ASR should be triggered!")
                return True
            else:
                print("ERROR: Enhanced ASR failed to initialize")
                return False
        else:
            print("ERROR: Enhanced ASR conditions not met")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("TESTING ENHANCED ASR FLOW")
    print("=" * 40)
    
    success = test_enhanced_asr_flow()
    
    print("\n" + "=" * 40)
    if success:
        print("SUCCESS: Enhanced ASR flow should work!")
    else:
        print("FAILED: Enhanced ASR flow has issues")
