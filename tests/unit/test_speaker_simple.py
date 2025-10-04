#!/usr/bin/env python3

import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_speaker_identification():
    """Test if speaker identification components are working"""
    try:
        print("Testing Dr. Chaffee profile...")
        from backend.scripts.common.voice_enrollment import VoiceEnrollment
        
        enrollment = VoiceEnrollment(voices_dir="backend/voices")
        profiles = enrollment.list_profiles()
        print(f"Available profiles: {profiles}")
        
        if 'chaffee' not in [p.lower() for p in profiles]:
            print("ERROR: Dr. Chaffee's profile not found!")
            return False
        
        print("SUCCESS: Dr. Chaffee's profile found")
        
        # Test loading the profile
        chaffee_profile = enrollment.load_profile("chaffee")
        if chaffee_profile is not None:
            print("SUCCESS: Dr. Chaffee's profile loaded")
            print(f"Profile shape: {chaffee_profile.shape if hasattr(chaffee_profile, 'shape') else 'Unknown'}")
        else:
            print("ERROR: Failed to load Dr. Chaffee's profile")
            return False
        
        # Test audio embedding extraction with a simple test
        print("\nTesting audio embedding extraction...")
        try:
            import numpy as np
            import tempfile
            import soundfile as sf
            
            # Generate 1 second of test audio
            sample_rate = 16000
            t = np.linspace(0, 1, sample_rate, False)
            audio_data = 0.1 * np.sin(2 * np.pi * 440.0 * t)
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                sf.write(tmp_file.name, audio_data, sample_rate)
                
                print(f"Testing with audio file: {tmp_file.name}")
                embeddings = enrollment._extract_embeddings_from_audio(tmp_file.name)
                
                if embeddings and len(embeddings) > 0:
                    print(f"SUCCESS: Extracted {len(embeddings)} embeddings")
                    
                    # Test similarity
                    sim = enrollment.compute_similarity(embeddings[0], chaffee_profile)
                    print(f"SUCCESS: Similarity computation: {sim:.3f}")
                    
                    os.unlink(tmp_file.name)
                    return True
                else:
                    print("ERROR: No embeddings extracted")
                    os.unlink(tmp_file.name)
                    return False
                    
        except Exception as e:
            print(f"ERROR in audio processing: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    except Exception as e:
        print(f"ERROR in speaker identification: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("TESTING SPEAKER IDENTIFICATION")
    print("=" * 50)
    
    success = test_speaker_identification()
    
    print("=" * 50)
    if success:
        print("SUCCESS: Speaker identification working!")
    else:
        print("FAILED: Speaker identification has issues")
