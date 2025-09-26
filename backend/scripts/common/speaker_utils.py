#!/usr/bin/env python3
"""
Speaker profile utilities for Chaffee-aware diarization and attribution
Implements hysteresis-based speaker labeling with overlap handling
"""

import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class SpeakerSegment:
    """Speaker segment with attribution metadata"""
    start: float
    end: float
    speaker_id: str  # From diarization (SPEAKER_00, SPEAKER_01, etc.)
    speaker_label: str  # CH, GUEST, G1, G2
    speaker_conf: float  # Cosine similarity score
    text: Optional[str] = None
    is_overlap: bool = False
    needs_refinement: bool = False

@dataclass
class ChaffeeProfile:
    """Chaffee speaker profile with thresholds"""
    embedding: np.ndarray
    threshold_hi: float = 0.75
    threshold_lo: float = 0.68
    min_runs: int = 2
    
    @classmethod
    def load_from_file(cls, profile_path: str) -> 'ChaffeeProfile':
        """Load Chaffee profile from file"""
        try:
            if profile_path.endswith('.json'):
                with open(profile_path, 'r') as f:
                    data = json.load(f)
                    embedding = np.array(data['embedding'])
                    return cls(
                        embedding=embedding,
                        threshold_hi=data.get('threshold_hi', 0.75),
                        threshold_lo=data.get('threshold_lo', 0.68),
                        min_runs=data.get('min_runs', 2)
                    )
            elif profile_path.endswith('.npy'):
                embedding = np.load(profile_path)
                return cls(embedding=embedding)
            else:
                raise ValueError(f"Unsupported profile format: {profile_path}")
        except Exception as e:
            logger.error(f"Failed to load Chaffee profile from {profile_path}: {e}")
            raise

