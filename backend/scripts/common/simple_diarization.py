#!/usr/bin/env python3
"""
Enhanced simple diarization module that doesn't require HuggingFace authentication
Uses spectral features and clustering for better speaker differentiation
"""

import os
import numpy as np
import librosa
import soundfile as sf
import tempfile
from typing import List, Tuple, Optional, Dict, Any
import logging
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import warnings

# Suppress warnings
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

logger = logging.getLogger(__name__)

def extract_audio_features(audio: np.ndarray, sr: int, frame_size: int = 1024, hop_length: int = 512) -> Dict[str, np.ndarray]:
    """
    Extract audio features for speaker differentiation
    
    Args:
        audio: Audio signal
        sr: Sample rate
        frame_size: Frame size for feature extraction
        hop_length: Hop length for feature extraction
        
    Returns:
        Dictionary of audio features
    """
    features = {}
    
    # Energy features
    features['rms'] = librosa.feature.rms(y=audio, frame_length=frame_size, hop_length=hop_length)[0]
    
    # Spectral features
    features['spectral_centroid'] = librosa.feature.spectral_centroid(y=audio, sr=sr, n_fft=frame_size, hop_length=hop_length)[0]
    features['spectral_bandwidth'] = librosa.feature.spectral_bandwidth(y=audio, sr=sr, n_fft=frame_size, hop_length=hop_length)[0]
    features['spectral_rolloff'] = librosa.feature.spectral_rolloff(y=audio, sr=sr, n_fft=frame_size, hop_length=hop_length)[0]
    
    # MFCC features (good for speaker characteristics)
    mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13, n_fft=frame_size, hop_length=hop_length)
    for i, mfcc in enumerate(mfccs):
        features[f'mfcc_{i+1}'] = mfcc
    
    # Pitch features
    try:
        f0, voiced_flag, _ = librosa.pyin(audio, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'), sr=sr, frame_length=frame_size, hop_length=hop_length)
        # Replace NaN values with 0
        f0 = np.nan_to_num(f0)
        features['pitch'] = f0
        features['voiced'] = voiced_flag.astype(float)
    except Exception:
        # Fallback if pitch extraction fails
        features['pitch'] = np.zeros_like(features['rms'])
        features['voiced'] = np.zeros_like(features['rms'])
    
    return features

def simple_energy_based_diarization(
    audio_path: str, 
    min_segment_duration: float = 2.0,
    energy_threshold: float = 0.01,
    pause_duration: float = 0.5,
    use_spectral_features: bool = True,  # Use spectral features for better speaker differentiation
    spectral_threshold: float = 0.5,   # Threshold for spectral change detection
    max_speakers: int = 2,  # Maximum number of speakers to detect
    min_speech_duration: float = 1.0  # Minimum speech duration in seconds
) -> List[Tuple[float, float, int]]:
    """
    Enhanced diarization that doesn't require HuggingFace authentication
    Uses energy detection, spectral features, and clustering for better speaker differentiation
    
    Args:
        audio_path: Path to audio file
        min_segment_duration: Minimum segment duration in seconds
        energy_threshold: Energy threshold for silence detection
        pause_duration: Pause duration in seconds to consider a new segment
        use_spectral_features: Whether to use spectral features for speaker differentiation
        spectral_threshold: Threshold for spectral change detection
        max_speakers: Maximum number of speakers to detect
        min_speech_duration: Minimum speech duration in seconds
        
    Returns:
        List of (start, end, speaker_id) tuples
    """
    try:
        logger.info(f"Processing audio file: {audio_path}")
        
        # Load audio
        audio, sr = librosa.load(audio_path, sr=16000)
        duration = len(audio) / sr
        logger.info(f"Audio duration: {duration:.2f} seconds")
        
        # Extract features
        frame_size = 1024
        hop_length = 512
        features = extract_audio_features(audio, sr, frame_size, hop_length)
        
        # Calculate time points for each frame
        times = librosa.times_like(features['rms'], sr=sr, hop_length=hop_length)
        
        # Voice activity detection based on energy
        is_speech = features['rms'] > energy_threshold
        
        # Find speech segments
        speech_segments = []
        in_speech = False
        speech_start = 0
        
        for i, speech in enumerate(is_speech):
            if speech and not in_speech:
                # Speech start
                speech_start = times[i]
                in_speech = True
            elif not speech and in_speech:
                # Speech end
                speech_end = times[i]
                if speech_end - speech_start >= min_speech_duration:
                    speech_segments.append((speech_start, speech_end))
                in_speech = False
        
        # Add final segment if still in speech
        if in_speech and times[-1] - speech_start >= min_speech_duration:
            speech_segments.append((speech_start, times[-1]))
        
        if not speech_segments:
            logger.warning("No speech segments found")
            # Return a single segment for the entire audio as fallback
            return [(0.0, duration, 0)]
            
        logger.info(f"Found {len(speech_segments)} speech segments")
        
        # Merge segments that are close together
        merged_segments = []
        current_start, current_end = speech_segments[0]
        
        for start, end in speech_segments[1:]:
            if start - current_end <= pause_duration:
                # Merge with current segment
                current_end = end
            else:
                # Add current segment and start a new one
                if current_end - current_start >= min_segment_duration:
                    merged_segments.append((current_start, current_end))
                current_start, current_end = start, end
        
        # Add the last segment
        if current_end - current_start >= min_segment_duration:
            merged_segments.append((current_start, current_end))
        
        logger.info(f"After merging: {len(merged_segments)} segments")
        
        # If not using spectral features or only one segment, return simple segments
        if not use_spectral_features or len(merged_segments) <= 1:
            return [(start, end, 0) for start, end in merged_segments]
        
        # Extract features for each segment for speaker clustering
        segment_features = []
        
        for start, end in merged_segments:
            # Convert time to frame indices
            start_idx = int(start * sr / hop_length)
            end_idx = int(end * sr / hop_length)
            
            # Ensure indices are within bounds
            start_idx = max(0, min(start_idx, len(times) - 1))
            end_idx = max(0, min(end_idx, len(times) - 1))
            
            if start_idx >= end_idx:
                continue
            
            # Extract segment features
            segment_feature_vector = []
            
            # Use key features for speaker differentiation
            for feature_name in ['spectral_centroid', 'spectral_bandwidth', 'spectral_rolloff', 
                               'mfcc_1', 'mfcc_2', 'mfcc_3', 'mfcc_4', 'pitch']:
                if feature_name in features:
                    # Get mean and std of feature in this segment
                    feature_mean = np.mean(features[feature_name][start_idx:end_idx])
                    feature_std = np.std(features[feature_name][start_idx:end_idx])
                    segment_feature_vector.extend([feature_mean, feature_std])
            
            segment_features.append(segment_feature_vector)
        
        # Perform speaker clustering if we have enough segments
        if len(segment_features) >= 2:
            try:
                # Normalize features
                scaler = StandardScaler()
                scaled_features = scaler.fit_transform(segment_features)
                
                # Reduce dimensionality if we have many features
                if scaled_features.shape[1] > 10:
                    pca = PCA(n_components=min(10, scaled_features.shape[0]))
                    scaled_features = pca.fit_transform(scaled_features)
                
                # Determine number of clusters (speakers)
                n_clusters = min(max_speakers, len(segment_features))
                
                # Perform clustering
                kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                labels = kmeans.fit_predict(scaled_features)
                
                logger.info(f"Clustered into {n_clusters} speakers")
                
                # Create final segments with speaker IDs
                final_segments = []
                for i, ((start, end), speaker_id) in enumerate(zip(merged_segments, labels)):
                    final_segments.append((start, end, int(speaker_id)))
                
                return final_segments
            except Exception as e:
                logger.error(f"Clustering failed: {e}")
                # Fall back to simple segments
                return [(start, end, 0) for start, end in merged_segments]
        else:
            # Not enough segments for clustering
            return [(start, end, 0) for start, end in merged_segments]
        
    except Exception as e:
        logger.error(f"Enhanced diarization failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Return a single segment for the entire audio as fallback
        try:
            duration = librosa.get_duration(path=audio_path)
            return [(0.0, duration, 0)]
        except:
            return [(0.0, 60.0, 0)]  # Arbitrary 60-second segment as last resort
