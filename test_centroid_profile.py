#!/usr/bin/env python3
"""
Test the voice enrollment system with the centroid-based profile
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

def test_centroid_profile():
    """Test the voice enrollment system with the centroid-based profile"""
    try:
        # Import necessary modules
        # Use the fixed implementation instead of the broken one
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from voice_enrollment_fixed import VoiceEnrollment
        import numpy as np
        
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
            
        # Create a test embedding
        test_embedding = np.random.normal(0, 1, (192,))
        test_embedding = test_embedding / np.linalg.norm(test_embedding)
        
        # Compute similarity
        similarity = enrollment.compute_similarity(test_embedding, chaffee_profile)
        logger.info(f"Similarity with Chaffee: {similarity:.4f}")
        
        # Test with a more similar embedding
        if has_centroid:
            # Create an embedding that's more similar to the centroid
            similar_embedding = np.array(chaffee_profile['centroid']) * 0.9 + np.random.normal(0, 0.1, (len(chaffee_profile['centroid']),))
            similar_embedding = similar_embedding / np.linalg.norm(similar_embedding)
            
            # Compute similarity
            similar_similarity = enrollment.compute_similarity(similar_embedding, chaffee_profile)
            logger.info(f"Similarity with more similar embedding: {similar_similarity:.4f}")
            
            # This should be higher than the random embedding
            logger.info(f"Improvement: {similar_similarity - similarity:.4f}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing centroid profile: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_centroid_profile()
