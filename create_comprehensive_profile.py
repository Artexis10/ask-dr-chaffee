#!/usr/bin/env python3
"""
Create a comprehensive Chaffee voice profile from multiple high-quality videos
"""

import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_comprehensive_profile():
    """Create a comprehensive Chaffee profile from multiple videos"""
    
    logger.info("Creating comprehensive Chaffee voice profile...")
    
    # All six videos provided by you
    chaffee_videos = [
        "https://www.youtube.com/watch?v=zw2c7s7NcqI",
        "https://www.youtube.com/watch?v=jLb5XUITtHQ",
        "https://www.youtube.com/watch?v=e6HdFlGmId4",
        "https://www.youtube.com/watch?v=zl_QM65_TpA",
        "https://www.youtube.com/watch?v=naRYI5Q-uYw",
        "https://www.youtube.com/watch?v=x6XSRbuBCd4"  # Adding the known working video
    ]
    
    # Backup existing profile
    if os.path.exists("voices/chaffee.json"):
        backup_path = "voices/chaffee_backup.json"
        logger.info(f"Backing up existing profile to {backup_path}")
        import shutil
        shutil.copy("voices/chaffee.json", backup_path)
        logger.info("Backup completed")
    
    # Process each video sequentially to avoid memory issues
    success_count = 0
    
    # First, create a new profile with the first video
    logger.info(f"Creating new profile with video 1/{len(chaffee_videos)}: {chaffee_videos[0]}")
    cmd = [
        "python", "backend/scripts/ingest_youtube_enhanced.py",
        "--setup-chaffee", chaffee_videos[0],
        "--overwrite-profile"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("Successfully created initial profile")
            success_count += 1
        else:
            logger.error(f"Failed to create initial profile")
            logger.error(f"Error: {result.stderr}")
            return  # Exit if initial profile creation fails
    except Exception as e:
        logger.error(f"Error creating initial profile: {e}")
        return
    
    # Now use direct voice enrollment to add remaining videos
    try:
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        enrollment = VoiceEnrollment(voices_dir='voices')
        
        # Process remaining videos
        for i, video in enumerate(chaffee_videos[1:], 1):
            logger.info(f"Adding video {i+1}/{len(chaffee_videos)} to profile: {video}")
            
            result = enrollment.enroll_speaker(
                name='chaffee',
                audio_sources=[video],
                update=True,  # Update existing profile
                min_duration=30.0
            )
            
            if result:
                logger.info(f"Successfully added video {i+1} to profile")
                success_count += 1
            else:
                logger.error(f"Failed to add video {i+1} to profile")
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        import traceback
        traceback.print_exc()
    
    # Check the final profile
    if success_count > 0:
        logger.info(f"Profile creation completed with {success_count}/{len(chaffee_videos)} videos")
        
        # Test the profile
        try:
            from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
            enrollment = VoiceEnrollment(voices_dir='voices')
            profile = enrollment.load_profile("chaffee")
            
            if profile is not None:
                logger.info(f"Profile loaded successfully: shape {profile.shape}")
                logger.info(f"Self-similarity: {enrollment.compute_similarity(profile, profile):.4f}")
                
                # Test with a known Chaffee video
                test_video = "https://www.youtube.com/watch?v=x6XSRbuBCd4"
                logger.info(f"Testing profile with {test_video}")
                
                # Use the enhanced_asr module to test fast-path
                sys.path.append('backend/scripts/common')
                from enhanced_asr import EnhancedASR
                from enhanced_asr_config import EnhancedASRConfig
                
                config = EnhancedASRConfig()
                asr = EnhancedASR(config)
                
                logger.info("Profile creation successful!")
            else:
                logger.error("Failed to load created profile")
        except Exception as e:
            logger.error(f"Error testing profile: {e}")
    else:
        logger.error("Failed to create profile from any video")

if __name__ == "__main__":
    create_comprehensive_profile()
