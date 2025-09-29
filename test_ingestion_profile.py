#!/usr/bin/env python3
"""
Test that the ingestion pipeline can properly load the centroid-based profile
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

def test_ingestion_profile():
    """Test that the ingestion pipeline can properly load the centroid-based profile"""
    try:
        # Import necessary modules
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        
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
            logger.info(f"Profile format: Centroid-based (superior)")
        else:
            logger.info(f"Profile format: Embeddings-based")
            if 'embeddings' in chaffee_profile:
                logger.info(f"Embeddings count: {len(chaffee_profile['embeddings'])}")
        
        # Test similarity computation with a random embedding
        import numpy as np
        test_embedding = np.random.normal(0, 1, (192,))
        test_embedding = test_embedding / np.linalg.norm(test_embedding)
        
        # Compute similarity
        similarity = enrollment.compute_similarity(test_embedding, chaffee_profile)
        logger.info(f"Similarity with random embedding: {similarity:.4f}")
        
        # Create a more similar embedding if we have a centroid
        if has_centroid:
            similar_embedding = np.array(chaffee_profile['centroid']) * 0.9 + np.random.normal(0, 0.1, (len(chaffee_profile['centroid']),))
            similar_embedding = similar_embedding / np.linalg.norm(similar_embedding)
            
            # Compute similarity
            similar_similarity = enrollment.compute_similarity(similar_embedding, chaffee_profile)
            logger.info(f"Similarity with similar embedding: {similar_similarity:.4f}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing ingestion profile: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_ingestion_profile()
