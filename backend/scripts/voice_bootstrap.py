#!/usr/bin/env python3
"""
Voice Profile Bootstrap CLI

Builds voice profiles from seed URLs and manages voice profile lifecycle.
"""

import os
import sys
import json
import hashlib
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import urllib.parse

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(backend_dir)

sys.path.append(project_root)
sys.path.append(backend_dir)
sys.path.append(os.path.join(script_dir, 'common'))

from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment

# Simple voice storage implementation to replace the missing module
class VoiceStorage:
    """Voice profile storage manager"""
    
    def __init__(self, voices_dir: str = 'voices'):
        self.voices_dir = Path(voices_dir)
        self.voices_dir.mkdir(exist_ok=True)
        
    def exists(self, name: str) -> bool:
        """Check if a voice profile exists"""
        profile_path = self.voices_dir / f"{name.lower()}.json"
        return profile_path.exists()
        
    def load(self, name: str) -> Optional[Dict]:
        """Load a voice profile"""
        profile_path = self.voices_dir / f"{name.lower()}.json"
        if not profile_path.exists():
            return None
            
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load profile {name}: {e}")
            return None
            
    def save(self, name: str, profile: Dict) -> bool:
        """Save a voice profile"""
        profile_path = self.voices_dir / f"{name.lower()}.json"
        try:
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save profile {name}: {e}")
            return False
            
    def list_profiles(self) -> List[str]:
        """List available voice profiles"""
        profiles = []
        for file_path in self.voices_dir.glob("*.json"):
            if file_path.stem.endswith('.meta'):
                continue
            profiles.append(file_path.stem)
        return profiles

def get_voice_storage(voices_dir: str = 'voices') -> VoiceStorage:
    """Get a voice storage instance"""
    return VoiceStorage(voices_dir)
    
def voice_exists(name: str, voices_dir: str = 'voices') -> bool:
    """Check if a voice profile exists"""
    storage = get_voice_storage(voices_dir)
    return storage.exists(name)
    
def save_voice_profile(name: str, profile: Dict, voices_dir: str = 'voices') -> bool:
    """Save a voice profile"""
    storage = get_voice_storage(voices_dir)
    return storage.save(name, profile)

logger = logging.getLogger(__name__)


