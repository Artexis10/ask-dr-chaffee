#!/usr/bin/env python3
"""
Complete transcript fetching pipeline with fallback strategies:
1. youtube-transcript-api (cheap, fast)
2. yt-dlp subtitles with proxy support
3. Mark for Whisper processing (optional)

All results are normalized and include provenance tracking.
"""

import os
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
import json
import re

# Third-party imports
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
    YT_TRANSCRIPT_AVAILABLE = True
except ImportError:
    YT_TRANSCRIPT_AVAILABLE = False

try:
    import webvtt
    WEBVTT_AVAILABLE = True
except ImportError:
    WEBVTT_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class TranscriptSegment:
    """Normalized transcript segment with timing and text."""
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str     # Transcript text
    
    @classmethod
    def from_youtube_transcript(cls, item: Dict[str, Any]) -> 'TranscriptSegment':
        """Create from youtube-transcript-api format."""
        start = float(item.get('start', 0))
        duration = float(item.get('duration', 0))
        text = item.get('text', '').strip()
        return cls(start=start, end=start + duration, text=text)
    
    @classmethod
    def from_vtt_caption(cls, caption) -> 'TranscriptSegment':
        """Create from webvtt caption object."""
        # Parse webvtt timestamp format (HH:MM:SS.mmm)
        start = cls._parse_vtt_timestamp(caption.start)
        end = cls._parse_vtt_timestamp(caption.end)
        
        # Clean text: remove newlines, extra spaces, and VTT formatting
        text = caption.text
        text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
        text = re.sub(r'\n+', ' ', text)     # Replace newlines with spaces
        text = re.sub(r'\s+', ' ', text)     # Normalize whitespace
        text = text.strip()
        
        return cls(start=start, end=end, text=text)
    
    @staticmethod
    def _parse_vtt_timestamp(timestamp: str) -> float:
        """Parse VTT timestamp to seconds."""
        # Format: HH:MM:SS.mmm or MM:SS.mmm
        parts = timestamp.split(':')
        if len(parts) == 3:  # HH:MM:SS.mmm
            hours, minutes, seconds = parts
            return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
        elif len(parts) == 2:  # MM:SS.mmm
            minutes, seconds = parts
            return float(minutes) * 60 + float(seconds)
        else:
            return 0.0


