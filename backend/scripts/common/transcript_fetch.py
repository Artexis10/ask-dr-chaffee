#!/usr/bin/env python3
"""
Robust transcript fetching with multiple fallback strategies
"""

import logging
import tempfile
import subprocess
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# Initialize logger first to avoid reference before assignment
logger = logging.getLogger(__name__)

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

# Import API-based transcript fetcher if available
try:
    from .transcript_api import YouTubeTranscriptAPI as YouTubeDataAPI
    YOUTUBE_DATA_API_AVAILABLE = True
except ImportError:
    logger.warning("YouTube Data API module not available. Install google-api-python-client for better performance.")
    YOUTUBE_DATA_API_AVAILABLE = False

try:
    import faster_whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

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
    
    def __init__(self, yt_dlp_path: str = "yt-dlp", whisper_model: str = "small.en", ffmpeg_path: str = None, proxies: dict = None, api_key: str = None):
        self.yt_dlp_path = yt_dlp_path
        self.whisper_model = whisper_model
        self._whisper_model_cache = None
        self.ffmpeg_path = ffmpeg_path
        self.proxies = proxies
        self.api_key = api_key or os.getenv('YOUTUBE_API_KEY')
        self._api_client = None
    
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
    
    def _get_api_client(self):
        """Get or create YouTube Data API client"""
        if self._api_client is None and self.api_key and YOUTUBE_DATA_API_AVAILABLE:
            try:
                self._api_client = YouTubeDataAPI(self.api_key)
                logger.info(f"Successfully initialized YouTube Data API client")
            except Exception as e:
                logger.error(f"Failed to initialize YouTube Data API client: {e}")
                return None
        elif not YOUTUBE_DATA_API_AVAILABLE:
            logger.warning("YouTube Data API module not available - cannot use API for transcripts")
        elif not self.api_key:
            logger.warning("No YouTube API key provided - cannot use API for transcripts")
        return self._api_client
    
    def fetch_youtube_transcript(self, video_id: str, languages: List[str] = None) -> Optional[List[TranscriptSegment]]:
        """Fetch transcript using YouTube's built-in captions"""
        if languages is None:
            languages = ['en', 'en-US', 'en-GB']
        
        logger.debug(f"Fetching YouTube transcript for {video_id}")
        
        # ALWAYS try YouTube Data API first if API key is provided
        if self.api_key:
            api_client = self._get_api_client()
            if api_client:
                try:
                    logger.info(f"Fetching transcript via YouTube Data API for {video_id}")
                    segments = api_client.get_transcript_segments(video_id, language_code=languages[0])
                    if segments:
                        logger.info(f"Successfully fetched transcript via YouTube Data API for {video_id}")
                        return segments
                    logger.info(f"No transcript found via YouTube Data API for {video_id}")
                except Exception as e:
                    logger.warning(f"Error fetching transcript via YouTube Data API: {e}")
            else:
                logger.warning(f"YouTube Data API client initialization failed despite having API key")
        else:
            logger.warning(f"No YouTube API key provided - cannot use YouTube Data API")
        
        # Only fall back to YouTube Transcript API if Data API failed or is unavailable
        logger.info(f"Falling back to YouTube Transcript API for {video_id}")
        try:
            # Create API instance with proxy support if configured
            api = YouTubeTranscriptApi()
            
            # Try to fetch transcript with preferred languages
            if self.proxies:
                # Use proxy if provided
                import requests
                from youtube_transcript_api.formatters import JSONFormatter
                
                # Create a session with proxies
                session = requests.Session()
                session.proxies.update(self.proxies)
                
                # Use the session to fetch the transcript
                try:
                    # First try with proxies
                    fetched_transcript = api.fetch(video_id, languages=languages, proxies=self.proxies)
                except Exception as e:
                    logger.warning(f"Failed to fetch with proxies: {e}, trying without proxies")
                    fetched_transcript = api.fetch(video_id, languages=languages)
            else:
                # Standard fetch without proxies
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
            "--no-warnings"
        ]
        
        # Add ffmpeg location if specified
        if self.ffmpeg_path:
            cmd.extend(["--ffmpeg-location", self.ffmpeg_path])
            
        # Add video URL
        cmd.append(f"https://www.youtube.com/watch?v={video_id}")
        
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
    parser.add_argument('--ffmpeg-path', help='Path to ffmpeg executable')
    parser.add_argument('--proxy', help='HTTP/HTTPS proxy to use for YouTube requests')
    parser.add_argument('--api-key', help='YouTube Data API key for transcript fetching')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    # Setup proxies if provided
    proxies = None
    if args.proxy:
        proxies = {
            'http': args.proxy,
            'https': args.proxy
        }
    
    fetcher = TranscriptFetcher(
        whisper_model=args.whisper_model, 
        ffmpeg_path=args.ffmpeg_path,
        proxies=proxies,
        api_key=args.api_key
    )
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
