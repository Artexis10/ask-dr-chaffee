#!/usr/bin/env python3
"""
Create a centroid-based voice profile for Dr. Chaffee
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

def create_centroid_profile():
    """Create a centroid-based voice profile for Dr. Chaffee"""
    try:
        # Import voice enrollment
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        
        # Create voice enrollment
        voices_dir = Path(os.getenv('VOICES_DIR', 'voices'))
        enrollment = VoiceEnrollment(voices_dir=str(voices_dir))
        
        # Backup existing profile
        profile_path = voices_dir / "chaffee.json"
        backup_path = voices_dir / "chaffee_backup_before_centroid.json"
        
        if profile_path.exists():
            import shutil
            shutil.copy(profile_path, backup_path)
            logger.info(f"Backed up existing profile to {backup_path}")
            
        # Use the existing profile as a starting point
        old_profile = enrollment.load_profile("chaffee")
        if not old_profile:
            logger.error("Failed to load existing profile")
            return False
            
        logger.info(f"Loaded existing profile with keys: {list(old_profile.keys())}")
        
        # Check if we already have a centroid
        if 'centroid' in old_profile:
            logger.info("Profile already has a centroid")
            centroid = old_profile['centroid']
        elif 'embeddings' in old_profile:
            # Create a centroid from the embeddings
            logger.info(f"Creating centroid from {len(old_profile['embeddings'])} embeddings")
            embeddings = np.array(old_profile['embeddings'])
            centroid = np.mean(embeddings, axis=0).tolist()
        else:
            logger.error("Profile doesn't have embeddings or centroid")
            return False
            
        # Create a new profile with the centroid
        new_profile = {
            'name': old_profile.get('name', 'chaffee'),
            'centroid': centroid,
            'embeddings': old_profile.get('embeddings', []),
            'threshold': old_profile.get('threshold', 0.62),
            'created_at': old_profile.get('created_at', '2025-09-29T17:00:00'),
            'metadata': {
                'source': 'centroid_conversion',
                'num_embeddings': len(old_profile.get('embeddings', [])),
                'original_profile': os.path.basename(profile_path)
            }
        }
        
        # Save the new profile
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(new_profile, f, indent=2)
            
        logger.info(f"Created centroid-based profile at {profile_path}")
        
        # Test the profile
        test_embeddings = enrollment._extract_embeddings_from_audio("audio_storage/x6XSRbuBCd4.wav")
        
        if test_embeddings:
            # Calculate similarity for each embedding
            similarities = [enrollment.compute_similarity(emb, new_profile) for emb in test_embeddings]
            
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
        logger.error(f"Error creating centroid profile: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    create_centroid_profile()
