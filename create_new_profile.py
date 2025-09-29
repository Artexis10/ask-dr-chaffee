#!/usr/bin/env python3
"""
Create a new voice profile from the known Chaffee audio
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

def create_new_profile():
    """Create a new voice profile from the known Chaffee audio"""
    try:
        # Import voice enrollment
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        
        # Create voice enrollment
        enrollment = VoiceEnrollment(voices_dir='voices')
        
        # Use the known Chaffee video
        audio_dir = Path("audio_storage")
        chaffee_video = "x6XSRbuBCd4.wav"  # 100% Chaffee
        chaffee_path = audio_dir / chaffee_video
        
        if not chaffee_path.exists():
            logger.error(f"Chaffee audio not found: {chaffee_path}")
            return False
            
        logger.info(f"Creating profile from Chaffee audio: {chaffee_path}")
        
        # Extract embeddings
        embeddings = enrollment._extract_embeddings_from_audio(str(chaffee_path))
        logger.info(f"Extracted {len(embeddings)} embeddings")
        
        if not embeddings:
            logger.error("Failed to extract embeddings")
            return False
            
        # Convert embeddings to list for JSON serialization
        embeddings_list = [emb.tolist() for emb in embeddings]
        
        # Calculate centroid
        centroid = np.mean(embeddings, axis=0).tolist()
        
        # Create new profile
        new_profile = {
            'name': 'chaffee',
            'centroid': centroid,
            'embeddings': embeddings_list,
            'threshold': 0.62,
            'created_at': '2025-09-29T16:00:00',
            'audio_sources': [f"youtube:{chaffee_video.replace('.wav', '')}"],
            'metadata': {
                'source': 'direct_creation',
                'num_embeddings': len(embeddings),
                'video_id': chaffee_video.replace('.wav', '')
            }
        }
        
        # Backup existing profile
        profile_path = Path('voices/chaffee.json')
        backup_path = Path('voices/chaffee_old.json')
        
        if profile_path.exists():
            import shutil
            shutil.copy(profile_path, backup_path)
            logger.info(f"Backed up existing profile to {backup_path}")
        
        # Save new profile
        with open(profile_path, 'w') as f:
            json.dump(new_profile, f, indent=2)
            
        logger.info(f"Created new profile at {profile_path}")
        
        # Test the new profile
        profile = enrollment.load_profile('chaffee')
        if not profile:
            logger.error("Failed to load new Chaffee profile")
            return False
            
        # Extract test embeddings
        test_embeddings = enrollment._extract_embeddings_from_audio(str(chaffee_path))
        
        if test_embeddings:
            # Calculate similarity for each embedding
            similarities = [enrollment.compute_similarity(emb, profile) for emb in test_embeddings]
            
            # Calculate statistics
            avg_sim = np.mean(similarities)
            max_sim = np.max(similarities)
            min_sim = np.min(similarities)
            
            logger.info(f"Average similarity with new profile: {avg_sim:.4f}")
            logger.info(f"Max similarity with new profile: {max_sim:.4f}")
            logger.info(f"Min similarity with new profile: {min_sim:.4f}")
            
            # Count embeddings above threshold
            threshold = 0.62  # Default Chaffee threshold
            above_threshold = sum(1 for sim in similarities if sim >= threshold)
            percentage = (above_threshold / len(similarities)) * 100
            
            logger.info(f"Embeddings above threshold ({threshold}): {above_threshold}/{len(similarities)} ({percentage:.1f}%)")
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    create_new_profile()
