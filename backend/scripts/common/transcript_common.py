#!/usr/bin/env python3
"""
Common definitions for transcript processing to avoid circular imports
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

def ensure_str(text):
    """Ensure text is a string"""
    if text is None:
        return ""
    return str(text).strip()

@dataclass
class TranscriptSegment:
    """Normalized transcript segment with speaker attribution"""
    start: float
    end: float  
    text: str
    speaker_label: Optional[str] = None
    speaker_confidence: Optional[float] = None
    avg_logprob: Optional[float] = None
    compression_ratio: Optional[float] = None
    no_speech_prob: Optional[float] = None
    temperature_used: Optional[float] = None
    re_asr: bool = False
    is_overlap: bool = False
    needs_refinement: bool = False
    
    @classmethod
    def from_youtube_transcript(cls, data) -> 'TranscriptSegment':
        """Create from YouTube transcript API format (FetchedTranscriptSnippet or dict)"""
        # Handle both dict format and FetchedTranscriptSnippet object
        if hasattr(data, 'start'):
            return cls(
                start=data.start,
                end=data.start + data.duration,
                text=data.text.strip()
            )
        else:
            return cls(
                start=data['start'],
                end=data['start'] + data['duration'],
                text=data['text'].strip()
            )
    
    @classmethod
    def from_whisper_segment(cls, segment) -> 'TranscriptSegment':
        """Create from Whisper segment object"""
        # Ensure text is a proper string (handle bytes on Windows)
        text_value = segment.text
        if isinstance(text_value, bytes):
            try:
                text_value = text_value.decode('utf-8', errors='replace')
            except Exception:
                text_value = str(text_value)
        else:
            text_value = str(text_value)
        text_value = text_value.strip()
        return cls(
            start=segment.start,
            end=segment.end,
            text=text_value
        )
