#!/usr/bin/env python3
"""
Direct test of the centroid-based profile
"""
import os
import sys
import json
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

def compute_similarity(embedding1, embedding2):
    """Compute cosine similarity between two embeddings"""
    # Ensure both embeddings are numpy arrays with the same dtype
    if isinstance(embedding1, list):
        embedding1 = np.array(embedding1, dtype=np.float64)
    if isinstance(embedding2, list):
        embedding2 = np.array(embedding2, dtype=np.float64)
        
    # Convert to float64 to avoid type mismatch
    embedding1 = embedding1.astype(np.float64)
    embedding2 = embedding2.astype(np.float64)
    
    # Ensure embeddings are flattened
    embedding1 = embedding1.flatten()
    embedding2 = embedding2.flatten()
    
    # Ensure embeddings have the same length
    min_len = min(len(embedding1), len(embedding2))
    if min_len == 0:
        return 0.0
        
    embedding1 = embedding1[:min_len]
    embedding2 = embedding2[:min_len]
    
    # Manual cosine similarity calculation
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
        
    # Compute dot product and divide by norms
    dot_product = np.dot(embedding1, embedding2)
    similarity = dot_product / (norm1 * norm2)
    
    # Ensure it's a native Python float
    return float(similarity)

def test_centroid_direct():
    """Direct test of the centroid-based profile"""
    try:
        # Load the Chaffee profile
        profile_path = os.path.join('voices', 'chaffee.json')
        with open(profile_path, 'r') as f:
            chaffee_profile = json.load(f)
            
        # Check if it's a centroid-based profile
        has_centroid = 'centroid' in chaffee_profile
        logger.info(f"Profile has centroid: {has_centroid}")
        
        if has_centroid:
            logger.info(f"Centroid length: {len(chaffee_profile['centroid'])}")
            
            # Create test embeddings
            # 1. Random embedding
            random_embedding = np.random.normal(0, 1, (len(chaffee_profile['centroid']),))
            random_embedding = random_embedding / np.linalg.norm(random_embedding)
            
            # 2. Similar embedding (90% centroid, 10% random)
            similar_embedding = np.array(chaffee_profile['centroid']) * 0.9 + np.random.normal(0, 0.1, (len(chaffee_profile['centroid']),))
            similar_embedding = similar_embedding / np.linalg.norm(similar_embedding)
            
            # 3. Very similar embedding (99% centroid, 1% random)
            very_similar_embedding = np.array(chaffee_profile['centroid']) * 0.99 + np.random.normal(0, 0.01, (len(chaffee_profile['centroid']),))
            very_similar_embedding = very_similar_embedding / np.linalg.norm(very_similar_embedding)
            
            # Compute similarities
            random_similarity = compute_similarity(random_embedding, chaffee_profile['centroid'])
            similar_similarity = compute_similarity(similar_embedding, chaffee_profile['centroid'])
            very_similar_similarity = compute_similarity(very_similar_embedding, chaffee_profile['centroid'])
            
            logger.info(f"Random embedding similarity: {random_similarity:.4f}")
            logger.info(f"Similar embedding similarity: {similar_similarity:.4f}")
            logger.info(f"Very similar embedding similarity: {very_similar_similarity:.4f}")
            
            # Check against threshold
            threshold = 0.62  # Default threshold
            logger.info(f"Threshold: {threshold:.4f}")
            
            logger.info(f"Random embedding above threshold: {random_similarity >= threshold}")
            logger.info(f"Similar embedding above threshold: {similar_similarity >= threshold}")
            logger.info(f"Very similar embedding above threshold: {very_similar_similarity >= threshold}")
            
            return True
        else:
            logger.error("Profile does not have a centroid")
            return False
        
    except Exception as e:
        logger.error(f"Error testing centroid direct: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_centroid_direct()
