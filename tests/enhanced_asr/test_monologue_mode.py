#!/usr/bin/env python3

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_monologue_config():
    """Test monologue configuration"""
    print("TESTING MONOLOGUE CONFIGURATION")
    print("=" * 50)
    
    assume_monologue = os.getenv('ASSUME_MONOLOGUE', 'false').lower() == 'true'
    chaffee_min_sim = float(os.getenv('CHAFFEE_MIN_SIM', '0.82'))
    
    print(f"ASSUME_MONOLOGUE env var: {os.getenv('ASSUME_MONOLOGUE', 'NOT SET')}")
    print(f"assume_monologue bool: {assume_monologue}")
    print(f"CHAFFEE_MIN_SIM: {chaffee_min_sim}")
    
    # Test Enhanced ASR config
    from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig
    config = EnhancedASRConfig()
    
    print(f"\nEnhancedASR Config:")
    print(f"assume_monologue: {config.assume_monologue}")
    print(f"chaffee_min_sim: {config.chaffee_min_sim}")
    print(f"voices_dir: {config.voices_dir}")
    
    # Test voice enrollment
    from backend.scripts.common.voice_enrollment import VoiceEnrollment
    enrollment = VoiceEnrollment(voices_dir=config.voices_dir)
    
    chaffee_profile = enrollment.load_profile("chaffee")
    print(f"\nChaffee profile loaded: {chaffee_profile is not None}")
    
    if chaffee_profile is not None:
        print(f"Chaffee profile shape: {chaffee_profile.shape}")
        
        # Test monologue check manually
        from backend.scripts.common.enhanced_asr import EnhancedASR
        asr = EnhancedASR(config)
        
        print(f"\nTesting monologue fast-path logic...")
        print(f"Config assume_monologue: {asr.config.assume_monologue}")
        
        if not asr.config.assume_monologue:
            print("ERROR: assume_monologue is False - monologue fast-path disabled!")
            return False
        else:
            print("SUCCESS: assume_monologue is True - monologue fast-path enabled!")
            return True
    else:
        print("ERROR: Chaffee profile not found")
        return False

if __name__ == "__main__":
    success = test_monologue_config()
    print("=" * 50)
    if success:
        print("SUCCESS: Monologue mode should work")
    else:  
        print("FAILED: Monologue mode has issues")
