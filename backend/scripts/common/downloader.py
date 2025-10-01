"""
Audio downloader module for yt-dlp with proxy support and audio preprocessing.
Handles downloading audio, applying preprocessing, and managing concurrent downloads.
"""
import os
import logging
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import yt_dlp
from yt_dlp.utils import DownloadError


logger = logging.getLogger(__name__)

# Semaphore to limit concurrent downloads (allow 8-10 simultaneous downloads)
# Using semaphore instead of lock to allow controlled concurrency
# Increased from 5 to 10 to feed 4 ASR workers with 24 I/O workers
_download_semaphore = threading.Semaphore(10)  # Allow up to 10 concurrent downloads

@dataclass
class AudioPreprocessingConfig:
    """Configuration for audio preprocessing."""
    normalize_audio: bool = True  # Convert to mono, 16kHz
    remove_silence: bool = False  # Apply silence removal
    pipe_mode: bool = False      # Use piping instead of temp files
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for metadata storage."""
        return {
            "normalize_audio": self.normalize_audio,
            "remove_silence": self.remove_silence,
            "pipe_mode": self.pipe_mode
        }


class AudioDownloader:
    """Handles audio downloading with yt-dlp and preprocessing with ffmpeg."""
    
    def __init__(self, ffmpeg_path: Optional[str] = None, temp_dir: Optional[str] = None):
        """
        Initialize the audio downloader.
        
        Args:
            ffmpeg_path: Path to ffmpeg executable. If None, uses system PATH.
            temp_dir: Directory for temporary files. If None, uses system temp.
        """
        # CRITICAL: Force UTF-8 encoding on Windows BEFORE any yt-dlp operations
        # Set environment variable that Python respects for all I/O operations
        import sys
        if sys.platform == 'win32':
            os.environ['PYTHONIOENCODING'] = 'utf-8'
            # Also reconfigure existing streams
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"
        self.temp_dir = temp_dir or tempfile.gettempdir()
        
        # Load configuration from environment
        self.proxy = os.getenv("YTDLP_PROXY", "").strip()
        self.ytdlp_opts = self._parse_ytdlp_opts()
        
        logger.info(f"AudioDownloader initialized with proxy: {'***' if self.proxy else 'None'}")
        logger.info(f"yt-dlp options: {' '.join(self.ytdlp_opts)}")
    
    def _parse_ytdlp_opts(self) -> List[str]:
        """Parse YTDLP_OPTS environment variable into list of options."""
        opts_str = os.getenv("YTDLP_OPTS", "").strip()
        if not opts_str:
            return []
        
        # Simple parsing - split by spaces but handle quoted arguments
        import shlex
        try:
            return shlex.split(opts_str)
        except ValueError as e:
            logger.warning(f"Failed to parse YTDLP_OPTS: {e}. Using raw split.")
            return opts_str.split()
    
    def _build_ytdlp_config(self, video_id: str, output_path: str) -> Dict[str, Any]:
        """Build yt-dlp configuration dictionary with stealth options."""
        
        # Custom logger to redirect yt-dlp output and avoid Windows encoding issues
        class YtDlpLogger:
            def debug(self, msg):
                # Suppress debug messages to avoid encoding issues
                pass
            
            def info(self, msg):
                # Only log important info messages
                if msg.startswith('[download]') and '100%' in msg:
                    logger.debug(f"yt-dlp: {msg}")
            
            def warning(self, msg):
                logger.warning(f"yt-dlp: {msg}")
            
            def error(self, msg):
                logger.error(f"yt-dlp: {msg}")
        
        config = {
            'outtmpl': output_path,
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio[acodec=opus]/bestaudio/best',  # Prioritize high-quality formats
            'extract_flat': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': False,  # Don't ignore errors - we need to see them to fix them properly
            # Anti-blocking recommendations (reduced for better throughput with semaphore limiting)
            'source_address': '0.0.0.0',  # Force IPv4 
            'sleep_requests': 1,  # Reduced from 5 - semaphore already limits concurrency
            'min_sleep_interval': 0.5,  # Reduced from 2
            'max_sleep_interval': 3,  # Reduced from 15
            # REMOVED: cookiesfrombrowser causes UTF-8 encoding errors on Windows
            # 'cookiesfrombrowser': ('firefox', None, None, None),
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ApyleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.youtube.com/',
            },
            'retries': 10,
            'retry_sleep': 3,
            'fragment_retries': 10,
            'socket_timeout': 60,
            # CRITICAL FIX: Use custom logger to avoid Windows encoding errors
            'logger': YtDlpLogger(),
            'noprogress': True,  # Disable progress bar to avoid encoding issues
            'quiet': True,  # Suppress console output - use logger instead
            'no_warnings': False,  # Show warnings via logger
            # Additional options to improve success rate
            'nocheckcertificate': True,  # Skip SSL certificate verification
            'prefer_insecure': False,  # Use HTTPS when available
            'age_limit': None,  # No age restrictions
        }
        
        # Add proxy if configured
        if self.proxy:
            config['proxy'] = self.proxy
        
        # Add ffmpeg path if specified
        if self.ffmpeg_path != "ffmpeg":
            config['ffmpeg_location'] = str(Path(self.ffmpeg_path).parent)
        
        # CRITICAL FIX: Do NOT parse YTDLP_OPTS environment variable
        # On Windows, cookie-related options cause UTF-8 encoding errors in yt-dlp's error handling
        # The config dictionary above already has all necessary options
        # Ignoring self.ytdlp_opts to prevent crashes
        
        return config
    
    def download_audio(self, video_id: str, preprocessing_config: Optional[AudioPreprocessingConfig] = None) -> str:
        """
        Download audio for a video and apply preprocessing.
        
        Args:
            video_id: YouTube video ID
            preprocessing_config: Audio preprocessing configuration
            
        Returns:
            Path to the processed audio file
            
        Raises:
            DownloadError: If download fails
            subprocess.CalledProcessError: If preprocessing fails
        """
        preprocessing_config = preprocessing_config or AudioPreprocessingConfig()
        
        # Use semaphore to limit concurrent downloads (allows 10 simultaneous)
        with _download_semaphore:
            return self._download_and_process(video_id, preprocessing_config)
    
    def _download_and_process(self, video_id: str, preprocessing_config: AudioPreprocessingConfig) -> str:
        """Internal method to download and process audio."""
        # Create temporary files
        raw_audio_path = os.path.join(self.temp_dir, f"{video_id}_raw.%(ext)s")
        processed_audio_path = os.path.join(self.temp_dir, f"{video_id}_processed.wav")
        
        try:
            # Download audio using yt-dlp
            logger.info(f"Downloading audio for video {video_id}")
            ytdl_config = self._build_ytdlp_config(video_id, raw_audio_path)
            
            # CRITICAL FIX: Suppress yt-dlp's stderr to prevent UTF-8 encoding errors on Windows
            # The error occurs when yt-dlp tries to write cookie errors to stderr using cp1252 encoding
            import io
            import contextlib
            import sys
            
            # CRITICAL: Force UTF-8 encoding for stdout/stderr before yt-dlp runs
            # This prevents "utf_8_encode() argument 1 must be str, not bytes" errors
            if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            
            # Wrap yt-dlp call to catch and handle UTF-8 encoding errors
            # Don't redirect stderr - let yt-dlp write directly (with UTF-8 encoding we set above)
            stderr_content = ""
            try:
                with yt_dlp.YoutubeDL(ytdl_config) as ytdl:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    info = ytdl.extract_info(url, download=True)
            except (UnicodeEncodeError, UnicodeDecodeError) as e:
                # This happens when yt-dlp tries to print error messages with non-ASCII characters
                # on Windows with cp1252 encoding. The download might have succeeded despite the error.
                logger.warning(f"UTF-8 encoding error during download for {video_id}, checking for downloaded file")
                # Check if file was downloaded anyway
                info = None  # Will trigger file search below
            except TypeError as e:
                # TypeError: utf_8_encode() argument 1 must be str, not bytes
                # This is another Windows encoding issue - download likely succeeded
                error_msg = str(e)
                if "utf_8_encode" in error_msg or "bytes" in error_msg:
                    logger.warning(f"UTF-8 TypeError during download for {video_id}, checking for downloaded file")
                    info = None  # Will trigger file search below
                else:
                    # Different TypeError - re-raise
                    raise
            except DownloadError as e:
                # yt-dlp's DownloadError - this is a real failure, log it properly
                error_msg = str(e)
                logger.error(f"yt-dlp DownloadError for {video_id}: {error_msg}")
                # Check if it's a known error type
                if "members-only" in error_msg.lower() or "join this channel" in error_msg.lower():
                    raise DownloadError(f"Video {video_id} is members-only content")
                elif "private" in error_msg.lower() or "unavailable" in error_msg.lower():
                    raise DownloadError(f"Video {video_id} is unavailable (private or deleted)")
                elif "429" in error_msg or "rate" in error_msg.lower():
                    raise DownloadError(f"Rate limited by YouTube for {video_id}")
                else:
                    raise DownloadError(f"Download failed for {video_id}: {error_msg}")
            except Exception as e:
                # Catch any other exception - log the type and message
                error_type = type(e).__name__
                try:
                    error_msg = str(e)
                except:
                    error_msg = "<unable to convert error to string>"
                logger.error(f"yt-dlp {error_type} for {video_id}: {error_msg}")
                # Don't assume file was downloaded - raise the error
                raise DownloadError(f"Download failed for {video_id}: {error_type}: {error_msg}")
            
            # DEBUG: Log info dict
            if info:
                logger.debug(f"yt-dlp info for {video_id}: title={info.get('title', 'N/A')}, ext={info.get('ext', 'N/A')}")
            else:
                logger.warning(f"yt-dlp returned None for {video_id}")
            
            # Find the actual downloaded file
            downloaded_file = None
            
            # First check if processed file already exists (from previous run or preprocessing)
            if os.path.exists(processed_audio_path):
                downloaded_file = processed_audio_path
                logger.debug(f"Found processed file: {downloaded_file}")
            else:
                # Check for raw downloaded files
                for ext in ['webm', 'mp4', 'm4a', 'ogg', 'wav']:
                    candidate = raw_audio_path.replace('%(ext)s', ext)
                    logger.debug(f"Checking for file: {candidate}")
                    if os.path.exists(candidate):
                        downloaded_file = candidate
                        logger.debug(f"Found file: {downloaded_file}")
                        break
            
            if not downloaded_file:
                # List what files ARE in the temp directory for debugging
                import glob
                temp_files = glob.glob(os.path.join(self.temp_dir, f"{video_id}*"))
                logger.error(f"Could not find downloaded file for {video_id}. Files in temp dir: {temp_files}")
                
                # Check if this looks like a genuine download failure vs encoding error
                if not temp_files and info is None:
                    # No files and no info - likely a genuine unavailable video
                    if "members-only" in stderr_content.lower() or "join this channel" in stderr_content.lower():
                        raise DownloadError(f"Video {video_id} is members-only content")
                    elif "private" in stderr_content.lower() or "unavailable" in stderr_content.lower():
                        raise DownloadError(f"Video {video_id} is unavailable (private or deleted)")
                    else:
                        logger.error(f"yt-dlp stderr: {stderr_content[:1000] if stderr_content else 'empty'}")
                        raise DownloadError(f"Could not download or find file for {video_id}")
                else:
                    # Files exist but we couldn't match them - likely encoding issue
                    logger.error(f"Files exist but couldn't be matched. Stderr: {stderr_content[:500] if stderr_content else 'empty'}")
                    raise DownloadError(f"Could not find downloaded file for {video_id}")
            
            # Ensure downloaded_file is always a proper string
            downloaded_file = str(downloaded_file)
            logger.info(f"Downloaded {downloaded_file}")
            
            # If we found the processed file, skip preprocessing and return it
            if downloaded_file == processed_audio_path:
                logger.debug(f"Using existing processed file: {processed_audio_path}")
                result_path = str(processed_audio_path)
                if isinstance(result_path, bytes):
                    result_path = result_path.decode('utf-8', errors='replace')
                return result_path
            
            # Apply preprocessing if needed
            if preprocessing_config.normalize_audio or preprocessing_config.remove_silence:
                processed_audio_path = self._preprocess_audio(
                    str(downloaded_file), 
                    str(processed_audio_path),
                    preprocessing_config
                )
                
                # Clean up raw file
                try:
                    os.remove(downloaded_file)
                except OSError:
                    pass
                
                # CRITICAL: Ensure OS-native string encoding to prevent utf_8_encode errors on Windows
                result_path = str(processed_audio_path)
                if isinstance(result_path, bytes):
                    result_path = result_path.decode('utf-8', errors='replace')
                return result_path
            else:
                # Return raw file if no preprocessing
                # CRITICAL: Ensure OS-native string encoding to prevent utf_8_encode errors on Windows
                result_path = str(downloaded_file)
                if isinstance(result_path, bytes):
                    result_path = result_path.decode('utf-8', errors='replace')
                return result_path
                
        except Exception as e:
            # Clean up any temporary files
            for temp_file in [raw_audio_path.replace('%(ext)s', ext) for ext in ['webm', 'mp4', 'm4a', 'ogg']] + [processed_audio_path]:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except OSError:
                    pass
            raise
    
    def _preprocess_audio(self, input_path: str, output_path: str, config: AudioPreprocessingConfig) -> str:
        """
        Preprocess audio file with ffmpeg.
        
        Args:
            input_path: Path to input audio file
            output_path: Path to output audio file
            config: Preprocessing configuration
            
        Returns:
            Path to processed audio file
        """
        cmd = [self.ffmpeg_path, '-i', input_path]
        
        # Audio normalization optimized for Whisper: mono, 16kHz, 16-bit PCM
        if config.normalize_audio:
            cmd.extend([
                '-ac', '1',           # Convert to mono (speech doesn't need stereo)
                '-ar', '16000',       # 16kHz sample rate (Whisper's native rate)
                '-sample_fmt', 's16', # 16-bit depth (sufficient for speech)
                '-vn'                 # No video stream
            ])
        
        # Silence removal (conservative settings)
        if config.remove_silence:
            silence_filter = 'silenceremove=start_periods=1:start_silence=0.1:start_threshold=-50dB:detection=peak'
            cmd.extend(['-af', silence_filter])
        
        cmd.extend(['-y', output_path])  # -y to overwrite output file
        
        logger.info(f"Running ffmpeg: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.debug(f"ffmpeg stdout: {result.stdout}")
            
            if not os.path.exists(output_path):
                raise subprocess.CalledProcessError(1, cmd, "Output file not created")
                
            return output_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg failed: {e}")
            logger.error(f"ffmpeg stderr: {e.stderr}")
            raise
    
    def cleanup_temp_files(self, video_id: str):
        """Clean up temporary files for a video."""
        patterns = [
            f"{video_id}_raw.*",
            f"{video_id}_processed.*"
        ]
        
        import glob
        for pattern in patterns:
            for file_path in glob.glob(os.path.join(self.temp_dir, pattern)):
                try:
                    os.remove(file_path)
                    logger.debug(f"Cleaned up temp file: {file_path}")
                except OSError as e:
                    logger.warning(f"Failed to clean up {file_path}: {e}")


def create_downloader(ffmpeg_path: Optional[str] = None, temp_dir: Optional[str] = None) -> AudioDownloader:
    """Factory function to create AudioDownloader instance."""
    return AudioDownloader(ffmpeg_path=ffmpeg_path, temp_dir=temp_dir)
