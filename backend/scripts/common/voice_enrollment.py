#!/usr/bin/env python3
"""
Voice enrollment system for speaker identification using SpeechBrain ECAPA embeddings
"""

import os
import json
import logging
import numpy as np
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
        return asdict(self)
    
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
        threshold = max(0.75, min(0.95, mean_sim - 2 * std_sim))
        return threshold

class VoiceEnrollment:
    """Voice enrollment system using SpeechBrain ECAPA-TDNN embeddings"""
    
    def __init__(self, voices_dir: str = None, model_name: str = "speechbrain/spkrec-ecapa-voxceleb"):
        self.voices_dir = Path(voices_dir or os.getenv('VOICES_DIR', 'voices'))
        self.voices_dir.mkdir(exist_ok=True)
        self.model_name = model_name
        self._model = None
        self._device = None
        
    def _get_model(self):
        """Lazy load SpeechBrain ECAPA model"""
        if self._model is None:
            try:
                from speechbrain.pretrained import EncoderClassifier
                
                # Determine device
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"Loading SpeechBrain ECAPA model on {self._device}")
                
                # Load pretrained ECAPA-TDNN model
                self._model = EncoderClassifier.from_hparams(
                    source=self.model_name,
                    run_opts={"device": self._device}
                )
                logger.info("Successfully loaded SpeechBrain ECAPA model")
                
            except ImportError as e:
                raise ImportError(f"SpeechBrain not available. Install with: pip install speechbrain. Error: {e}")
            except Exception as e:
                logger.error(f"Failed to load SpeechBrain model: {e}")
                raise
                
        return self._model
    
    def _extract_embeddings_from_audio(self, audio_path: str, segment_duration: float = 3.0) -> List[np.ndarray]:
        """Extract speaker embeddings from audio file in segments"""
        model = self._get_model()
        
        try:
            # Load audio file
            audio, sr = librosa.load(audio_path, sr=16000, mono=True)
            logger.debug(f"Loaded audio: {len(audio)} samples at {sr}Hz")
            
            # Split into segments for robust embedding extraction
            segment_samples = int(segment_duration * sr)
            embeddings = []
            
            for start_idx in range(0, len(audio), segment_samples):
                end_idx = min(start_idx + segment_samples, len(audio))
                segment = audio[start_idx:end_idx]
                
                # Skip segments that are too short (< 1 second)
                if len(segment) < sr:
                    continue
                
                # Convert to torch tensor
                segment_tensor = torch.FloatTensor(segment).unsqueeze(0)
                if self._device == "cuda":
                    segment_tensor = segment_tensor.cuda()
                
                # Extract embedding
                with torch.no_grad():
                    embedding = model.encode_batch(segment_tensor)
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
            
            # Create temporary file for audio
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                output_path = tmp_file.name
            
            # Use yt-dlp to download audio
            cmd = [
                'yt-dlp',
                '--extract-audio',
                '--audio-format', 'wav',
                '--audio-quality', '0',
                '--no-playlist',
                '-o', output_path.replace('.wav', '.%(ext)s'),
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logger.error(f"yt-dlp failed: {result.stderr}")
                return None
            
            # Find the actual output file
            output_dir = Path(output_path).parent
            video_id = url.split('v=')[-1].split('&')[0] if 'v=' in url else 'audio'
            
            for ext in ['.wav', '.mp3', '.m4a']:
                potential_path = output_dir / f"{video_id}{ext}"
                if potential_path.exists():
                    return str(potential_path)
            
            # Fallback: find any audio file created recently
            audio_files = list(output_dir.glob('*.wav')) + list(output_dir.glob('*.mp3'))
            if audio_files:
                return str(audio_files[0])
            
            logger.error(f"Could not find downloaded audio file for {url}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to download audio from {url}: {e}")
            return None
    
    def enroll_speaker(
        self, 
        name: str, 
        audio_sources: List[str], 
        overwrite: bool = False,
        min_duration: float = 30.0
    ) -> Optional[VoiceProfile]:
        """
        Enroll a speaker using audio files or YouTube URLs
        
        Args:
            name: Speaker name (e.g., "Chaffee")
            audio_sources: List of file paths or YouTube URLs
            overwrite: Whether to overwrite existing profile
            min_duration: Minimum total audio duration required (seconds)
            
        Returns:
            VoiceProfile if successful, None otherwise
        """
        profile_path = self.voices_dir / f"{name.lower()}.json"
        
        if profile_path.exists() and not overwrite:
            logger.error(f"Voice profile for '{name}' already exists. Use --overwrite to replace.")
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
            
            # Check if we have enough data
            if total_duration < min_duration:
                logger.error(f"Insufficient audio duration: {total_duration:.1f}s < {min_duration}s required")
                return None
            
            if len(all_embeddings) < 3:
                logger.error(f"Insufficient embeddings: {len(all_embeddings)} < 3 required")
                return None
            
            # Compute centroid embedding
            embeddings_array = np.array(all_embeddings)
            centroid = np.mean(embeddings_array, axis=0)
            
            # Create voice profile
            from datetime import datetime
            profile = VoiceProfile(
                name=name,
                centroid=centroid.tolist(),
                embeddings=[emb.tolist() for emb in all_embeddings],
                metadata={
                    "total_duration_seconds": total_duration,
                    "num_embeddings": len(all_embeddings),
                    "embedding_dim": len(centroid),
                    "model": self.model_name,
                    "recommended_threshold": None  # Will be computed
                },
                created_at=datetime.now().isoformat(),
                audio_sources=processed_sources
            )
            
            # Compute recommended threshold
            profile.metadata["recommended_threshold"] = profile.get_similarity_threshold()
            
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
