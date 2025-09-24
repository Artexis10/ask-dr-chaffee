#!/usr/bin/env python3
"""
Simple diarization module that doesn't require HuggingFace authentication
"""

import numpy as np
import librosa
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

def simple_energy_based_diarization(
    audio_path: str, 
    min_segment_duration: float = 3.0,
    energy_threshold: float = 0.01,
    pause_duration: float = 0.5
) -> List[Tuple[float, float, int]]:
    """
    Simple energy-based diarization that doesn't require HuggingFace authentication
    
    Args:
        audio_path: Path to audio file
        min_segment_duration: Minimum segment duration in seconds
        energy_threshold: Energy threshold for silence detection
        pause_duration: Pause duration in seconds to consider a new segment
        
    Returns:
        List of (start, end, speaker_id) tuples
    """
    try:
        # Load audio
        audio, sr = librosa.load(audio_path, sr=16000)
        
        # Calculate energy
        energy = librosa.feature.rms(y=audio, frame_length=1024, hop_length=512)[0]
        times = librosa.times_like(energy, sr=sr, hop_length=512)
        
        # Find segments based on energy
        is_speech = energy > energy_threshold
        
        # Find segment boundaries
        boundaries = np.where(np.diff(is_speech.astype(int)) != 0)[0]
        
        if len(boundaries) == 0:
            # No boundaries found, treat the whole audio as one segment
            if is_speech[0]:
                return [(0.0, len(audio) / sr, 0)]
            else:
                return []
        
        # Convert boundaries to time
        boundary_times = times[boundaries]
        
        # Create segments
        segments = []
        speaker_id = 0
        
        # Add first segment if it starts with speech
        if is_speech[0]:
            start_time = 0.0
            if len(boundary_times) > 0:
                end_time = boundary_times[0]
                if end_time - start_time >= min_segment_duration:
                    segments.append((start_time, end_time, speaker_id))
        
        # Process remaining segments
        for i in range(0, len(boundary_times) - 1, 2):
            if i + 1 >= len(boundary_times):
                break
                
            start_time = boundary_times[i]
            end_time = boundary_times[i + 1]
            
            # Only add if segment is long enough
            if end_time - start_time >= min_segment_duration:
                segments.append((start_time, end_time, speaker_id))
                
                # If there's a long pause, increment speaker ID
                if i + 2 < len(boundary_times) and boundary_times[i + 2] - end_time > pause_duration:
                    speaker_id += 1
        
        # Add last segment if it ends with speech
        if len(boundary_times) > 0 and is_speech[-1]:
            start_time = boundary_times[-1]
            end_time = times[-1]
            if end_time - start_time >= min_segment_duration:
                segments.append((start_time, end_time, speaker_id))
        
        logger.info(f"Simple diarization found {len(segments)} segments with {speaker_id + 1} speakers")
        return segments
        
    except Exception as e:
        logger.error(f"Simple diarization failed: {e}")
        # Return a single segment for the entire audio as fallback
        try:
            duration = librosa.get_duration(path=audio_path)
            return [(0.0, duration, 0)]
        except:
            return [(0.0, 60.0, 0)]  # Arbitrary 60-second segment as last resort
