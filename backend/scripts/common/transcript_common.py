#!/usr/bin/env python3
"""
Common definitions for transcript processing to avoid circular imports
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class TranscriptSegment:
    """Normalized transcript segment"""
    start: float
    end: float  
    text: str
    
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
        return cls(
            start=segment.start,
            end=segment.end,
            text=segment.text.strip()
        )
