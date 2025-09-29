#!/usr/bin/env python3
"""
Create a voice profile for Dr. Chaffee using seed URLs and voice_enrollment_optimized.py
"""
import os
import sys
import json
import logging
import tempfile
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def download_audio(url, output_dir):
    """Download audio from a YouTube URL using yt-dlp"""
    try:
        # Extract video ID
        if "youtube.com/watch?v=" in url:
            video_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            video_id = url.split("/")[-1]
        else:
            logger.error(f"Unsupported URL format: {url}")
            return None
            
        output_path = os.path.join(output_dir, f"{video_id}.wav")
        
        # Check if already downloaded
        if os.path.exists(output_path):
            logger.info(f"Audio already downloaded: {output_path}")
            return output_path
            
        # Download using yt-dlp
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "wav",
            "--audio-quality", "0",
            "--format", "bestaudio",
            "--no-check-certificate",
            "--no-playlist",
            "--ignore-errors",
            "-o", output_path,
            url
        ]
        
        logger.info(f"Downloading audio from {url}")
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Check if file exists
        if os.path.exists(output_path):
            logger.info(f"Downloaded audio to {output_path}")
            return output_path
        else:
            logger.error(f"Failed to download audio from {url}")
            return None
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Error downloading audio from {url}: {e}")
        logger.error(f"STDERR: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Error downloading audio: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_profile_from_seeds():
    """Create a voice profile for Dr. Chaffee using seed URLs"""
    try:
        # Import voice enrollment
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        
        # Define paths
        script_dir = Path(__file__).parent
        seed_file = script_dir / "chaffee_seed_urls.json"
        
        if not seed_file.exists():
            logger.error(f"Seed file not found: {seed_file}")
            return False
            
        logger.info(f"Using seed file: {seed_file}")
        
        # Load seed file
        with open(seed_file, 'r', encoding='utf-8') as f:
            seed_data = json.load(f)
            
        # Extract URLs
        urls = [source['url'] for source in seed_data['sources']]
        logger.info(f"Found {len(urls)} URLs in seed file")
        
        # Create audio storage directory
        audio_dir = Path("audio_storage")
        audio_dir.mkdir(exist_ok=True)
        logger.info(f"Audio will be stored in: {audio_dir}")
        
        # Download audio files
        audio_files = []
        for i, url in enumerate(urls):
            logger.info(f"Processing URL {i+1}/{len(urls)}: {url}")
            audio_path = download_audio(url, audio_dir)
            if audio_path:
                audio_files.append(audio_path)
        
        if not audio_files:
            logger.error("Failed to download any audio files")
            return False
            
        logger.info(f"Downloaded {len(audio_files)} audio files")
        
        # Create voice enrollment
        voices_dir = Path(os.getenv('VOICES_DIR', 'voices'))
        enrollment = VoiceEnrollment(voices_dir=str(voices_dir))
        
        # Backup existing profile if it exists
        profile_path = voices_dir / "chaffee.json"
        backup_path = voices_dir / "chaffee_backup_before_seed.json"
        
        if profile_path.exists():
            import shutil
            shutil.copy(profile_path, backup_path)
            logger.info(f"Backed up existing profile to {backup_path}")
            
            # Remove the existing profile to ensure we create a fresh one
            os.remove(profile_path)
            logger.info(f"Removed existing profile to create a fresh one")
        
        # Create profile from audio files
        logger.info(f"Creating profile from {len(audio_files)} audio files")
        profile = enrollment.enroll_speaker(
            name="chaffee",
            audio_sources=audio_files,
            overwrite=True
        )
        
        if not profile:
            logger.error("Failed to create profile")
            return False
            
        logger.info(f"✅ Successfully created profile at {profile_path}")
        
        # Test the profile with one of the audio files
        test_file = audio_files[0]
        logger.info(f"Testing profile with {test_file}")
        
        # Extract embeddings
        embeddings = enrollment._extract_embeddings_from_audio(test_file)
        
        if embeddings:
            # Calculate similarity for each embedding
            import numpy as np
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
        logger.error(f"Error creating profile: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    create_profile_from_seeds()