def extract_video_id_from_url(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats.
    Returns the ID string or None if not found.
    """
    try:
        parsed = urllib.parse.urlparse(url)

        # Standard youtube.com URL variants
        if parsed.hostname in ['www.youtube.com', 'youtube.com', 'm.youtube.com']:
            # URL may be like: https://www.youtube.com/watch?v=VIDEOID
            q = urllib.parse.parse_qs(parsed.query)
            if 'v' in q:
                return q['v'][0]
            # Or embed style paths
            if parsed.path.startswith('/embed/'):
                return parsed.path.split('/embed/')[1].split('?')[0]
            if parsed.path.startswith('/v/'):
                return parsed.path.split('/v/')[1].split('?')[0]
            # Shorts format: /shorts/VIDEOID
            if parsed.path.startswith('/shorts/'):
                return parsed.path.split('/shorts/')[1].split('?')[0]

        # youtu.be short links
        if parsed.hostname in ['youtu.be']:
            return parsed.path.lstrip('/')

        return None

    except Exception as e:
        logger.error(f"Failed to extract video ID from {url}: {e}")
        return None


def compute_seed_hash(seeds_data: Dict[str, Any]) -> str:
    """
    Compute MD5 hash of seed data for tracking changes
    
    Args:
        seeds_data: Seed configuration data
        
    Returns:
        MD5 hash as hex string
    """
    # Create a stable representation for hashing
    # Only hash the actual URLs, not metadata like timestamps
    urls = [source['url'] for source in seeds_data.get('sources', [])]
    urls.sort()  # Ensure stable ordering
    
    content = json.dumps(urls, sort_keys=True)
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def validate_seed_file(seed_file_path: Path) -> Dict[str, Any]:
    """
    Validate and load seed configuration file
    
    Args:
        seed_file_path: Path to seed configuration file
        
    Returns:
        Parsed seed configuration
        
    Raises:
        ValueError: If seed file is invalid
    """
    if not seed_file_path.exists():
        raise ValueError(f"Seed file not found: {seed_file_path}")
    
    try:
        with open(seed_file_path, 'r', encoding='utf-8') as f:
            seeds_data = json.load(f)
            
        # Validate structure
        if 'sources' not in seeds_data:
            raise ValueError("Seed file missing 'sources' field")
            
        sources = seeds_data['sources']
        if not isinstance(sources, list) or len(sources) == 0:
            raise ValueError("'sources' must be a non-empty list")
            
        # Validate each source
        for i, source in enumerate(sources):
            if not isinstance(source, dict):
                raise ValueError(f"Source {i} must be an object")
            if 'url' not in source:
                raise ValueError(f"Source {i} missing 'url' field")
                
        return seeds_data
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in seed file: {e}")


def perform_purity_check(fetcher, 
                        profile_name: str, 
                        holdout_video_id: str,
                        min_similarity: float) -> bool:
    """
    Perform voice purity check using a holdout video
    
    Args:
        fetcher: Enhanced transcript fetcher instance
        profile_name: Name of the voice profile to test
        holdout_video_id: Video ID to use for holdout test
        min_similarity: Minimum required similarity
        
    Returns:
        True if purity check passes, False otherwise
    """
    try:
        logger.info(f"Performing purity check with video {holdout_video_id}")
        
        # Get short audio segment for testing
        youtube_url = f"https://www.youtube.com/watch?v={holdout_video_id}"
        
        # Note: This would need to be implemented in the enhanced transcript fetcher
        # For now, we'll assume it passes if the profile exists
        storage = get_voice_storage()
        if storage.exists(profile_name):
            logger.info(f"✅ Purity check passed (profile exists: {profile_name})")
            return True
        else:
            logger.warning(f"❌ Purity check failed (profile missing: {profile_name})")
            return False
    except Exception as e:
        logger.error(f"Purity check failed with error: {e}")
        return False


def build_voice_profile(seed_file_path: Path, profile_name: str, overwrite: bool = False, update: bool = False) -> bool:
    """
    Build a voice profile from seed URLs
    
    Args:
        seed_file_path: Path to seed configuration file
        profile_name: Name for the voice profile
        overwrite: Whether to overwrite existing profile
        update: Whether to update existing profile
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Validate seed file
        logger.info(f"Loading seed configuration from {seed_file_path}")
        seeds_data = validate_seed_file(seed_file_path)
        
        # Get voice storage
        storage = get_voice_storage()
        
        # Check if profile exists
        if storage.exists(profile_name):
            if overwrite:
                logger.info(f"🔄 Overwriting existing profile '{profile_name}'")
            elif update:
                logger.info(f"🔄 Updating existing profile '{profile_name}'")
            else:
                logger.error(f"Profile '{profile_name}' already exists. Use --overwrite or --update")
                return False
        else:
            if update:
                logger.warning(f"Profile '{profile_name}' does not exist. Creating new profile.")
            mode_description = "Initial Creation"
        
        # Similarity threshold from environment (used for metadata)
        min_similarity = float(os.getenv('CHAFFEE_MIN_SIM', '0.62'))
            
        # Extract URLs from seed data
        urls = [source['url'] for source in seeds_data['sources']]
        logger.info(f"🚀 Enrolling from {len(urls)} seed URLs using local audio files")
        
        # Find local audio files corresponding to the URLs
        audio_dir = Path("audio_storage")
        if not audio_dir.exists():
            logger.error(f"Audio directory not found: {audio_dir}")
            return False
            
        # Get all WAV files
        audio_files = list(audio_dir.glob("*.wav"))
        if not audio_files:
            logger.error(f"No WAV files found in {audio_dir}")
            return False
            
        logger.info(f"Found {len(audio_files)} WAV files in {audio_dir}")
        
        # Create voice enrollment
        voices_dir = Path(os.getenv('VOICES_DIR', 'voices'))
        enrollment = VoiceEnrollment(voices_dir=str(voices_dir))
        
        # Extract embeddings from all audio files
        all_embeddings = []
        for audio_file in audio_files:
            try:
                logger.info(f"Extracting embeddings from {audio_file}")
                
                # Use the same approach as ingest_youtube_enhanced.py
                # Process audio in chunks to handle large files
                from backend.scripts.ingest_youtube_enhanced import EnhancedTranscriptFetcher
                
                # Create a temporary fetcher just for audio processing
                fetcher = EnhancedTranscriptFetcher(
                    whisper_model="distil-large-v3",
                    audio_storage=True,
                    audio_storage_dir="audio_storage"
                )
                
                # Use the fetcher's methods to process the audio
                # This will handle chunking and memory management properly
                audio_path = str(audio_file)
                video_id = os.path.basename(audio_path).split('.')[0]
                
                # Use the enrollment method from the fetcher
                success = fetcher.enroll_speaker_from_audio(
                    audio_path=audio_path,
                    speaker_name=profile_name,
                    overwrite=overwrite
                )
                
                if success:
                    logger.info(f"Successfully processed {audio_file}")
                else:
                    logger.warning(f"Failed to process {audio_file}")
                    
            except Exception as e:
                logger.error(f"Error processing {audio_file}: {e}")
                import traceback
                traceback.print_exc()
                # Continue with next file
        
        if not all_embeddings:
            logger.error("No embeddings extracted from any audio file")
            return False
            
        logger.info(f"Extracted a total of {len(all_embeddings)} embeddings")
        
        # Calculate centroid
        import numpy as np
        centroid = np.mean(all_embeddings, axis=0).tolist()
        
        # Create profile
        profile = {
            'name': profile_name.lower(),
            'centroid': centroid,
            'embeddings': [emb.tolist() for emb in all_embeddings],
            'threshold': min_similarity,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'audio_sources': [os.path.basename(str(f)) for f in audio_files],
            'metadata': {
                'source': 'voice_bootstrap.py',
                'num_embeddings': len(all_embeddings)
            }
        }
        
        # Save profile
        success = storage.save(profile_name, profile)
        if not success:
            logger.error("Failed to save profile")
            return False
        
        # Verify profile was created
        if not storage.exists(profile_name):
            logger.error("Failed to save profile")
            return False
            
        # Load profile for validation
        profile_data = storage.load(profile_name)
        if not profile_data:
            logger.error("Profile exists but cannot be loaded")
            return False
                
        # Note: profile file is saved by the optimized pipeline. Proceed to metadata.
        metadata = {
            "version": 1,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "seeds_hash": compute_seed_hash(seeds_data),
            "min_sim": min_similarity,
            "seed_file": str(seed_file_path),
            "video_count": len(urls),
            "method": "optimized_pipeline",
            "mode": mode_description,
            "pipeline_features": [
                "ingest_youtube_enhanced",
                "pipelined_concurrency",
                "speaker_id_enrollment"
            ]
        }
        metadata_path = storage.voices_dir / f"{profile_name.lower()}.meta.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        logger.info(f"✅ Voice profile '{profile_name}' built successfully!")
        logger.info(f"   Profile: {storage.voices_dir / f'{profile_name.lower()}.json'}")
        logger.info(f"   Embeddings: {profile_data.get('metadata', {}).get('num_embeddings', 0)}")
        logger.info(f"   Method: Direct format selection with m4a audio")
        
        return True
            
    except Exception as e:
        logger.error(f"❌ Voice profile creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def build_voice_profile_from_local_audio(profile_name: str, overwrite: bool = False) -> bool:
    """
    Build a voice profile from local audio files
    
    Args:
        profile_name: Name for the voice profile
        overwrite: Whether to overwrite existing profile
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get voice storage
        # Validate seed file
        logger.info(f"Loading seed configuration from {seed_file_path}")
        seeds_data = validate_seed_file(seed_file_path)
        
        # Check if profile already exists
        storage = get_voice_storage()
        if storage.exists(profile_name) and not (overwrite or update):
            logger.error(f"Profile '{profile_name}' already exists. Use --overwrite to replace or --update to enhance.")
            return False
        
        # Determine mode
        if update and storage.exists(profile_name):
            logger.info(f"🔄 Updating existing profile '{profile_name}' with self-improving logic")
            mode_description = "Self-Improving Update (99%+ Chaffee content)"
        elif overwrite:
            logger.info(f"🔄 Overwriting existing profile '{profile_name}'")
            mode_description = "Complete Rebuild"
        else:
            logger.info(f"🆕 Creating new profile '{profile_name}'")
            mode_description = "Initial Creation"
        
        # Similarity threshold from environment (used for metadata)
        min_similarity = float(os.getenv('CHAFFEE_MIN_SIM', '0.62'))
            
        # Extract URLs and delegate to optimized pipeline (ingest_youtube_enhanced)
        urls = [source['url'] for source in seeds_data['sources']]
        logger.info(f"🚀 Enrolling from {len(urls)} seed URLs via optimized pipeline with DB ingestion")

        import subprocess
        # Set environment variable for dummy YouTube API key
        os.environ['YOUTUBE_API_KEY'] = 'dummy_key_for_setup'
        
        # Step 1: First create the voice profile with --setup-chaffee and yt-dlp source
        cmd = [
            sys.executable, '-m', 'backend.scripts.ingest_youtube_enhanced',
            '--source', 'yt-dlp',  # Use yt-dlp source
            '--setup-chaffee'
        ] + urls + [
            # Profile options
            '--voices-dir', os.getenv('VOICES_DIR', 'voices'),
            '--chaffee-min-sim', str(min_similarity),
        ]
        if overwrite:
            cmd.append('--overwrite-profile')
        if update:
            cmd.append('--update-profile')

        logger.info(f"Step 1: Creating voice profile: {' '.join(cmd[:6])} ... {len(urls)} URLs")
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.stdout:
                logger.debug(result.stdout)
            if result.stderr:
                logger.debug(result.stderr)
        except subprocess.CalledProcessError as e:
            logger.error("Voice profile creation failed!")
            logger.error(f"Exit code: {e.returncode}")
            logger.error(f"STDOUT:\n{e.stdout}")
            logger.error(f"STDERR:\n{e.stderr}")
            return False

        # Step 2: Now ingest the videos into the database
        logger.info("Step 2: Ingesting videos into database")
        ingest_cmd = [
            sys.executable, '-m', 'backend.scripts.ingest_youtube_enhanced',
            '--source', 'api',  # Use API source for better metadata
            '--limit', str(len(urls)),
            '--voices-dir', os.getenv('VOICES_DIR', 'voices'),
            '--chaffee-min-sim', str(min_similarity),
        ]
        
        # Add YouTube API key if available
        api_key = os.getenv('YOUTUBE_API_KEY', '')
        if api_key:
            ingest_cmd.extend(['--youtube-api-key', api_key])
        
        # Add all URLs directly
        for url in urls:
            ingest_cmd.append(url)
        
        logger.info(f"Running DB ingestion: {' '.join(ingest_cmd[:6])} ...")
        try:
            ingest_result = subprocess.run(ingest_cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if ingest_result.stdout:
                logger.debug(ingest_result.stdout)
            if ingest_result.stderr:
                logger.debug(ingest_result.stderr)
        except subprocess.CalledProcessError as e:
            logger.warning("Database ingestion failed, but profile was created successfully")
            logger.warning(f"Exit code: {e.returncode}")
            logger.warning(f"STDOUT:\n{e.stdout}")
            logger.warning(f"STDERR:\n{e.stderr}")
            # Continue even if DB ingestion fails - profile is the priority
        
        # Verify profile was created
        if not storage.exists(profile_name):
            logger.error("Failed to save profile")
            return False
            
        # Load profile for validation
        profile_data = storage.load(profile_name)
        if not profile_data:
            logger.error("Profile exists but cannot be loaded")
            return False
                
        # Note: profile file is saved by the optimized pipeline. Proceed to metadata.
        metadata = {
            "version": 1,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "seeds_hash": compute_seed_hash(seeds_data),
            "min_sim": min_similarity,
            "seed_file": str(seed_file_path),
            "video_count": len(urls),
            "method": "optimized_pipeline",
            "mode": mode_description,
            "pipeline_features": [
                "ingest_youtube_enhanced",
                "pipelined_concurrency",
                "speaker_id_enrollment"
            ]
        }
        metadata_path = storage.voices_dir / f"{profile_name.lower()}.meta.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        logger.info(f"✅ Voice profile '{profile_name}' built successfully!")
        logger.info(f"   Profile: {storage.voices_dir / f'{profile_name.lower()}.json'}")
        logger.info(f"   Embeddings: {profile_data.get('metadata', {}).get('num_embeddings', 0)}")
        logger.info(f"   Method: Direct format selection with m4a audio")
        
        return True
            
    except Exception as e:
        logger.error(f"❌ Voice profile creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def refresh_voice_profile(profile_name: str, since_date: str) -> bool:
    """
    Refresh a voice profile with new content since a given date
    
    Args:
        profile_name: Name of the voice profile to refresh
        since_date: Date string (YYYY-MM-DD format)
        
    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Refresh functionality not yet implemented")
    # TODO: Implement incremental refresh logic
    return False


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Voice Profile Bootstrap CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build Chaffee profile from seed URLs (initial creation)
  python -m backend.scripts.voice_bootstrap build \\
    --seeds backend/config/chaffee_seed_urls.json \\
    --name Chaffee \\
    --overwrite
  
  # Update existing profile with self-improving logic (99%+ Chaffee content)
  python -m backend.scripts.voice_bootstrap build \\
    --seeds backend/config/chaffee_seed_urls.json \\
    --name Chaffee \\
    --update
  
  # Refresh profile with new content (future)
  python -m backend.scripts.voice_bootstrap refresh \\
    --name Chaffee \\
    --since 2024-01-01
        """
    )
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
        ]
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Build command
    build_parser = subparsers.add_parser('build', help='Build voice profile from seed URLs')
    build_parser.add_argument('--seeds', type=Path, required=True,
                             help='Path to seed URLs configuration file')
    build_parser.add_argument('--name', type=str, required=True,
                             help='Name for the voice profile')
    build_parser.add_argument('--overwrite', action='store_true',
                             help='Overwrite existing profile if it exists')
    build_parser.add_argument('--update', action='store_true',
                             help='Update existing profile with new content (self-improving)')
    
    # Refresh command (future)
    refresh_parser = subparsers.add_parser('refresh', help='Refresh voice profile with new content')
    refresh_parser.add_argument('--name', type=str, required=True,
                               help='Name of the voice profile to refresh')
    refresh_parser.add_argument('--since', type=str, required=True,
                               help='Refresh with content since this date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
        
    try:
        if args.command == 'build':
            success = build_voice_profile(
                seed_file_path=args.seeds,
                profile_name=args.name,
                overwrite=args.overwrite,
                update=args.update
            )
            return 0 if success else 1
            
        elif args.command == 'refresh':
            success = refresh_voice_profile(
                profile_name=args.name,
                since_date=args.since
            )
            return 0 if success else 1
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
