#!/usr/bin/env python3
"""
Robust transcript fetching with multiple fallback strategies
"""

import logging
import tempfile
import subprocess
import os
import re
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
    from backend.scripts.common.downloader import AudioDownloader, AudioPreprocessingConfig
    try:
        from backend.scripts.common.transcript_api import YouTubeTranscriptAPI as YouTubeDataAPI
        YOUTUBE_DATA_API_AVAILABLE = True
    except ImportError:
        logger.warning("YouTube Data API module not available. Install google-api-python-client for better performance.")
else:
    # When imported as module, use relative imports
    from .transcript_common import TranscriptSegment
    from .downloader import AudioDownloader, AudioPreprocessingConfig

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, VideoUnavailable, NoTranscriptFound
    YOUTUBE_TRANSCRIPT_AVAILABLE = True
except ImportError:
    YOUTUBE_TRANSCRIPT_AVAILABLE = False
    logger.warning("youtube-transcript-api not available. Install with: pip install youtube-transcript-api")

try:
    import faster_whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

class TranscriptFetcher:
    """Fetch transcripts with multiple fallback strategies"""
    
    def __init__(self, yt_dlp_path: str = "yt-dlp", whisper_model: str = None, whisper_upgrade: str = None, ffmpeg_path: str = None, proxies: dict = None, api_key: str = None, credentials_path: str = None, enable_preprocessing: bool = True, store_audio_locally: bool = True, audio_storage_dir: str = None, production_mode: bool = False):
        self.yt_dlp_path = yt_dlp_path
        self.whisper_model = whisper_model or os.getenv('WHISPER_MODEL', 'small.en')
        self.whisper_upgrade = whisper_upgrade or os.getenv('WHISPER_UPGRADE', 'medium.en')
        self._whisper_model_cache = {}  # Cache multiple models
        self.ffmpeg_path = ffmpeg_path
        self.proxies = proxies
        self.api_key = api_key
        self.credentials_path = credentials_path
        self.enable_preprocessing = enable_preprocessing
        self._api_client = None  # Lazy loaded
        
        # Audio storage configuration
        self.production_mode = production_mode or os.getenv('PRODUCTION_MODE', 'false').lower() == 'true'
        self.store_audio_locally = store_audio_locally and not self.production_mode
        self.audio_storage_dir = None
        
        if self.store_audio_locally:
            from pathlib import Path
            storage_dir = audio_storage_dir or os.getenv('AUDIO_STORAGE_DIR', './audio_storage')
            self.audio_storage_dir = Path(storage_dir)
            self.audio_storage_dir.mkdir(exist_ok=True)
            logger.info(f"Audio will be stored in: {self.audio_storage_dir}")
        elif self.production_mode:
            logger.info("Production mode: Audio storage disabled")
        
        # Initialize AudioDownloader with current settings
        from .downloader import AudioDownloader
        # Use system temp dir by default - caller can override via temp_dir parameter
        import tempfile
        self.temp_dir = tempfile.gettempdir()
        self.audio_downloader = AudioDownloader(ffmpeg_path=ffmpeg_path, temp_dir=self.temp_dir)
        
        logger.info(f"TranscriptFetcher initialized with model: {self.whisper_model}")
        if self.proxies:
            logger.info(f"Proxy configured: {self.proxies}")
        if self.api_key:
            logger.info("YouTube API key provided for enhanced transcript fetching")
    
    def _get_whisper_model(self, model_name: str = None):
        """Lazy load Whisper model"""
        if not WHISPER_AVAILABLE:
            raise ImportError("faster-whisper not available. Install with: pip install faster-whisper")
        
        model_name = model_name or self.whisper_model
        
        if model_name not in self._whisper_model_cache:
            logger.info(f"Loading Whisper model: {model_name}")
            
            # Try GPU first (much faster), fallback to CPU if needed
            try:
                # Use GPU acceleration for RTX cards
                self._whisper_model_cache[model_name] = faster_whisper.WhisperModel(
                    model_name, 
                    device="cuda",  # Use GPU acceleration
                    compute_type="float16"  # Optimal for modern GPUs
                )
                logger.info(f"Successfully loaded {model_name} on GPU (CUDA)")
            except Exception as e:
                logger.warning(f"GPU loading failed, falling back to CPU: {e}")
                # Fallback to CPU
                self._whisper_model_cache[model_name] = faster_whisper.WhisperModel(
                    model_name, 
                    device="cpu",  # Fallback to CPU
                    compute_type="int8"  # Optimize memory usage for CPU
                )
                logger.info(f"Loaded {model_name} on CPU (fallback)")
        return self._whisper_model_cache[model_name]
    
    def _assess_transcript_quality(self, segments: List[TranscriptSegment]) -> Dict[str, Any]:
        """Assess the quality of a transcript to determine if upgrade is needed."""
        if not segments:
            return {"score": 0, "issues": ["no_content"], "needs_upgrade": True}
        
        total_text = " ".join(seg.text for seg in segments)
        word_count = len(total_text.split())
        char_count = len(total_text)
        
        # Calculate various quality metrics
        punct_count = len(re.findall(r'[.!?,:;]', total_text))
        punct_density = punct_count / max(char_count, 1)
        
        # Look for signs of poor transcription
        repeat_patterns = len(re.findall(r'\b(\w+)\s+\1\b', total_text, re.IGNORECASE))
        nonsense_words = len(re.findall(r'\b[bcdfghjklmnpqrstvwxyz]{4,}\b', total_text, re.IGNORECASE))
        
        # Average segment length
        avg_segment_length = sum(seg.end - seg.start for seg in segments) / len(segments)
        
        issues = []
        score = 100
        
        # Quality checks
        if word_count < 10:
            issues.append("too_short")
            score -= 50
        
        if punct_density < 0.01:  # Less than 1% punctuation
            issues.append("low_punctuation")
            score -= 20
        
        if repeat_patterns > word_count * 0.1:  # More than 10% repeated words
            issues.append("repetitive")
            score -= 30
        
        if nonsense_words > word_count * 0.2:  # More than 20% nonsense words
            issues.append("nonsense_words")
            score -= 40
        
        if avg_segment_length > 30:  # Segments too long (poor segmentation)
            issues.append("poor_segmentation")
            score -= 10
        
        needs_upgrade = score < 70 or len(issues) > 2
        
        return {
            "score": max(0, score),
            "word_count": word_count,
            "punct_density": punct_density,
            "avg_segment_length": avg_segment_length,
            "issues": issues,
            "needs_upgrade": needs_upgrade
        }
    
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
        
        logger.debug(f"Using YouTube Transcript API for {video_id}")
        
        # Use YouTube Transcript API for third-party videos
        try:
            # Create API instance
            api = YouTubeTranscriptApi()
            
            # Fetch transcript with language preferences (tries English first, then any available)
            try:
                fetched_transcript = api.fetch(video_id, languages=['en'])
            except Exception:
                # If English not available, try without language restriction
                fetched_transcript = api.fetch(video_id)
            
            # Convert to our transcript format
            segments = []
            for snippet in fetched_transcript:
                # Each snippet has text, start, and duration
                segment = TranscriptSegment(
                    start_time=snippet.start,
                    end_time=snippet.start + snippet.duration,
                    text=snippet.text.strip()
                )
                segments.append(segment)
            
            # Filter out non-verbal content and empty segments
            segments = [seg for seg in segments 
                       if seg.text and len(seg.text.strip()) > 0 
                       and not any(marker in seg.text.lower() 
                                 for marker in ['[music]', '[applause]', '[laughter]', '[silence]'])]
            
            if segments:
                logger.info(f"Successfully fetched YouTube transcript for {video_id} ({len(segments)} segments)")
                return segments
            else:
                logger.warning(f"No valid transcript segments found for {video_id}")
                return None
            
            logger.debug(f"YouTube transcript not available for {video_id}")
            return None
        
        except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound) as e:
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
                '--audio-format', 'wav',  # Lossless format, better for Whisper
                '--audio-quality', '0',  # Best quality
                '--no-playlist',
                # Latest nightly anti-blocking fixes (2025.09.26):
                '--extractor-args', 'youtube:player_client=web_safari',  # Use web_safari client (latest fix)
                '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                '--referer', 'https://www.youtube.com/',
                '-4',  # Force IPv4 (fixes many 403s)
                '--retry-sleep', '3',  # Pause between retries  
                '--retries', '10',  # More retries
                '--fragment-retries', '10',
                '--sleep-requests', '2',  # Sleep between requests
                '--socket-timeout', '60',  # Longer timeout
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
                
                # Store audio locally if configured
                stored_path = None
                if self.store_audio_locally:
                    stored_path = self._store_audio_permanently(audio_file, video_id)
                    if stored_path:
                        logger.info(f"Audio stored at: {stored_path}")
                
                # Transcribe with parallel Whisper (bypasses GIL)
                segments, metadata = self.transcribe_with_whisper_parallel(audio_file)
                
                # Add storage info to metadata
                if stored_path:
                    metadata = metadata or {}
                    metadata['stored_audio_path'] = str(stored_path)
                
                return segments
                
            except subprocess.TimeoutExpired:
                logger.error(f"Audio download timeout for {video_id}")
                return None
            except Exception as e:
                logger.error(f"Error downloading audio for {video_id}: {e}")
                return None
    
    def _store_audio_permanently(self, temp_audio_path: Path, video_id: str) -> Optional[Path]:
        """Store downloaded audio file permanently"""
        try:
            if not self.audio_storage_dir:
                return None
            
            # Create filename based on video ID and extension
            stored_filename = f"{video_id}{temp_audio_path.suffix}"
            stored_path = self.audio_storage_dir / stored_filename
            
            # Copy file to permanent location
            import shutil
            shutil.copy2(temp_audio_path, stored_path)
            
            logger.info(f"Audio stored permanently: {stored_path}")
            return stored_path
            
        except Exception as e:
            logger.error(f"Failed to store audio permanently: {e}")
            return None
    
    def transcribe_with_whisper_parallel(self, audio_path: Path, model_name: str = None) -> Tuple[Optional[List[TranscriptSegment]], Dict[str, Any]]:
        """
        Transcribe audio using multi-model Whisper pool for maximum RTX 5080 utilization
        """
        try:
            from .multi_model_whisper import get_multi_model_manager
            
            # Get the global multi-model manager
            # Use environment variable for model size and number of models
            num_models = int(os.getenv('WHISPER_PARALLEL_MODELS', '2'))
            model_size = os.getenv('WHISPER_MODEL_ENHANCED', 'large-v3')
            manager = get_multi_model_manager(num_models=num_models, model_size=model_size)
            
            # Use multi-model transcription
            segments, metadata = manager.transcribe_with_multi_model(audio_path, model_name)
            
            return segments, metadata
            
        except Exception as e:
            logger.error(f"Multi-model Whisper failed for {audio_path}: {e}")
            # Fallback to single model
            return self.transcribe_with_whisper_fallback(audio_path, model_name)
    
    def transcribe_with_whisper_fallback(self, audio_path: Path, model_name: str = None, enable_silence_removal: bool = False) -> Tuple[Optional[List[TranscriptSegment]], Dict[str, Any]]:
        """
        Transcribe audio using Whisper with enhanced VAD settings and quality assessment
        
        Returns:
            (segments, metadata) where metadata includes quality info and processing flags
        """
        if not WHISPER_AVAILABLE:
            logger.error("Whisper not available for transcription")
            return None, {"error": "whisper_unavailable"}
        
        model_name = model_name or self.whisper_model
        logger.debug(f"Transcribing with Whisper model {model_name}: {audio_path}")
        
        # Set up preprocessing config for this transcription
        preprocessing_config = AudioPreprocessingConfig(
            normalize_audio=self.preprocessing_config.normalize_audio,
            remove_silence=enable_silence_removal,
            pipe_mode=self.preprocessing_config.pipe_mode
        )
        
        metadata = {
            "model": model_name,
            "preprocessing": preprocessing_config.to_dict(),
            "vad_enabled": True
        }
        
        try:
            model = self._get_whisper_model(model_name)
            
            # Enhanced VAD parameters for better voice activity detection
            vad_parameters = {
                "min_silence_duration_ms": 700,  # More sensitive than default 1000ms
                "speech_pad_ms": 400,           # Padding around speech segments
                "max_speech_duration_s": 30,     # Maximum continuous speech duration
            }
            
            # Transcribe with enhanced settings
            segments, info = self.whisper_model.transcribe(
                str(audio_path),
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,  # Enable VAD to filter out silence/non-speech
                language="en",  # Force English for better performance
                vad_parameters=vad_parameters  # Pass custom VAD parameters
            )
            
            # Convert to normalized format
            transcript_segments = []
            for segment in segments:
                ts = TranscriptSegment.from_whisper_segment(segment)
                if ts.text and len(ts.text.strip()) > 1:  # Filter very short segments
                    transcript_segments.append(ts)
            
            # Add transcription info to metadata
            metadata.update({
                "detected_language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "segments_count": len(transcript_segments)
            })
            
            logger.info(f"Whisper ({model_name}) transcribed {len(transcript_segments)} segments from {audio_path}")
            return transcript_segments, metadata
            
        except Exception as e:
            logger.error(f"Whisper transcription failed for {audio_path}: {e}")
            metadata["error"] = str(e)
            return None, metadata
    
    def fetch_transcript(
        self, 
        video_id: str, 
        max_duration_s: Optional[int] = None,
        force_whisper: bool = False,
        cleanup_audio: bool = True,
        enable_silence_removal: bool = False
    ) -> Tuple[Optional[List[TranscriptSegment]], str, Dict[str, Any]]:
        """
        Fetch transcript with fallback strategy and quality-based model escalation
        
        Returns:
            (segments, method, metadata) where method is 'youtube', 'whisper', or 'whisper_upgraded'
        """
        metadata = {"video_id": video_id, "preprocessing_flags": {}}
        
        # Try YouTube transcript first unless forced to use Whisper
        if not force_whisper:
            youtube_segments = self.fetch_youtube_transcript(video_id)
            if youtube_segments:
                metadata.update({"source": "youtube", "segment_count": len(youtube_segments)})
                return youtube_segments, 'youtube', metadata
        
        # Check duration limit for Whisper fallback
        if max_duration_s is not None:
            # We would need duration info passed in or fetched here
            # For now, assume caller has already checked duration
            pass
        
        # Fallback to Whisper transcription
        logger.info(f"Falling back to Whisper transcription for {video_id}")
        
        # Download and preprocess audio
        try:
            preprocessing_config = AudioPreprocessingConfig(
                normalize_audio=True,
                remove_silence=enable_silence_removal,
                pipe_mode=False
            )
            
            audio_path = self.downloader.download_audio(video_id, preprocessing_config)
            metadata["preprocessing_flags"] = preprocessing_config.to_dict()
            
            if not audio_path or not os.path.exists(audio_path):
                metadata["error"] = "audio_download_failed"
                return None, 'failed', metadata
            
            # First attempt with parallel processing
            whisper_segments, whisper_metadata = self.transcribe_with_whisper_parallel(
                Path(audio_path), 
                model_name=self.whisper_model
            )
            
            method = 'whisper'
            metadata.update(whisper_metadata)
            
            # If we got segments, assess quality and potentially upgrade
            if whisper_segments:
                quality_info = self._assess_transcript_quality(whisper_segments)
                metadata["quality_assessment"] = quality_info
                
                logger.info(f"Transcript quality score: {quality_info['score']} for {video_id}")
                
                # Upgrade to better model if quality is poor and upgrade model is different
                if (quality_info['needs_upgrade'] and 
                    self.whisper_upgrade != self.whisper_model and
                    quality_info['score'] < 70):
                    
                    logger.info(f"Quality issues detected ({quality_info['issues']}). "
                               f"Upgrading to {self.whisper_upgrade} for {video_id}")
                    
                    # Try with upgraded model (fallback method for quality upgrade)
                    upgrade_segments, upgrade_metadata = self.transcribe_with_whisper_fallback(
                        Path(audio_path),
                        model_name=self.whisper_upgrade,
                        enable_silence_removal=enable_silence_removal
                    )
                    
                    if upgrade_segments:
                        upgrade_quality = self._assess_transcript_quality(upgrade_segments)
                        
                        # Use upgraded version if it's better
                        if upgrade_quality['score'] > quality_info['score']:
                            logger.info(f"Upgrade successful. Quality improved from "
                                       f"{quality_info['score']} to {upgrade_quality['score']}")
                            whisper_segments = upgrade_segments
                            method = 'whisper_upgraded'
                            metadata.update(upgrade_metadata)
                            metadata["quality_assessment"] = upgrade_quality
                            metadata["upgrade_used"] = True
                        else:
                            logger.info("Upgrade did not improve quality, keeping original")
                            metadata["upgrade_attempted"] = True
                            metadata["upgrade_failed"] = True
            
            return whisper_segments, method, metadata
                
        except Exception as e:
            # Handle encoding errors safely - this is critical on Windows
            try:
                error_msg = str(e)
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = repr(e)  # Use repr() which is safer
            
            # Also wrap logger call in case it triggers encoding errors
            try:
                logger.error(f"Error in Whisper transcription for {video_id}: {error_msg}")
            except (UnicodeEncodeError, UnicodeDecodeError):
                # If even logging fails, just log a generic message
                logger.error(f"Error in Whisper transcription for {video_id}: [encoding error in error message]")
            
            metadata["error"] = error_msg
            return None, 'failed', metadata
            
        finally:
            # Cleanup audio file
            if cleanup_audio:
                try:
                    self.downloader.cleanup_temp_files(video_id)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp files for {video_id}: {e}")

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
