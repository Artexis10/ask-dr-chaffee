#!/usr/bin/env python3

import os
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_similarity_directly():
    """Test similarity computation directly"""
    print("TESTING SIMILARITY COMPUTATION DIRECTLY")
    print("=" * 50)
    
    # Import voice enrollment
    from backend.scripts.common.voice_enrollment import VoiceEnrollment
    
    # Initialize voice enrollment
    enrollment = VoiceEnrollment(voices_dir="backend/voices")
    
    # Load Chaffee profile
    chaffee_profile = enrollment.load_profile("chaffee")
    
    if chaffee_profile is None:
        print("ERROR: Could not load Chaffee profile")
        return False
        
    print(f"Chaffee profile loaded: {chaffee_profile.shape}")
    
    # Create a test embedding
    test_embedding = np.random.rand(192)  # Same shape as Chaffee profile
    
    # Normalize the embedding (like in compute_similarity)
    test_embedding = test_embedding / np.linalg.norm(test_embedding)
    
    print(f"Test embedding created: {test_embedding.shape}")
    
    # Test similarity computation
    try:
        # Original method
        print("\nTesting original similarity computation:")
        sim = enrollment.compute_similarity(test_embedding, chaffee_profile)
        print(f"Similarity: {sim}")
        
        # Manual computation
        print("\nTesting manual similarity computation:")
        emb1_norm = test_embedding / np.linalg.norm(test_embedding)
        emb2_norm = chaffee_profile / np.linalg.norm(chaffee_profile)
        manual_sim = float(np.dot(emb1_norm, emb2_norm))
        print(f"Manual similarity: {manual_sim}")
        
        # Test with explicit float conversion
        print("\nTesting with explicit float conversion:")
        float_sim = float(sim)
        print(f"Float similarity: {float_sim}")
        
        # Test comparison
        print("\nTesting comparison:")
        threshold = 0.6
        print(f"Threshold: {threshold}")
        
        # Test different comparison methods
        print(f"sim > threshold: {sim > threshold}")
        print(f"float(sim) > threshold: {float(sim) > threshold}")
        print(f"sim.item() > threshold: {sim.item() > threshold}")
        
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_similarity_directly()
    print("=" * 50)
    if success:
        print("SUCCESS: Similarity computation works")
    else:
        print("FAILED: Similarity computation has issues")
