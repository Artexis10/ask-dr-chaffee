#!/usr/bin/env python3
"""
Check the format of the voice profile
"""
import os
import sys
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_profile(profile_path):
    """Check the format of a voice profile"""
    try:
        with open(profile_path, 'r') as f:
            profile = json.load(f)
        
        logger.info(f"Profile keys: {list(profile.keys())}")
        
        if 'centroid' in profile:
            logger.info(f"Profile has centroid with length: {len(profile['centroid'])}")
            logger.info("This is a centroid-based profile (good)")
            return True
        elif 'embeddings' in profile:
            logger.info(f"Profile has embeddings: {len(profile['embeddings'])}")
            logger.info("This is an embeddings-based profile")
            
            # Create a centroid from the embeddings
            import numpy as np
            embeddings = np.array(profile['embeddings'])
            centroid = np.mean(embeddings, axis=0).tolist()
            
            # Create a new profile with the centroid
            new_profile = {
                'name': profile.get('name', 'chaffee'),
                'centroid': centroid,
                'threshold': profile.get('threshold', 0.62),
                'created_at': profile.get('created_at', '2025-09-29'),
                'metadata': {
                    'source': 'converted_from_embeddings',
                    'num_embeddings': len(profile['embeddings']),
                    'original_profile': os.path.basename(profile_path)
                }
            }
            
            # Save the new profile
            output_path = profile_path.replace('.json', '_centroid.json')
            with open(output_path, 'w') as f:
                json.dump(new_profile, f, indent=2)
            
            logger.info(f"Created centroid-based profile at {output_path}")
            return True
        else:
            logger.error("Profile doesn't have centroid or embeddings")
            return False
    except Exception as e:
        logger.error(f"Error checking profile: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    profile_path = "voices/chaffee.json"
    check_profile(profile_path)
