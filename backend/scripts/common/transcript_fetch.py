#!/usr/bin/env python3
"""
Robust transcript fetching with multiple fallback strategies
"""

import logging
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

try:
    import faster_whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

logger = logging.getLogger(__name__)

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

class TranscriptFetcher:
    """Fetch transcripts with multiple fallback strategies"""
    
    def __init__(self, yt_dlp_path: str = "yt-dlp", whisper_model: str = "small.en"):
        self.yt_dlp_path = yt_dlp_path
        self.whisper_model = whisper_model
        self._whisper_model_cache = None
    
    def _get_whisper_model(self):
        """Lazy load Whisper model"""
        if not WHISPER_AVAILABLE:
            raise ImportError("faster-whisper not available. Install with: pip install faster-whisper")
        
        if self._whisper_model_cache is None:
            logger.info(f"Loading Whisper model: {self.whisper_model}")
            self._whisper_model_cache = faster_whisper.WhisperModel(
                self.whisper_model, 
                device="cpu",  # Use CPU for compatibility
                compute_type="int8"  # Optimize memory usage
            )
        return self._whisper_model_cache
    
    def fetch_youtube_transcript(self, video_id: str, languages: List[str] = None) -> Optional[List[TranscriptSegment]]:
        """Fetch transcript using YouTube's built-in captions"""
        if languages is None:
            languages = ['en', 'en-US', 'en-GB']
        
        logger.debug(f"Fetching YouTube transcript for {video_id}")
        
        try:
            # Create API instance
            api = YouTubeTranscriptApi()
            
            # Try to fetch transcript with preferred languages
            fetched_transcript = api.fetch(video_id, languages=languages)
            logger.debug(f"Found transcript for {video_id}")
            
            # Convert fetched transcript to our format
            segments = []
            for item in fetched_transcript:
                segment = TranscriptSegment.from_youtube_transcript(item)
                if segment.text and segment.text.strip() != '[Music]':  # Filter out music markers
                    segments.append(segment)
            
            return segments
            
        except (TranscriptsDisabled, VideoUnavailable) as e:
            logger.debug(f"YouTube transcript not available for {video_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching YouTube transcript for {video_id}: {e}")
            return None
    
    def download_audio(self, video_id: str, output_dir: Path = None) -> Optional[Path]:
        """Download audio using yt-dlp"""
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir())
        
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{video_id}.m4a"
        
        logger.debug(f"Downloading audio for {video_id}")
        
        cmd = [
            self.yt_dlp_path,
            "-x",  # Extract audio
            "--audio-format", "m4a",
            "--audio-quality", "0",  # Best quality
            "-o", str(output_file.with_suffix('.%(ext)s')),
            "--no-warnings",
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"yt-dlp failed for {video_id}: {result.stderr}")
                return None
            
            # Check if file was created
            if output_file.exists():
                logger.debug(f"Audio downloaded: {output_file}")
                return output_file
            else:
                logger.error(f"Audio file not found after download: {output_file}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Audio download timeout for {video_id}")
            return None
        except Exception as e:
            logger.error(f"Error downloading audio for {video_id}: {e}")
            return None
    
    def transcribe_with_whisper(self, audio_path: Path) -> Optional[List[TranscriptSegment]]:
        """Transcribe audio using Whisper"""
        if not WHISPER_AVAILABLE:
            logger.error("Whisper not available for transcription")
            return None
        
        logger.debug(f"Transcribing with Whisper: {audio_path}")
        
        try:
            model = self._get_whisper_model()
            
            # Transcribe with word-level timestamps
            segments, info = model.transcribe(
                str(audio_path),
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(min_silence_duration_ms=1000)
            )
            
            # Convert to normalized format
            transcript_segments = []
            for segment in segments:
                ts = TranscriptSegment.from_whisper_segment(segment)
                if ts.text and len(ts.text.strip()) > 1:  # Filter very short segments
                    transcript_segments.append(ts)
            
            logger.info(f"Whisper transcribed {len(transcript_segments)} segments from {audio_path}")
            return transcript_segments
            
        except Exception as e:
            logger.error(f"Whisper transcription failed for {audio_path}: {e}")
            return None
    
    def fetch_transcript(
        self, 
        video_id: str, 
        max_duration_s: Optional[int] = None,
        force_whisper: bool = False,
        cleanup_audio: bool = True
    ) -> Tuple[Optional[List[TranscriptSegment]], str]:
        """
        Fetch transcript with fallback strategy
        
        Returns:
            (segments, method) where method is 'youtube' or 'whisper'
        """
        # Try YouTube transcript first unless forced to use Whisper
        if not force_whisper:
            youtube_segments = self.fetch_youtube_transcript(video_id)
            if youtube_segments:
                return youtube_segments, 'youtube'
        
        # Check duration limit for Whisper fallback
        if max_duration_s is not None:
            # We would need duration info passed in or fetched here
            # For now, assume caller has already checked duration
            pass
        
        # Fallback to Whisper transcription
        logger.info(f"Falling back to Whisper transcription for {video_id}")
        
        # Download audio
        audio_path = self.download_audio(video_id)
        if not audio_path:
            return None, 'failed'
        
        try:
            # Transcribe with Whisper
            whisper_segments = self.transcribe_with_whisper(audio_path)
            
            if whisper_segments:
                return whisper_segments, 'whisper'
            else:
                return None, 'failed'
                
        finally:
            # Cleanup audio file
            if cleanup_audio and audio_path and audio_path.exists():
                try:
                    audio_path.unlink()
                    logger.debug(f"Cleaned up audio file: {audio_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup audio file {audio_path}: {e}")

def main():
    """CLI for testing transcript fetching"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch video transcript')
    parser.add_argument('video_id', help='YouTube video ID')
    parser.add_argument('--whisper-model', default='small.en', help='Whisper model size')
    parser.add_argument('--force-whisper', action='store_true', help='Skip YouTube transcript')
    parser.add_argument('--max-duration', type=int, help='Max duration for Whisper fallback')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    fetcher = TranscriptFetcher(whisper_model=args.whisper_model)
    segments, method = fetcher.fetch_transcript(
        args.video_id,
        max_duration_s=args.max_duration,
        force_whisper=args.force_whisper
    )
    
    if segments:
        print(f"\nTranscript fetched using {method} ({len(segments)} segments):")
        for i, segment in enumerate(segments[:5]):  # Show first 5
            print(f"  {segment.start:.1f}s - {segment.end:.1f}s: {segment.text}")
        if len(segments) > 5:
            print(f"  ... and {len(segments) - 5} more segments")
    else:
        print("Failed to fetch transcript")

if __name__ == '__main__':
    main()
