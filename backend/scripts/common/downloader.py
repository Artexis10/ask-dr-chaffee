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

# Thread lock to limit concurrent downloads per process
_download_lock = threading.Lock()

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
        config = {
            'outtmpl': output_path,
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio[acodec=opus]/bestaudio/best',  # Prioritize high-quality formats
            'extract_flat': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,  # CRITICAL: Ignore cookie errors instead of crashing
            # GPT-5's anti-blocking recommendations 
            'source_address': '0.0.0.0',  # Force IPv4 
            'sleep_requests': 5,
            'min_sleep_interval': 2,  # Required with max_sleep_interval
            'max_sleep_interval': 15,
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
            # CRITICAL FIX: Force UTF-8 encoding for all output to prevent Windows encoding errors
            'encoding': 'utf-8',
            'quiet': False,  # Keep logging
            'no_warnings': False,  # Show warnings but don't crash
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
        
        # Use thread lock to limit concurrent downloads
        with _download_lock:
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
            
            # Create a UTF-8 compatible stderr buffer
            stderr_buffer = io.StringIO()
            
            with contextlib.redirect_stderr(stderr_buffer):
                with yt_dlp.YoutubeDL(ytdl_config) as ytdl:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    info = ytdl.extract_info(url, download=True)
            
            # Log any stderr output (now safely captured as UTF-8)
            stderr_content = stderr_buffer.getvalue()
            if stderr_content and not stderr_content.isspace():
                logger.debug(f"yt-dlp stderr for {video_id}: {stderr_content[:500]}")
            
            # Find the actual downloaded file
            downloaded_file = None
            for ext in ['webm', 'mp4', 'm4a', 'ogg', 'wav']:
                candidate = raw_audio_path.replace('%(ext)s', ext)
                if os.path.exists(candidate):
                    downloaded_file = candidate
                    break
            
            if not downloaded_file:
                # Check if download actually happened - info might be None if video is unavailable
                if info is None:
                    raise DownloadError(f"Video {video_id} is unavailable (members-only, private, or deleted)")
                
                # List what files ARE in the temp directory for debugging
                import glob
                temp_files = glob.glob(os.path.join(self.temp_dir, f"{video_id}*"))
                logger.error(f"Could not find downloaded file for {video_id}. Files in temp dir: {temp_files}")
                logger.error(f"yt-dlp stderr: {stderr_content[:1000] if stderr_content else 'empty'}")
                raise DownloadError(f"Could not find downloaded file for {video_id}")
            
            # Ensure downloaded_file is always a proper string
            downloaded_file = str(downloaded_file)
            logger.info(f"Downloaded {downloaded_file}")
            
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
