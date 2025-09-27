#!/usr/bin/env python3
"""
Local file lister for ingesting pre-downloaded video/audio files.
Provides a unified interface similar to YouTube listers but for local content.
"""

import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
import mimetypes

# Local imports
from .list_videos_yt_dlp import VideoInfo

logger = logging.getLogger(__name__)

class LocalFileInfo:
    """Information about a local video/audio file, compatible with VideoInfo interface"""
    
    def __init__(self, file_path: Path, video_id: Optional[str] = None, title: Optional[str] = None):
        self.file_path = file_path
        self.video_id = video_id or self._generate_video_id()
        self.title = title or self._extract_title()
        
        # Get file stats
        stat = file_path.stat()
        self.published_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        self.duration_s = None  # Will be detected during processing
        self.url = f"file://{file_path.absolute()}"
        
        # Determine if it's audio or video
        mime_type, _ = mimetypes.guess_type(str(file_path))
        self.is_audio_only = mime_type and mime_type.startswith('audio/')
        
        # Additional metadata
        self.file_size = stat.st_size
        self.file_extension = file_path.suffix.lower()
        
        logger.debug(f"Created LocalFileInfo: {self.video_id} -> {file_path}")
    
    def _generate_video_id(self) -> str:
        """Generate a unique video ID based on file path and content"""
        # Create a stable hash from file path and size
        content = f"{self.file_path.absolute()}_{self.file_path.stat().st_size}"
        hash_obj = hashlib.md5(content.encode('utf-8'))
        return f"local_{hash_obj.hexdigest()[:11]}"  # Similar length to YouTube IDs
    
    def _extract_title(self) -> str:
        """Extract a title from the filename"""
        # Remove extension and clean up filename
        title = self.file_path.stem
        
        # Replace common separators with spaces
        title = title.replace('_', ' ').replace('-', ' ').replace('.', ' ')
        
        # Remove common patterns
        title = title.strip()
        if not title:
            title = f"Local File {self.video_id}"
        
        return title
    
    def to_video_info(self) -> VideoInfo:
        """Convert to VideoInfo object for compatibility with existing pipeline"""
        return VideoInfo(
            video_id=self.video_id,
            title=self.title,
            url=self.url,
            published_at=self.published_at,
            duration_s=self.duration_s,
            # Additional fields for local files
            description=f"Local file: {self.file_path.name}",
            thumbnail_url=None,
            view_count=None,
            like_count=None,
            channel_title="Local Files"
        )


