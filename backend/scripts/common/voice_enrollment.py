#!/usr/bin/env python3
"""
Voice enrollment system for speaker identification using SpeechBrain ECAPA embeddings
"""

import os
import json
import logging
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import tempfile
import torch
from dataclasses import dataclass, asdict
import librosa
import soundfile as sf

logger = logging.getLogger(__name__)

@dataclass
class VoiceProfile:
    """Voice profile containing speaker embeddings and metadata"""
    name: str
    centroid: List[float]  # Mean embedding vector
    embeddings: List[List[float]]  # All embeddings used to compute centroid
    metadata: Dict[str, Any]
    created_at: str
    audio_sources: List[str]  # Source files/URLs used for enrollment
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        # Convert numpy arrays to lists for JSON serialization
        result = {
            'name': self.name,
            'centroid': self.centroid if isinstance(self.centroid, list) else self.centroid.tolist(),
            'embeddings': [emb.tolist() if isinstance(emb, np.ndarray) else emb for emb in self.embeddings],
            'metadata': self.metadata,
            'created_at': self.created_at,
            'audio_sources': self.audio_sources
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VoiceProfile':
        """Create VoiceProfile from dictionary"""
        return cls(**data)
    
    def get_similarity_threshold(self) -> float:
        """Get recommended similarity threshold based on embedding variance"""
        if len(self.embeddings) < 2:
            return 0.82  # Default threshold
        
        # Calculate intra-speaker variance
        embeddings_array = np.array(self.embeddings)
        centroid_array = np.array(self.centroid)
        
        # Compute cosine similarities to centroid
        similarities = []
        for emb in embeddings_array:
            sim = np.dot(emb, centroid_array) / (np.linalg.norm(emb) * np.linalg.norm(centroid_array))
            similarities.append(sim)
        
        # Threshold = mean - 2*std (conservative)
        mean_sim = np.mean(similarities)
        std_sim = np.std(similarities)
        
        # Clamp between reasonable bounds
        return float(max(0.5, mean_sim - 3 * std_sim))

class VoiceEnrollment:
    """Voice enrollment system for speaker identification"""
    
    def __init__(self, voices_dir: Optional[str] = None):
        """
        Initialize voice enrollment system
        
        Args:
            voices_dir: Directory to store voice profiles (default: ~/.cache/enhanced_asr/voice_profiles)
        """
        if voices_dir:
            self.voices_dir = Path(voices_dir)
        else:
            # Default to ~/.cache/enhanced_asr/voice_profiles
            self.voices_dir = Path.home() / '.cache' / 'enhanced_asr' / 'voice_profiles'
            
        # Create directory if it doesn't exist
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize SpeechBrain model
        self.model = None
        
    def _load_model(self):
        """Load SpeechBrain ECAPA-TDNN model"""
        if self.model is not None:
            return
            
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading SpeechBrain ECAPA model on {device}")
            
            from speechbrain.pretrained import EncoderClassifier
            self.model = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="pretrained_models/spkrec-ecapa-voxceleb",
                run_opts={"device": device}
            )
            logger.info("Successfully loaded SpeechBrain ECAPA model")
        except Exception as e:
            logger.error(f"Failed to load SpeechBrain model: {e}")
            raise
    
    def _extract_embeddings_from_audio(self, audio_path: str) -> List[np.ndarray]:
        """Extract speaker embeddings from audio file using sliding window"""
        try:
            # Load model if not already loaded
            if self.model is None:
                self._load_model()
                
            # Load audio
            audio, sr = librosa.load(audio_path, sr=16000)
            logger.debug(f"Loaded audio: {len(audio)} samples at {sr}Hz")
            
            # Extract embeddings using sliding window (5-second segments, 2.5-second stride)
            window_size = 5 * sr  # 5 seconds
            stride = 2.5 * sr  # 2.5 seconds
            
            embeddings = []
            for start in range(0, len(audio) - window_size + 1, int(stride)):
                end = start + window_size
                segment = audio[start:end]
                
                # Skip segments with low energy (likely silence)
                if np.mean(np.abs(segment)) < 0.005:
                    continue
                    
                # Extract embedding
                with torch.no_grad():
                    embedding = self.model.encode_batch(torch.tensor(segment).unsqueeze(0))
                    embedding_np = embedding.squeeze().cpu().numpy()
                    embeddings.append(embedding_np)
                    
            logger.info(f"Extracted {len(embeddings)} embeddings from {audio_path}")
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to extract embeddings from {audio_path}: {e}")
            return []
    
    def _download_youtube_audio(self, url: str) -> Optional[str]:
        """Download audio from YouTube URL using yt-dlp"""
        try:
            import subprocess
            import shutil
            
            # Check if yt-dlp is available
            if shutil.which('yt-dlp') is None:
                logger.error("yt-dlp not found in PATH. Please install with: pip install yt-dlp")
                return None
            
            # Create temporary directory for output
            temp_dir = tempfile.mkdtemp()
            output_path = os.path.join(temp_dir, 'audio.%(ext)s')
            
            # Get video ID for better filename
            video_id = url.split('v=')[-1].split('&')[0] if 'v=' in url else 'audio'
            
            # Use yt-dlp to download audio - directly to mp3 to avoid ffmpeg issues
            cmd = [
                'yt-dlp',
                '--extract-audio',
                '--audio-format', 'mp3',  # Use mp3 instead of wav to avoid ffmpeg issues
                '--audio-quality', '0',
                '--no-playlist',
                '--no-warnings',
                '--no-check-certificate',  # Avoid SSL issues
                '--prefer-ffmpeg',
                '--output', output_path,
                url
            ]
            
            logger.info(f"Downloading audio from YouTube: {url}")
            logger.info(f"Running command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # Check for downloaded file
            expected_file = os.path.join(temp_dir, f'audio.mp3')
            if os.path.exists(expected_file):
                logger.info(f"Successfully downloaded audio to: {expected_file}")
                return expected_file
            
            # If the expected file doesn't exist, look for any audio file
            audio_files = []
            for ext in ['.mp3', '.m4a', '.wav', '.webm']:
                audio_files.extend(list(Path(temp_dir).glob(f'*{ext}')))
            
            if audio_files:
                logger.info(f"Found audio file: {audio_files[0]}")
                return str(audio_files[0])
            
            # If we get here, something went wrong
            logger.error(f"yt-dlp failed with return code {result.returncode}")
            logger.error(f"STDERR: {result.stderr}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"No audio files found in {temp_dir}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to download audio from {url}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def enroll_speaker(
        self, 
        name: str, 
        audio_sources: List[str], 
        overwrite: bool = False,
        update: bool = False,
        min_duration: float = 30.0
    ) -> Optional[VoiceProfile]:
        """
        Enroll a speaker using audio files or YouTube URLs
        
        Args:
            name: Speaker name (e.g., "Chaffee")
            audio_sources: List of file paths or YouTube URLs
            overwrite: Whether to overwrite existing profile
            update: Whether to update existing profile with new audio
            min_duration: Minimum total audio duration required (seconds)
            
        Returns:
            VoiceProfile if successful, None otherwise
        """
        profile_path = self.voices_dir / f"{name.lower()}.json"
        
        # Load existing profile if updating
        existing_embeddings = []
        existing_sources = []
        existing_duration = 0.0
        
        if profile_path.exists():
            if update:
                # Load existing profile for updating
                existing_profile = self.load_profile(name)
                if existing_profile:
                    existing_embeddings = existing_profile.embeddings
                    existing_sources = existing_profile.audio_sources
                    existing_duration = existing_profile.metadata.get('total_duration_seconds', 0.0)
                    logger.info(f"Updating existing profile for '{name}' with {len(existing_embeddings)} embeddings")
            elif not overwrite:
                logger.error(f"Voice profile for '{name}' already exists. Use --overwrite to replace or --update to add new audio.")
                return None
        
        logger.info(f"Enrolling speaker: {name} with {len(audio_sources)} audio sources")
        
        all_embeddings = []
        processed_sources = []
        total_duration = 0.0
        temp_files = []
        
        try:
            for source in audio_sources:
                logger.info(f"Processing audio source: {source}")
                
                # Handle YouTube URLs vs local files
                audio_path = source
                if source.startswith(('http://', 'https://', 'www.')):
                    # Download from YouTube
                    audio_path = self._download_youtube_audio(source)
                    if audio_path:
                        temp_files.append(audio_path)
                    else:
                        logger.warning(f"Failed to download audio from {source}")
                        continue
                elif not os.path.exists(source):
                    logger.warning(f"Audio file does not exist: {source}")
                    continue
                
                # Check audio duration
                try:
                    audio, sr = librosa.load(audio_path, sr=None)
                    duration = len(audio) / sr
                    total_duration += duration
                    logger.info(f"Audio duration: {duration:.1f}s")
                except Exception as e:
                    logger.error(f"Failed to load audio {audio_path}: {e}")
                    continue
                
                # Extract embeddings
                embeddings = self._extract_embeddings_from_audio(audio_path)
                if embeddings:
                    all_embeddings.extend(embeddings)
                    processed_sources.append(source)
                    logger.info(f"Added {len(embeddings)} embeddings from {source}")
                else:
                    logger.warning(f"No embeddings extracted from {source}")
                    continue
            
            # Add existing embeddings and duration if updating
            if existing_embeddings:
                all_embeddings.extend(existing_embeddings)
                processed_sources.extend(existing_sources)
                total_duration += existing_duration
                logger.info(f"Added {len(existing_embeddings)} embeddings from existing profile")
                
            # Check if we have enough audio
            if total_duration < min_duration:
                logger.error(f"Insufficient audio duration: {total_duration:.1f}s < {min_duration:.1f}s required")
                return None
                
            # Compute centroid (average of all embeddings)
            embeddings_array = np.array(all_embeddings)
            centroid = np.mean(embeddings_array, axis=0)
            
            # Compute recommended threshold
            similarities = []
            for emb in all_embeddings:
                sim = np.dot(emb, centroid) / (np.linalg.norm(emb) * np.linalg.norm(centroid))
                similarities.append(float(sim))
                
            # Use 3 standard deviations below mean as threshold
            mean_sim = np.mean(similarities)
            std_sim = np.std(similarities)
            recommended_threshold = float(max(0.5, mean_sim - 3 * std_sim))
            
            # Create profile
            profile = VoiceProfile(
                name=name,
                embeddings=all_embeddings,
                centroid=centroid.tolist(),
                audio_sources=processed_sources,
                created_at=datetime.now().isoformat(),
                metadata={
                    'num_embeddings': len(all_embeddings),
                    'total_duration_seconds': total_duration,
                    'recommended_threshold': recommended_threshold,
                    'model': 'speechbrain/spkrec-ecapa-voxceleb'
                }
            )
            
            # Save profile
            with open(profile_path, 'w') as f:
                json.dump(profile.to_dict(), f, indent=2)
            
            logger.info(f"Successfully enrolled speaker '{name}' with {len(all_embeddings)} embeddings")
            logger.info(f"Recommended similarity threshold: {profile.metadata['recommended_threshold']:.3f}")
            logger.info(f"Profile saved to: {profile_path}")
            
            return profile
            
        except Exception as e:
            logger.error(f"Failed to enroll speaker {name}: {e}")
            return None
            
        finally:
            # Cleanup temporary files
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except:
                    pass
    
    def load_profile(self, name: str) -> Optional[VoiceProfile]:
        """Load a voice profile by name"""
        profile_path = self.voices_dir / f"{name.lower()}.json"
        
        if not profile_path.exists():
            logger.error(f"Voice profile not found: {profile_path}")
            return None
        
        try:
            with open(profile_path, 'r') as f:
                data = json.load(f)
            return VoiceProfile.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load voice profile {name}: {e}")
            return None
    
    def list_profiles(self) -> List[str]:
        """List all available voice profiles"""
        profiles = []
        for profile_file in self.voices_dir.glob('*.json'):
            profiles.append(profile_file.stem.title())
        return sorted(profiles)
    
    def compute_similarity(self, embedding: np.ndarray, profile: VoiceProfile) -> float:
        """Compute cosine similarity between embedding and profile centroid"""
        centroid = np.array(profile.centroid)
        similarity = np.dot(embedding, centroid) / (np.linalg.norm(embedding) * np.linalg.norm(centroid))
        return float(similarity)

def main():
    """CLI for voice enrollment"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Voice enrollment system for speaker identification')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Enroll command
    enroll_parser = subparsers.add_parser('enroll', help='Enroll a new speaker')
    enroll_parser.add_argument('--name', required=True, help='Speaker name (e.g., Chaffee)')
    enroll_parser.add_argument('--audio', nargs='+', help='Audio file paths')
    enroll_parser.add_argument('--url', nargs='+', help='YouTube URLs')
    enroll_parser.add_argument('--overwrite', action='store_true', help='Overwrite existing profile')
    enroll_parser.add_argument('--update', action='store_true', help='Update existing profile with new audio')
    enroll_parser.add_argument('--min-duration', type=float, default=30.0, help='Minimum audio duration (seconds)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List enrolled speakers')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show speaker profile information')
    info_parser.add_argument('name', help='Speaker name')
    
    parser.add_argument('--voices-dir', help='Directory to store voice profiles')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
    
    # Initialize enrollment system
    enrollment = VoiceEnrollment(voices_dir=args.voices_dir)
    
    if args.command == 'enroll':
        # Collect audio sources
        audio_sources = []
        if args.audio:
            audio_sources.extend(args.audio)
        if args.url:
            audio_sources.extend(args.url)
        
        if not audio_sources:
            logger.error("No audio sources provided. Use --audio or --url")
            return 1
        
        # Enroll speaker
        profile = enrollment.enroll_speaker(
            name=args.name,
            audio_sources=audio_sources,
            overwrite=args.overwrite,
            update=args.update,
            min_duration=args.min_duration
        )
        
        if profile:
            print(f"✓ Successfully enrolled speaker: {args.name}")
            print(f"  Embeddings: {profile.metadata['num_embeddings']}")
            print(f"  Duration: {profile.metadata['total_duration_seconds']:.1f}s")
            print(f"  Threshold: {profile.metadata['recommended_threshold']:.3f}")
            return 0
        else:
            print(f"✗ Failed to enroll speaker: {args.name}")
            return 1
    
    elif args.command == 'list':
        profiles = enrollment.list_profiles()
        if profiles:
            print("Enrolled speakers:")
            for profile_name in profiles:
                print(f"  • {profile_name}")
        else:
            print("No enrolled speakers found.")
        return 0
    
    elif args.command == 'info':
        profile = enrollment.load_profile(args.name)
        if profile:
            print(f"Speaker: {profile.name}")
            print(f"Created: {profile.created_at}")
            print(f"Embeddings: {profile.metadata['num_embeddings']}")
            print(f"Duration: {profile.metadata['total_duration_seconds']:.1f}s")
            print(f"Threshold: {profile.metadata['recommended_threshold']:.3f}")
            print(f"Sources: {len(profile.audio_sources)}")
            for i, source in enumerate(profile.audio_sources, 1):
                print(f"  {i}. {source}")
        else:
            print(f"Speaker '{args.name}' not found.")
            return 1
        return 0
    
    else:
        parser.print_help()
        return 1

if __name__ == '__main__':
    exit(main())