class TranscriptFetcher:
    """Complete transcript fetching pipeline with multiple strategies."""
    
    def __init__(self):
        """Initialize the transcript fetcher with environment configuration."""
        self.ytdlp_bin = os.getenv('YTDLP_BIN', 'yt-dlp')
        self.ytdlp_proxy = os.getenv('YTDLP_PROXY', '').strip()
        self.data_dir = Path(__file__).parent.parent / 'data' / 'subs'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"TranscriptFetcher initialized - yt-dlp: {self.ytdlp_bin}, proxy: {'***' if self.ytdlp_proxy else 'None'}")
    
    def fetch_transcript(
        self, 
        video_id: str, 
        prefer_langs: Tuple[str, ...] = ("en", "en-US", "en-GB")
    ) -> Tuple[Optional[List[TranscriptSegment]], Optional[str]]:
        """
        Fetch transcript using the complete pipeline.
        
        Args:
            video_id: YouTube video ID
            prefer_langs: Preferred language codes in order
            
        Returns:
            (segments, provenance) where provenance is 'yt_caption', 'yt_dlp', or None
        """
        logger.info(f"Fetching transcript for {video_id}")
        
        # Strategy 1: youtube-transcript-api (fastest, cheapest)
        segments = self._fetch_youtube_transcript_api(video_id, prefer_langs)
        if segments:
            logger.info(f"✅ Got transcript via youtube-transcript-api for {video_id} ({len(segments)} segments)")
            return segments, 'yt_caption'
        
        # Strategy 2: yt-dlp subtitles (with proxy support)
        segments = self._fetch_ytdlp_subtitles(video_id, prefer_langs)
        if segments:
            logger.info(f"✅ Got transcript via yt-dlp subtitles for {video_id} ({len(segments)} segments)")
            return segments, 'yt_dlp'
        
        # No transcript found
        logger.info(f"❌ No transcript found for {video_id} - mark for Whisper")
        return None, None
    
    def _fetch_youtube_transcript_api(
        self, 
        video_id: str, 
        prefer_langs: Tuple[str, ...]
    ) -> Optional[List[TranscriptSegment]]:
        """Fetch transcript using youtube-transcript-api."""
        if not YT_TRANSCRIPT_AVAILABLE:
            logger.debug("youtube-transcript-api not available, skipping")
            return None
        
        try:
            logger.debug(f"Trying youtube-transcript-api for {video_id}")
            # Use the new API directly
            api = YouTubeTranscriptApi()
            
            # Try to fetch with preferred languages
            try:
                fetched_transcript = api.fetch(video_id, languages=list(prefer_langs))
            except Exception:
                # If preferred languages fail, try English
                try:
                    fetched_transcript = api.fetch(video_id, languages=['en'])
                except Exception:
                    # If English fails, try without language restriction
                    fetched_transcript = api.fetch(video_id)
            
            # Convert to our format
            segments = []
            for snippet in fetched_transcript:
                segment = TranscriptSegment(
                    start_time=snippet.start,
                    end_time=snippet.start + snippet.duration,
                    text=snippet.text.strip()
                )
                segments.append(segment)
            
            # Filter out very short or empty segments
            segments = [seg for seg in segments if seg.text and len(seg.text.strip()) > 2]
            
            # Filter out non-verbal content
            segments = [seg for seg in segments if not any(
                marker in seg.text.lower() 
                for marker in ['[music]', '[applause]', '[laughter]', '[silence]']
            )]
            
            return segments if segments else None
                
        except (TranscriptsDisabled, VideoUnavailable) as e:
            logger.debug(f"YouTube transcript unavailable for {video_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching YouTube transcript for {video_id}: {e}")
            return None
        
        return None
    
    def _fetch_ytdlp_subtitles(
        self, 
        video_id: str, 
        prefer_langs: Tuple[str, ...]
    ) -> Optional[List[TranscriptSegment]]:
        """Fetch subtitles using yt-dlp with proxy support."""
        if not WEBVTT_AVAILABLE:
            logger.debug("webvtt library not available, skipping yt-dlp subtitles")
            return None
        
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            output_pattern = str(self.data_dir / f"{video_id}.%(ext)s")
            
            # Build yt-dlp command
            cmd = [
                self.ytdlp_bin,
                url,
                '--skip-download',
                '--write-auto-sub',
                '--sub-lang', 'en',
                '--sub-format', 'vtt/srt/best',
                '--convert-subs', 'vtt',
                '-o', output_pattern
            ]
            
            # Add proxy if configured
            if self.ytdlp_proxy:
                cmd.extend(['--proxy', self.ytdlp_proxy])
                logger.debug(f"Using proxy for yt-dlp: {self.ytdlp_proxy}")
            
            logger.debug(f"Running yt-dlp subtitle extraction: {' '.join(cmd)}")
            
            # Run yt-dlp
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.debug(f"yt-dlp failed for {video_id}: {result.stderr}")
                return None
            
            # Find the downloaded VTT file
            vtt_file = self.data_dir / f"{video_id}.en.vtt"
            if not vtt_file.exists():
                # Try without language suffix
                vtt_file = self.data_dir / f"{video_id}.vtt"
                if not vtt_file.exists():
                    logger.debug(f"No VTT file found for {video_id}")
                    return None
            
            # Parse VTT file
            segments = self._parse_vtt_file(vtt_file)
            
            # Clean up the VTT file
            try:
                vtt_file.unlink()
            except OSError:
                pass
            
            return segments
            
        except subprocess.TimeoutExpired:
            logger.warning(f"yt-dlp timeout for {video_id}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching yt-dlp subtitles for {video_id}: {e}")
            return None
    
    def _parse_vtt_file(self, vtt_file: Path) -> Optional[List[TranscriptSegment]]:
        """Parse VTT file into transcript segments."""
        try:
            captions = webvtt.read(str(vtt_file))
            segments = []
            
            for caption in captions:
                segment = TranscriptSegment.from_vtt_caption(caption)
                if segment.text and len(segment.text.strip()) > 2:
                    segments.append(segment)
            
            # Merge segments that are too close together (< 1 second apart)
            merged_segments = self._merge_close_segments(segments)
            
            # Filter out non-verbal content
            filtered_segments = [seg for seg in merged_segments if not any(
                marker in seg.text.lower() 
                for marker in ['[music]', '[applause]', '[laughter]', '[silence]']
            )]
            
            return filtered_segments if filtered_segments else None
            
        except Exception as e:
            logger.warning(f"Error parsing VTT file {vtt_file}: {e}")
            return None
    
    def _merge_close_segments(
        self, 
        segments: List[TranscriptSegment], 
        gap_threshold: float = 1.0
    ) -> List[TranscriptSegment]:
        """Merge segments that are very close together."""
        if not segments:
            return segments
        
        merged = [segments[0]]
        
        for segment in segments[1:]:
            last_segment = merged[-1]
            
            # If segments are close together, merge them
            if segment.start - last_segment.end <= gap_threshold:
                merged[-1] = TranscriptSegment(
                    start=last_segment.start,
                    end=segment.end,
                    text=f"{last_segment.text} {segment.text}"
                )
            else:
                merged.append(segment)
        
        return merged


# Factory function for easy import
def create_transcript_fetcher() -> TranscriptFetcher:
    """Create a configured TranscriptFetcher instance."""
    return TranscriptFetcher()


def main():
    """CLI for testing transcript fetching."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test transcript fetching pipeline')
    parser.add_argument('video_id', help='YouTube video ID to test')
    parser.add_argument('--langs', nargs='+', default=['en', 'en-US'], 
                       help='Preferred languages')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    fetcher = create_transcript_fetcher()
    segments, provenance = fetcher.fetch_transcript(args.video_id, tuple(args.langs))
    
    if segments:
        print(f"\n✅ Transcript found via {provenance} ({len(segments)} segments):")
        for i, segment in enumerate(segments[:5]):  # Show first 5
            print(f"  {segment.start:.1f}s - {segment.end:.1f}s: {segment.text}")
        if len(segments) > 5:
            print(f"  ... and {len(segments) - 5} more segments")
    else:
        print(f"\n❌ No transcript found for {args.video_id}")


if __name__ == '__main__':
    main()