class LocalFileLister:
    """List local video/audio files for ingestion"""
    
    def __init__(self, supported_extensions: Optional[List[str]] = None):
        """
        Initialize local file lister.
        
        Args:
            supported_extensions: List of supported file extensions (with or without dots)
        """
        if supported_extensions is None:
            # Default supported video and audio formats
            supported_extensions = [
                # Video formats
                'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v',
                # Audio formats  
                'wav', 'mp3', 'm4a', 'aac', 'ogg', 'flac', 'wma'
            ]
        
        # Normalize extensions (ensure they start with dot)
        self.supported_extensions = [
            ext if ext.startswith('.') else f'.{ext}' 
            for ext in supported_extensions
        ]
        
        logger.info(f"LocalFileLister initialized with extensions: {self.supported_extensions}")
    
    def list_files_from_directory(
        self, 
        directory: Path, 
        patterns: Optional[List[str]] = None,
        recursive: bool = True,
        max_results: Optional[int] = None,
        newest_first: bool = True
    ) -> List[LocalFileInfo]:
        """
        List supported files from a directory.
        
        Args:
            directory: Directory to scan
            patterns: Glob patterns to match (e.g., ['*.mp4', '*.wav'])
            recursive: Whether to scan subdirectories
            max_results: Maximum number of files to return
            newest_first: Whether to sort by modification time (newest first)
            
        Returns:
            List of LocalFileInfo objects
        """
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")
        
        logger.info(f"Scanning directory for files: {directory}")
        
        files = []
        
        # If patterns provided, use glob matching
        if patterns:
            for pattern in patterns:
                if recursive:
                    found_files = directory.rglob(pattern)
                else:
                    found_files = directory.glob(pattern)
                
                for file_path in found_files:
                    if file_path.is_file():
                        files.append(file_path)
        else:
            # Use extension matching
            if recursive:
                all_files = directory.rglob('*')
            else:
                all_files = directory.glob('*')
            
            for file_path in all_files:
                if (file_path.is_file() and 
                    file_path.suffix.lower() in self.supported_extensions):
                    files.append(file_path)
        
        logger.info(f"Found {len(files)} matching files")
        
        # Convert to LocalFileInfo objects
        file_infos = []
        for file_path in files:
            try:
                file_info = LocalFileInfo(file_path)
                file_infos.append(file_info)
            except Exception as e:
                logger.warning(f"Error processing file {file_path}: {e}")
                continue
        
        # Sort files
        if newest_first:
            file_infos.sort(key=lambda f: f.published_at, reverse=True)
        else:
            file_infos.sort(key=lambda f: f.published_at)
        
        # Apply limit
        if max_results:
            file_infos = file_infos[:max_results]
        
        logger.info(f"Returning {len(file_infos)} file info objects")
        return file_infos
    
    def list_files_from_paths(self, file_paths: List[Path]) -> List[LocalFileInfo]:
        """
        Create LocalFileInfo objects from a list of file paths.
        
        Args:
            file_paths: List of file paths to process
            
        Returns:
            List of LocalFileInfo objects
        """
        file_infos = []
        
        for file_path in file_paths:
            if not file_path.exists():
                logger.warning(f"File does not exist: {file_path}")
                continue
                
            if not file_path.is_file():
                logger.warning(f"Path is not a file: {file_path}")
                continue
            
            # Check if extension is supported
            if file_path.suffix.lower() not in self.supported_extensions:
                logger.warning(f"Unsupported file type: {file_path}")
                continue
            
            try:
                file_info = LocalFileInfo(file_path)
                file_infos.append(file_info)
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                continue
        
        return file_infos
    
    def get_file_duration(self, file_path: Path) -> Optional[float]:
        """
        Get duration of media file using ffprobe.
        
        Args:
            file_path: Path to media file
            
        Returns:
            Duration in seconds, or None if cannot be determined
        """
        try:
            import subprocess
            
            cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
            else:
                logger.debug(f"Could not determine duration for {file_path}")
                return None
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError) as e:
            logger.debug(f"Error getting duration for {file_path}: {e}")
            return None
        except FileNotFoundError:
            logger.debug("ffprobe not found - cannot determine file durations")
            return None


def create_local_file_lister(supported_extensions: Optional[List[str]] = None) -> LocalFileLister:
    """Factory function to create LocalFileLister instance."""
    return LocalFileLister(supported_extensions=supported_extensions)


if __name__ == '__main__':
    # CLI for testing
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='List local video/audio files')
    parser.add_argument('directory', type=Path, help='Directory to scan')
    parser.add_argument('--patterns', nargs='+', help='File patterns to match')
    parser.add_argument('--recursive', action='store_true', default=True, help='Scan subdirectories')
    parser.add_argument('--limit', type=int, help='Maximum number of files')
    parser.add_argument('--extensions', nargs='+', help='Supported file extensions')
    
    args = parser.parse_args()
    
    lister = LocalFileLister(supported_extensions=args.extensions)
    files = lister.list_files_from_directory(
        args.directory,
        patterns=args.patterns,
        recursive=args.recursive,
        max_results=args.limit
    )
    
    print(f"\nFound {len(files)} files:")
    for file_info in files:
        print(f"  {file_info.video_id}: {file_info.title}")
        print(f"    Path: {file_info.file_path}")
        print(f"    Size: {file_info.file_size / (1024*1024):.1f} MB")
        print(f"    Modified: {file_info.published_at}")
        print()
