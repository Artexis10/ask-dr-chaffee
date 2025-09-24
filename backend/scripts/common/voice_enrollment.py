#!/usr/bin/env python3
"""
Voice Enrollment System for Speaker Identification
"""

import os
import json
import logging
import numpy as np
import torch
import librosa
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class VoiceProfile:
    """Voice profile containing speaker embeddings and metadata"""
    name: str
    embeddings: List[np.ndarray]
    threshold: float
    created_at: str
    metadata: Dict[str, Any]

def compute_threshold_from_similarities(similarities: List[float]) -> float:
    """Compute threshold from a list of similarities"""
    if len(similarities) < 2:
        return 0.7  # Default conservative threshold
    
    similarities = np.array(similarities)
    
    # Threshold = mean - 2*std (conservative)
    mean_sim = np.mean(similarities)
    std_sim = np.std(similarities)
    
    # Clamp between reasonable bounds
    return float(max(0.5, mean_sim - 3 * std_sim))

class VoiceEnrollment:
    """Voice enrollment system for speaker identification"""
    
    def __init__(self, voices_dir: str = "voices", device: str = "cpu"):
        """
        Initialize voice enrollment system
        
        Args:
            voices_dir: Directory to store voice profiles
            device: Device to use for SpeechBrain model (default: "cpu")
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
        self.device = device
        
    def _load_model(self):
        """Load SpeechBrain ECAPA-TDNN model"""
        if self.model is not None:
            return
            
        try:
            # Disable symlinks to avoid permission issues on Windows
            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
            
            # Force CPU for compatibility with RTX 5080
            self.device = "cpu"
            logger.info(f"Loading SpeechBrain ECAPA model on {self.device}")
            
            # Load model directly from HuggingFace
            from speechbrain.inference import EncoderClassifier
            self.model = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                run_opts={"device": self.device}
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
            
            # Extract embeddings using sliding window (smaller window for better coverage)
            window_size = 3 * sr  # 3 seconds (was 5 seconds)
            stride = 1.5 * sr  # 1.5 seconds (was 2.5 seconds)
            
            embeddings = []
            for start in range(0, len(audio) - window_size + 1, int(stride)):
                end = start + window_size
                segment = audio[start:end]
                
                # Skip segments with very low energy (likely silence) - use extremely low threshold
                # Original threshold was 0.001, lowering to 0.0001 to ensure we get embeddings
                if np.mean(np.abs(segment)) < 0.0001:
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
    
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings"""
        # Normalize embeddings
        emb1_norm = embedding1 / np.linalg.norm(embedding1)
        emb2_norm = embedding2 / np.linalg.norm(embedding2)
        
        # Compute cosine similarity
        similarity = np.dot(emb1_norm, emb2_norm)
        return float(similarity)
    
    def save_profile(self, name: str, embeddings: List[np.ndarray], 
                    threshold: Optional[float] = None, metadata: Optional[Dict] = None) -> None:
        """Save voice profile to disk"""
        if not embeddings:
            raise ValueError("Cannot save profile with no embeddings")
        
        if threshold is None:
            # Compute threshold from internal similarities
            similarities = []
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    sim = self.compute_similarity(embeddings[i], embeddings[j])
                    similarities.append(sim)
            threshold = compute_threshold_from_similarities(similarities)
        
        profile_data = {
            'name': name,
            'embeddings': [emb.tolist() for emb in embeddings],
            'threshold': threshold,
            'created_at': str(Path().absolute()),
            'metadata': metadata or {}
        }
        
        profile_path = self.voices_dir / f"{name.lower()}.json"
        with open(profile_path, 'w') as f:
            json.dump(profile_data, f, indent=2)
        
        logger.info(f"Saved voice profile for {name} to {profile_path}")
    
    def load_profile(self, name: str) -> Optional[np.ndarray]:
        """Load voice profile from disk"""
        profile_path = self.voices_dir / f"{name.lower()}.json"
        
        if not profile_path.exists():
            logger.warning(f"Profile not found: {profile_path}")
            return None
        
        try:
            with open(profile_path, 'r') as f:
                profile_data = json.load(f)
            
            # Convert embeddings back to numpy arrays and compute mean
            embeddings = [np.array(emb) for emb in profile_data['embeddings']]
            mean_embedding = np.mean(embeddings, axis=0)
            
            logger.debug(f"Loaded profile for {name}: {len(embeddings)} embeddings")
            return mean_embedding
            
        except Exception as e:
            logger.error(f"Failed to load profile {name}: {e}")
            return None
    
    def list_profiles(self) -> List[str]:
        """List available voice profiles"""
        profiles = []
        for profile_file in self.voices_dir.glob("*.json"):
            if profile_file.name != '.gitignore':
                profile_name = profile_file.stem.title()
                profiles.append(profile_name)
        return profiles
    
    def get_profile_info(self, name: str) -> Optional[Dict]:
        """Get profile information"""
        profile_path = self.voices_dir / f"{name.lower()}.json"
        
        if not profile_path.exists():
            return None
        
        try:
            with open(profile_path, 'r') as f:
                profile_data = json.load(f)
            
            # Handle both 'threshold' and 'recommended_threshold' field names
            threshold = profile_data.get('threshold') or profile_data.get('recommended_threshold', 0.7)
            
            return {
                'name': profile_data['name'],
                'threshold': threshold,
                'embedding_count': len(profile_data['embeddings']),
                'created_at': profile_data.get('created_at'),
                'metadata': profile_data.get('metadata', {})
            }
        except Exception as e:
            logger.error(f"Failed to get profile info for {name}: {e}")
            return None
            
    def enroll_speaker(self, name: str, audio_sources: List[str], 
                      overwrite: bool = False, update: bool = False,
                      min_duration: float = 30.0) -> Optional[Dict]:
        """
        Enroll a speaker using audio sources (files or YouTube URLs)
        
        Args:
            name: Speaker name
            audio_sources: List of audio file paths or YouTube URLs
            overwrite: Whether to overwrite existing profile
            update: Whether to update existing profile
            min_duration: Minimum audio duration required
            
        Returns:
            Profile metadata if successful, None otherwise
        """
        try:
            # Check if profile exists
            profile_path = self.voices_dir / f"{name.lower()}.json"
            existing_profile = None
            existing_sources = []
            
            if profile_path.exists():
                if not (overwrite or update):
                    logger.warning(f"Profile {name} already exists. Use --overwrite or --update")
                    return None
                    
                # Load existing profile if updating
                if update:
                    try:
                        with open(profile_path, 'r') as f:
                            existing_profile = json.load(f)
                            existing_sources = existing_profile.get('audio_sources', [])
                    except Exception as e:
                        logger.error(f"Failed to load existing profile: {e}")
                        if not overwrite:
                            return None
            
            # Process audio sources
            all_embeddings = []
            processed_sources = []
            total_duration = 0.0
            
            # Filter out duplicate sources if updating
            new_sources = []
            for source in audio_sources:
                # Normalize YouTube URLs to standard format
                if 'youtube.com' in source or 'youtu.be' in source:
                    # Extract video ID and standardize URL
                    if 'youtu.be/' in source:
                        video_id = source.split('youtu.be/')[-1].split('?')[0]
                    else:
                        video_id = source.split('v=')[-1].split('&')[0]
                    
                    standard_url = f"https://www.youtube.com/watch?v={video_id}"
                    
                    # Check if this video is already in the profile
                    if update and standard_url in existing_sources:
                        logger.info(f"Skipping already enrolled video: {standard_url}")
                        continue
                    
                    source = standard_url
                
                new_sources.append(source)
            
            # Process new sources
            for source in new_sources:
                logger.info(f"Processing audio source: {source}")
                
                # Handle YouTube URLs
                if 'youtube.com' in source or 'youtu.be' in source:
                    # Download audio using yt-dlp
                    import tempfile
                    import subprocess
                    
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                        try:
                            cmd = [
                                'yt-dlp',
                                '-x',
                                '--audio-format', 'wav',
                                '--audio-quality', '0',
                                '--format', 'bestaudio',
                                '--no-check-certificate',
                                '--no-playlist',
                                '--ignore-errors',
                                '-o', tmp_file.name,
                                source
                            ]
                            
                            logger.info(f"Downloading audio from {source}")
                            subprocess.run(cmd, check=True, capture_output=True)
                            
                            # Extract embeddings
                            embeddings = self._extract_embeddings_from_audio(tmp_file.name)
                            
                            if embeddings:
                                # Get audio duration
                                import librosa
                                duration = librosa.get_duration(path=tmp_file.name)
                                
                                if duration >= min_duration:
                                    all_embeddings.extend(embeddings)
                                    processed_sources.append(source)
                                    total_duration += duration
                                    logger.info(f"Added {len(embeddings)} embeddings from {source} ({duration:.1f}s)")
                                else:
                                    logger.warning(f"Audio too short: {duration:.1f}s < {min_duration:.1f}s")
                            else:
                                logger.warning(f"No embeddings extracted from {source}")
                                
                        except Exception as e:
                            logger.error(f"Failed to process YouTube URL {source}: {e}")
                        finally:
                            # Clean up temp file
                            try:
                                os.unlink(tmp_file.name)
                            except:
                                pass
                
                # Handle local audio files
                elif os.path.exists(source):
                    embeddings = self._extract_embeddings_from_audio(source)
                    
                    if embeddings:
                        # Get audio duration
                        import librosa
                        duration = librosa.get_duration(path=source)
                        
                        if duration >= min_duration:
                            all_embeddings.extend(embeddings)
                            processed_sources.append(source)
                            total_duration += duration
                            logger.info(f"Added {len(embeddings)} embeddings from {source} ({duration:.1f}s)")
                        else:
                            logger.warning(f"Audio too short: {duration:.1f}s < {min_duration:.1f}s")
                    else:
                        logger.warning(f"No embeddings extracted from {source}")
                else:
                    logger.warning(f"Source not found: {source}")
            
            # Combine with existing embeddings if updating
            if update and existing_profile:
                existing_embeddings = [np.array(emb) for emb in existing_profile.get('embeddings', [])]
                all_embeddings.extend(existing_embeddings)
                
                # Add existing sources
                for source in existing_sources:
                    if source not in processed_sources:
                        processed_sources.append(source)
                
                # Add existing duration
                if 'metadata' in existing_profile and 'total_duration_seconds' in existing_profile['metadata']:
                    total_duration += existing_profile['metadata']['total_duration_seconds']
            
            # Check if we have enough embeddings
            if not all_embeddings:
                logger.error("No embeddings extracted from any source")
                return None
                
            # Compute threshold from internal similarities
            similarities = []
            for i in range(min(len(all_embeddings), 100)):
                for j in range(i + 1, min(len(all_embeddings), 100)):
                    sim = self.compute_similarity(all_embeddings[i], all_embeddings[j])
                    similarities.append(sim)
            
            threshold = compute_threshold_from_similarities(similarities)
            
            # Create metadata
            metadata = {
                'num_embeddings': len(all_embeddings),
                'total_duration_seconds': total_duration,
                'recommended_threshold': threshold,
                'model': 'speechbrain/spkrec-ecapa-voxceleb'
            }
            
            # Save profile
            from datetime import datetime
            profile_data = {
                'name': name,
                'embeddings': [emb.tolist() for emb in all_embeddings],
                'threshold': threshold,
                'recommended_threshold': threshold,
                'created_at': datetime.now().isoformat(),
                'metadata': metadata,
                'audio_sources': processed_sources
            }
            
            with open(profile_path, 'w') as f:
                json.dump(profile_data, f, indent=2)
            
            logger.info(f"Saved voice profile for {name} with {len(all_embeddings)} embeddings")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to enroll speaker: {e}")
            import traceback
            traceback.print_exc()
            return None
