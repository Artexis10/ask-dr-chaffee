#!/usr/bin/env python3
"""
Test the monologue fast-path with the centroid-based profile
"""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_monologue_fastpath():
    """Test the monologue fast-path with the centroid-based profile"""
    try:
        # Import necessary modules
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from voice_enrollment_fixed import VoiceEnrollment
        
        # Monkey patch the voice_enrollment_optimized module
        import backend.scripts.common.voice_enrollment_optimized
        backend.scripts.common.voice_enrollment_optimized.VoiceEnrollment = VoiceEnrollment
        
        # Now import the enhanced ASR modules
        from backend.scripts.common.enhanced_asr import EnhancedASR
        from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig
        from backend.scripts.common.downloader import create_downloader
        
        # Create downloader
        downloader = create_downloader()
        
        # Create ASR config with monologue assumption enabled
        config = EnhancedASRConfig(
            overrides={
                'chaffee_min_sim': '0.62',
                'guest_min_sim': '0.82',
                'attr_margin': '0.05',
                'assume_monologue': 'true'  # Enable monologue assumption
            }
        )
        
        # Create Enhanced ASR
        asr = EnhancedASR(config)
        
        # Define test video - use a monologue video
        video_id = "tk3jYFzgJDQ"  # This should be a Dr. Chaffee monologue
        
        # Download audio if needed
        audio_dir = Path("audio_storage")
        audio_dir.mkdir(exist_ok=True)
        
        audio_path = audio_dir / f"{video_id}.wav"
        if not audio_path.exists():
            logger.info(f"Downloading audio for {video_id}")
            downloaded_path = downloader.download_audio(video_id)
            
            # Copy to audio_storage
            import shutil
            shutil.copy(downloaded_path, audio_path)
            
        logger.info(f"Using audio file: {audio_path}")
        
        # Test monologue fast-path
        logger.info("Testing monologue fast-path")
        result = asr._check_monologue_fast_path(str(audio_path))
        
        if result:
            logger.info("✅ Fast-path triggered - identified as Chaffee monologue")
            return True
        else:
            logger.info("❌ Fast-path rejected - not identified as Chaffee monologue")
            return False
        
    except Exception as e:
        logger.error(f"Error testing monologue fast-path: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_monologue_fastpath()
