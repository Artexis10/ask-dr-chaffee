#!/usr/bin/env python3
"""
Test voice similarity calculation directly
"""
import os
import sys
import json
import logging
import numpy as np
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_similarity():
    """Test voice similarity calculation directly"""
    try:
        # Import voice enrollment
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        
        # Create voice enrollment
        enrollment = VoiceEnrollment(voices_dir='voices')
        
        # Load Chaffee profile
        profile = enrollment.load_profile('chaffee')
        if not profile:
            logger.error("Failed to load Chaffee profile")
            return False
            
        logger.info(f"Profile keys: {list(profile.keys())}")
        
        # Check if profile has centroid
        has_centroid = 'centroid' in profile
        logger.info(f"Profile has centroid: {has_centroid}")
        
        if has_centroid:
            logger.info(f"Centroid length: {len(profile['centroid'])}")
            
        # Create test embeddings
        # 1. Random embedding (should have low similarity)
        random_embedding = np.random.normal(0, 1, (192,))
        random_embedding = random_embedding / np.linalg.norm(random_embedding)
        
        # 2. Similar embedding (if we have a centroid)
        if has_centroid:
            similar_embedding = np.array(profile['centroid']) * 0.9 + np.random.normal(0, 0.1, (len(profile['centroid']),))
            similar_embedding = similar_embedding / np.linalg.norm(similar_embedding)
        else:
            similar_embedding = random_embedding
            
        # 3. Very similar embedding (if we have a centroid)
        if has_centroid:
            very_similar_embedding = np.array(profile['centroid']) * 0.95 + np.random.normal(0, 0.05, (len(profile['centroid']),))
            very_similar_embedding = very_similar_embedding / np.linalg.norm(very_similar_embedding)
        else:
            very_similar_embedding = random_embedding
        
        # Test similarity calculation
        random_sim = enrollment.compute_similarity(random_embedding, profile)
        similar_sim = enrollment.compute_similarity(similar_embedding, profile)
        very_similar_sim = enrollment.compute_similarity(very_similar_embedding, profile)
        
        logger.info(f"Random similarity: {random_sim:.4f}")
        logger.info(f"Similar similarity: {similar_sim:.4f}")
        logger.info(f"Very similar similarity: {very_similar_sim:.4f}")
        
        # Test with real audio
        audio_dir = Path("audio_storage")
        if audio_dir.exists():
            # Find a Chaffee video
            chaffee_video = "x6XSRbuBCd4.wav"  # 100% Chaffee
            chaffee_path = audio_dir / chaffee_video
            
            if chaffee_path.exists():
                logger.info(f"Testing with Chaffee audio: {chaffee_path}")
                
                # Extract embeddings
                embeddings = enrollment._extract_embeddings_from_audio(str(chaffee_path))
                logger.info(f"Extracted {len(embeddings)} embeddings")
                
                if embeddings:
                    # Calculate similarity for each embedding
                    similarities = [enrollment.compute_similarity(emb, profile) for emb in embeddings]
                    
                    # Calculate statistics
                    avg_sim = np.mean(similarities)
                    max_sim = np.max(similarities)
                    min_sim = np.min(similarities)
                    
                    logger.info(f"Average similarity: {avg_sim:.4f}")
                    logger.info(f"Max similarity: {max_sim:.4f}")
                    logger.info(f"Min similarity: {min_sim:.4f}")
                    
                    # Count embeddings above threshold
                    threshold = 0.62  # Default Chaffee threshold
                    above_threshold = sum(1 for sim in similarities if sim >= threshold)
                    percentage = (above_threshold / len(similarities)) * 100
                    
                    logger.info(f"Embeddings above threshold ({threshold}): {above_threshold}/{len(similarities)} ({percentage:.1f}%)")
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing similarity: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_similarity()
