#!/usr/bin/env python3
"""
Direct test of the monologue fast-path with the centroid-based profile
"""
import os
import sys
import logging
import numpy as np
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

# Import the fixed voice enrollment
sys.path.insert(0, os.path.dirname(__file__))
from voice_enrollment_fixed import VoiceEnrollment

def test_direct_fastpath():
    """Direct test of the monologue fast-path with the centroid-based profile"""
    try:
        # Import necessary modules
        from backend.scripts.common.downloader import create_downloader
        
        # Create downloader
        downloader = create_downloader()
        
        # Initialize voice enrollment
        voices_dir = os.getenv('VOICES_DIR', 'voices')
        enrollment = VoiceEnrollment(voices_dir=voices_dir)
        
        # Load Chaffee profile
        chaffee_profile = enrollment.load_profile("chaffee")
        if not chaffee_profile:
            logger.error("Failed to load Chaffee profile")
            return False
            
        # Check if it's a centroid-based profile
        has_centroid = 'centroid' in chaffee_profile
        logger.info(f"Profile has centroid: {has_centroid}")
        
        if has_centroid:
            logger.info(f"Centroid length: {len(chaffee_profile['centroid'])}")
        
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
        
        # Extract embeddings from audio
        logger.info("Extracting embeddings from audio")
        embeddings = enrollment._extract_embeddings_from_audio(str(audio_path))
        
        if not embeddings:
            logger.error("No embeddings extracted from audio")
            return False
            
        logger.info(f"Extracted {len(embeddings)} embeddings from audio")
        
        # Test first few embeddings
        test_embeddings = embeddings[:5]  # Test first 25 seconds
        similarities = []
        
        # Compare each test embedding with the Chaffee profile
        for emb in test_embeddings:
            try:
                # Use the improved compute_similarity that handles profiles directly
                sim = enrollment.compute_similarity(emb, chaffee_profile)
                logger.info(f"Similarity: {sim:.4f}")
                
                # Ensure it's a valid float
                sim_float = float(sim)
                if not np.isnan(sim_float) and not np.isinf(sim_float):
                    similarities.append(sim_float)
            except Exception as e:
                logger.error(f"Error computing similarity: {e}")
                continue
                
        # If we couldn't get any valid similarities, use fallback
        if not similarities:
            logger.error("No valid similarities computed")
            return False
            
        # Use a more lenient threshold for centroid-based profiles
        # since they tend to be more accurate
        threshold_multiplier = 0.9 if has_centroid else 0.8
        
        avg_similarity = float(np.mean(similarities))  # Ensure scalar value
        # Use LOWER threshold for fast-path to catch more solo content
        # More lenient for centroid-based profiles since they're more accurate
        chaffee_min_sim = 0.62  # Default threshold
        threshold = max(chaffee_min_sim * threshold_multiplier, 
                       chaffee_min_sim - (0.03 if has_centroid else 0.05))
        
        logger.info(f"Fast-path check: avg_sim={avg_similarity:.3f}, threshold={threshold:.3f}")
        
        # Check if similarity is above threshold
        is_above_threshold = avg_similarity >= threshold
        
        if is_above_threshold:
            logger.info("✅ Fast-path triggered - identified as Chaffee monologue")
            return True
        else:
            logger.info("❌ Fast-path rejected - not identified as Chaffee monologue")
            return False
        
    except Exception as e:
        logger.error(f"Error testing direct fast-path: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_direct_fastpath()