class SpeakerProfiler:
    """Speaker profiling with Chaffee-aware hysteresis and overlap handling"""
    
    def __init__(self, 
                 chaffee_profile: Optional[ChaffeeProfile] = None,
                 ch_hi: float = 0.75,
                 ch_lo: float = 0.68,
                 min_runs: int = 2,
                 overlap_split_ms: int = 300):
        
        self.chaffee_profile = chaffee_profile
        self.ch_hi = ch_hi
        self.ch_lo = ch_lo
        self.min_runs = min_runs
        self.overlap_split_ms = overlap_split_ms / 1000.0  # Convert to seconds
        
        # State for hysteresis
        self.current_state = "UNKNOWN"
        self.consecutive_count = 0
        
        logger.info(f"SpeakerProfiler initialized: CH_HI={ch_hi}, CH_LO={ch_lo}, MIN_RUNS={min_runs}")
    
    def compute_speaker_similarity(self, speaker_embedding: np.ndarray) -> float:
        """Compute cosine similarity with Chaffee profile"""
        if self.chaffee_profile is None:
            return 0.0
        
        # Normalize embeddings
        norm_chaffee = self.chaffee_profile.embedding / np.linalg.norm(self.chaffee_profile.embedding)
        norm_speaker = speaker_embedding / np.linalg.norm(speaker_embedding)
        
        # Cosine similarity
        similarity = np.dot(norm_chaffee, norm_speaker)
        return float(similarity)
    
    def apply_hysteresis_labeling(self, segments: List[Dict[str, Any]]) -> List[SpeakerSegment]:
        """Apply hysteresis-based speaker labeling to segments"""
        labeled_segments = []
        
        # Reset state for new sequence
        self.current_state = "UNKNOWN"
        self.consecutive_count = 0
        
        for i, segment in enumerate(segments):
            # Get speaker similarity (if available from existing diarization)
            speaker_conf = segment.get('speaker_confidence', 0.0)
            
            # Apply hysteresis logic
            if self.current_state == "UNKNOWN" or self.current_state == "GUEST":
                if speaker_conf >= self.ch_hi:
                    self.consecutive_count += 1
                    if self.consecutive_count >= self.min_runs:
                        self.current_state = "CH"
                        speaker_label = "CH"
                    else:
                        speaker_label = "GUEST"  # Still transitioning
                else:
                    self.consecutive_count = 0
                    speaker_label = "GUEST"
            
            elif self.current_state == "CH":
                if speaker_conf <= self.ch_lo:
                    self.consecutive_count += 1
                    if self.consecutive_count >= self.min_runs:
                        self.current_state = "GUEST"
                        speaker_label = "GUEST"
                    else:
                        speaker_label = "CH"  # Still transitioning
                else:
                    self.consecutive_count = 0
                    speaker_label = "CH"
            else:
                speaker_label = "GUEST"
            
            # Check for overlap
            is_overlap = self._detect_overlap(segment, segments, i)
            
            labeled_segment = SpeakerSegment(
                start=segment['start'],
                end=segment['end'],
                speaker_id=segment.get('speaker', 'SPEAKER_00'),
                speaker_label=speaker_label,
                speaker_conf=speaker_conf,
                text=segment.get('text', ''),
                is_overlap=is_overlap
            )
            
            labeled_segments.append(labeled_segment)
        
        logger.info(f"Applied hysteresis labeling to {len(labeled_segments)} segments")
        return labeled_segments
    
    def _detect_overlap(self, current_segment: Dict[str, Any], 
                       all_segments: List[Dict[str, Any]], 
                       current_index: int) -> bool:
        """Detect if segment has speaker overlap"""
        current_start = current_segment['start']
        current_end = current_segment['end']
        
        # Check adjacent segments for overlap
        for i, other_segment in enumerate(all_segments):
            if i == current_index:
                continue
            
            other_start = other_segment['start']
            other_end = other_segment['end']
            
            # Calculate overlap
            overlap_start = max(current_start, other_start)
            overlap_end = min(current_end, other_end)
            overlap_duration = max(0, overlap_end - overlap_start)
            
            if overlap_duration > 0.3:  # 300ms overlap threshold
                return True
        
        return False
    
    def split_overlap_segments(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """Split overlapping segments into sub-windows per speaker"""
        split_segments = []
        
        for segment in segments:
            if segment.is_overlap and (segment.end - segment.start) > self.overlap_split_ms:
                # Split into smaller windows
                window_duration = self.overlap_split_ms
                current_start = segment.start
                
                while current_start < segment.end:
                    window_end = min(current_start + window_duration, segment.end)
                    
                    split_segment = SpeakerSegment(
                        start=current_start,
                        end=window_end,
                        speaker_id=segment.speaker_id,
                        speaker_label=segment.speaker_label,
                        speaker_conf=segment.speaker_conf,
                        text=segment.text,
                        is_overlap=True,
                        needs_refinement=True  # Flag for potential refinement
                    )
                    
                    split_segments.append(split_segment)
                    current_start = window_end
            else:
                split_segments.append(segment)
        
        logger.info(f"Split overlap segments: {len(segments)} -> {len(split_segments)}")
        return split_segments
    
    def merge_adjacent_segments(self, segments: List[SpeakerSegment], 
                               max_gap: float = 0.3, 
                               max_duration: float = 30.0) -> List[SpeakerSegment]:
        """Merge adjacent same-speaker segments for efficiency"""
        if not segments:
            return segments
        
        merged_segments = []
        current_segment = segments[0]
        
        for next_segment in segments[1:]:
            # Check if segments can be merged
            gap = next_segment.start - current_segment.end
            same_speaker = (current_segment.speaker_label == next_segment.speaker_label)
            within_duration = (next_segment.end - current_segment.start) <= max_duration
            
            if same_speaker and gap <= max_gap and within_duration:
                # Merge segments
                current_segment = SpeakerSegment(
                    start=current_segment.start,
                    end=next_segment.end,
                    speaker_id=current_segment.speaker_id,
                    speaker_label=current_segment.speaker_label,
                    speaker_conf=max(current_segment.speaker_conf, next_segment.speaker_conf),
                    text=f"{current_segment.text} {next_segment.text}".strip(),
                    is_overlap=current_segment.is_overlap or next_segment.is_overlap,
                    needs_refinement=current_segment.needs_refinement or next_segment.needs_refinement
                )
            else:
                # Cannot merge, add current and start new
                merged_segments.append(current_segment)
                current_segment = next_segment
        
        # Add final segment
        merged_segments.append(current_segment)
        
        logger.info(f"Merged adjacent segments: {len(segments)} -> {len(merged_segments)}")
        return merged_segments

def load_chaffee_profile(profile_path: str) -> Optional[ChaffeeProfile]:
    """Load Chaffee profile from file path"""
    if not profile_path or not os.path.exists(profile_path):
        logger.warning(f"Chaffee profile not found: {profile_path}")
        return None
    
    try:
        return ChaffeeProfile.load_from_file(profile_path)
    except Exception as e:
        logger.error(f"Failed to load Chaffee profile: {e}")
        return None

def create_speaker_aware_prompt(speaker_label: str, base_prompt: str = "") -> str:
    """Create speaker-aware initial prompt for Whisper"""
    if speaker_label == "CH":
        # Rich domain prompt for Chaffee
        chaffee_lexicon = (
            "ketogenesis linoleic acid LDL statins seed oils DHA EPA taurine "
            "oxalates gout uric acid mTOR autoimmunity cholecystectomy carnivore "
            "nutrition metabolism insulin resistance inflammation"
        )
        return f"{base_prompt} {chaffee_lexicon}".strip()
    else:
        # Minimal prompt for guests
        return base_prompt
