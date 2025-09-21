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
        """Build yt-dlp configuration dictionary."""
        config = {
            'outtmpl': output_path,
            'format': 'bestaudio/best',
            'extract_flat': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': False,
        }
        
        # Add proxy if configured
        if self.proxy:
            config['proxy'] = self.proxy
        
        # Add ffmpeg path if specified
        if self.ffmpeg_path != "ffmpeg":
            config['ffmpeg_location'] = str(Path(self.ffmpeg_path).parent)
        
        # Convert parsed options to yt-dlp config
        # Note: This is a simplified conversion, real implementation would need
        # more sophisticated parsing for all yt-dlp options
        for opt in self.ytdlp_opts:
            if opt.startswith('--sleep-requests'):
                continue  # Handled by yt-dlp internally
            elif opt.startswith('--retries'):
                try:
                    config['retries'] = int(opt.split()[-1])
                except (ValueError, IndexError):
                    pass
            elif opt.startswith('--fragment-retries'):
                try:
                    config['fragment_retries'] = int(opt.split()[-1])
                except (ValueError, IndexError):
                    pass
            elif opt.startswith('--socket-timeout'):
                try:
                    config['socket_timeout'] = int(opt.split()[-1])
                except (ValueError, IndexError):
                    pass
        
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
            
            with yt_dlp.YoutubeDL(ytdl_config) as ytdl:
                url = f"https://www.youtube.com/watch?v={video_id}"
                info = ytdl.extract_info(url, download=True)
                
                # Find the actual downloaded file
                downloaded_file = None
                for ext in ['webm', 'mp4', 'm4a', 'ogg']:
                    candidate = raw_audio_path.replace('%(ext)s', ext)
                    if os.path.exists(candidate):
                        downloaded_file = candidate
                        break
                
                if not downloaded_file:
                    raise DownloadError(f"Could not find downloaded file for {video_id}")
                
                logger.info(f"Downloaded {downloaded_file}")
            
            # Apply preprocessing if needed
            if preprocessing_config.normalize_audio or preprocessing_config.remove_silence:
                processed_audio_path = self._preprocess_audio(
                    downloaded_file, 
                    processed_audio_path,
                    preprocessing_config
                )
                
                # Clean up raw file
                try:
                    os.remove(downloaded_file)
                except OSError:
                    pass
                    
                return processed_audio_path
            else:
                # Return raw file if no preprocessing
                return downloaded_file
                
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
        
        # Audio normalization: mono, 16kHz, 16-bit PCM
        if config.normalize_audio:
            cmd.extend(['-ac', '1', '-ar', '16000', '-sample_fmt', 's16', '-vn'])
        
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
