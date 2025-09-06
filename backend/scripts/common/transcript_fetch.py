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

# Initialize logger first to avoid reference before assignment
logger = logging.getLogger(__name__)

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

# Handle imports differently when run as script vs module
if __name__ == '__main__':
    # When run as script, use absolute imports
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from backend.scripts.common.transcript_common import TranscriptSegment
    try:
        from backend.scripts.common.transcript_api import YouTubeTranscriptAPI as YouTubeDataAPI
        YOUTUBE_DATA_API_AVAILABLE = True
    except ImportError:
        logger.warning("YouTube Data API module not available. Install google-api-python-client for better performance.")
        YOUTUBE_DATA_API_AVAILABLE = False
else:
    # When imported as module, use relative imports
    from .transcript_common import TranscriptSegment
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

class TranscriptFetcher:
    """Fetch transcripts with multiple fallback strategies"""
    
    def __init__(self, yt_dlp_path: str = "yt-dlp", whisper_model: str = "small.en", ffmpeg_path: str = None, proxies: dict = None, api_key: str = None, credentials_path: str = None):
        self.yt_dlp_path = yt_dlp_path
        self.whisper_model = whisper_model
        self._whisper_model_cache = None
        self.ffmpeg_path = ffmpeg_path
        self.proxies = proxies
        self.api_key = api_key or os.getenv('YOUTUBE_API_KEY')
        self.credentials_path = credentials_path or os.getenv('YOUTUBE_CREDENTIALS_PATH')
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
        if self._api_client is None and YOUTUBE_DATA_API_AVAILABLE:
            try:
                # Try OAuth2 first, then fall back to API key
                self._api_client = YouTubeDataAPI(
                    credentials_path=self.credentials_path,
                    api_key=self.api_key
                )
                logger.info(f"Successfully initialized YouTube Data API client")
            except Exception as e:
                logger.error(f"Failed to initialize YouTube Data API client: {e}")
                return None
        elif not YOUTUBE_DATA_API_AVAILABLE:
            logger.warning("YouTube Data API module not available - cannot use API for transcripts")
        elif not self.credentials_path and not self.api_key:
            logger.warning("No YouTube credentials or API key provided - cannot use API for transcripts")
        return self._api_client
    
    def fetch_youtube_transcript(self, video_id: str, languages: List[str] = None) -> Optional[List[TranscriptSegment]]:
        """Fetch transcript using YouTube's built-in captions"""
        if languages is None:
            languages = ['en', 'en-US', 'en-GB']
        
        logger.debug(f"Fetching YouTube transcript for {video_id}")
        
        # Try YouTube Data API first if OAuth2 credentials available (requires channel permissions)
        if self.credentials_path:
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
        
        logger.debug(f"Using YouTube Transcript API as fallback for {video_id}")
        
        # Use YouTube Transcript API for third-party videos
        try:
            # Create API instance with proxy support if configured
            api = YouTubeTranscriptApi()
            
            # Add proxy support if configured
            if self.proxies:
                logger.info(f"Using proxy for YouTube Transcript API: {self.proxies}")
                
                try:
                    # Handle different proxy formats
                    proxy_dict = self.proxies
                    if isinstance(self.proxies, str):
                        # Convert string proxy to dict format
                        proxy_dict = {
                            'http': self.proxies,
                            'https': self.proxies
                        }
                    
                    # Monkey patch requests for youtube_transcript_api
                    import youtube_transcript_api._api
                    original_get = youtube_transcript_api._api.requests.get
                    
                    def proxied_get(*args, **kwargs):
                        kwargs['proxies'] = proxy_dict
                        kwargs['timeout'] = 30  # Add timeout for proxy requests
                        return original_get(*args, **kwargs)
                    
                    youtube_transcript_api._api.requests.get = proxied_get
                    
                    # Get transcript with proxy
                    transcript_list = api.list_transcripts(video_id)
                    transcript = None
                    
                    # Try preferred languages
                    for lang in languages:
                        try:
                            transcript = transcript_list.find_transcript([lang])
                            break
                        except:
                            continue
                    
                    if not transcript:
                        transcript = transcript_list.find_generated_transcript(['en'])
                    
                    if transcript:
                        transcript_data = transcript.fetch()
                        segments = [TranscriptSegment.from_youtube_transcript(item) for item in transcript_data]
                        # Filter out non-verbal content
                        segments = [seg for seg in segments if not any(marker in seg.text.lower() for marker in ['[music]', '[applause]', '[laughter]'])]
                        
                        # Restore original function
                        youtube_transcript_api._api.requests.get = original_get
                        
                        logger.info(f"Successfully fetched transcript with proxy for {video_id} ({len(segments)} segments)")
                        return segments
                    
                    # Restore original function
                    youtube_transcript_api._api.requests.get = original_get
                    
                except Exception as e:
                    logger.warning(f"Proxy-based transcript fetch failed: {e}")
                    # Restore original function in case of error
                    try:
                        youtube_transcript_api._api.requests.get = original_get
                    except:
                        pass
                    # Continue without proxy   
            else:
                # Standard fetch without proxies
                transcript_list = api.list_transcripts(video_id)
                transcript = None
                
                # Try preferred languages
                for lang in languages:
                    try:
                        transcript = transcript_list.find_transcript([lang])
                        break
                    except:
                        continue
                
                if not transcript:
                    transcript = transcript_list.find_generated_transcript(['en'])
                
                if transcript:
                    transcript_data = transcript.fetch()
                    segments = [TranscriptSegment.from_youtube_transcript(item) for item in transcript_data]
                    # Filter out non-verbal content
                    segments = [seg for seg in segments if not any(marker in seg.text.lower() for marker in ['[music]', '[applause]', '[laughter]'])]
                    
                    logger.info(f"Successfully fetched transcript for {video_id} ({len(segments)} segments)")
                    return segments
            
            logger.debug(f"YouTube transcript not available for {video_id}")
            return None
        
        except (TranscriptsDisabled, VideoUnavailable) as e:
            logger.debug(f"YouTube transcript not available for {video_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching YouTube transcript for {video_id}: {e}")
            return None
    
    def fetch_whisper_transcript(self, video_id: str) -> Optional[List[TranscriptSegment]]:
        """Fetch transcript using Whisper after downloading audio with yt-dlp"""
        if not WHISPER_AVAILABLE:
            logger.error("Whisper not available for transcription")
            return None
            
        logger.info(f"Downloading audio for Whisper transcription: {video_id}")
        
        # Download audio using yt-dlp
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / f"{video_id}.%(ext)s"
            
            cmd = [
                self.yt_dlp_path,
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '0',  # Best quality
                '--no-playlist',
                '-o', str(output_path),
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            
            # Add ffmpeg path if specified
            if self.ffmpeg_path:
                cmd.extend(['--ffmpeg-location', self.ffmpeg_path])
            
            # Add proxy support for yt-dlp
            if self.proxies:
                # yt-dlp proxy format
                if isinstance(self.proxies, dict):
                    if 'http' in self.proxies:
                        cmd.extend(['--proxy', self.proxies['http']])
                    elif 'https' in self.proxies:
                        cmd.extend(['--proxy', self.proxies['https']])
                elif isinstance(self.proxies, str):
                    cmd.extend(['--proxy', self.proxies])
                
                logger.info(f"Using proxy for yt-dlp: {self.proxies}")
            
            try:
                logger.debug(f"Running yt-dlp command: {' '.join(cmd)}")
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
                
                # Find the downloaded audio file
                audio_files = list(Path(temp_dir).glob(f"{video_id}.*"))
                if not audio_files:
                    logger.error(f"No audio file found after download for {video_id}")
                    return None
                
                audio_file = audio_files[0]
                logger.debug(f"Audio downloaded: {audio_file}")
                
                # Transcribe with Whisper
                return self.transcribe_with_whisper(audio_file)
                
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
