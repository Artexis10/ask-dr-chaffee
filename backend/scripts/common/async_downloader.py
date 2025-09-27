#!/usr/bin/env python3
"""
Async bulk audio downloader for YouTube ingestion pipeline.
Pre-downloads audio files in batches while transcription is happening.
"""

import asyncio
import logging
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import time

logger = logging.getLogger(__name__)

@dataclass
class DownloadTask:
    """Represents a single download task"""
    video_id: str
    title: str
    url: str
    output_path: Path
    status: str = 'pending'  # pending, downloading, completed, failed
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None

class AsyncAudioDownloader:
    """Async bulk audio downloader for YouTube videos"""
    
    def __init__(self, 
                 yt_dlp_path: str = "yt-dlp",
                 max_concurrent_downloads: int = 6,
                 storage_dir: Optional[Path] = None,
                 temp_dir: Optional[Path] = None,
                 db_connection=None,
                 skip_existing: bool = True,
                 skip_members_only: bool = True):
        """
        Initialize async audio downloader
        
        Args:
            yt_dlp_path: Path to yt-dlp executable
            max_concurrent_downloads: Maximum concurrent downloads
            storage_dir: Permanent storage directory (if None, uses temp)
            temp_dir: Temporary download directory
        """
        self.yt_dlp_path = yt_dlp_path
        self.max_concurrent_downloads = max_concurrent_downloads
        self.storage_dir = storage_dir
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "async_downloads"
        self.temp_dir.mkdir(exist_ok=True)
        self.db_connection = db_connection
        self.skip_existing = skip_existing
        self.skip_members_only = skip_members_only
        
        # Track downloads
        self.download_tasks: Dict[str, DownloadTask] = {}
        self.download_queue = asyncio.Queue()
        self.completed_queue = asyncio.Queue()
        
        # Performance metrics
        self.stats = {
            'total_downloads': 0,
            'completed_downloads': 0,
            'failed_downloads': 0,
            'total_download_time': 0.0,
            'concurrent_peak': 0
        }
        
        logger.info(f"AsyncAudioDownloader initialized: {max_concurrent_downloads} concurrent, storage: {storage_dir}")
    
    def check_video_exists_in_db(self, video_id: str) -> bool:
        """Check if video already exists in database"""
        if not self.db_connection:
            return False
        
        try:
            with self.db_connection.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM sources WHERE source_id = %s LIMIT 1",
                    (video_id,)
                )
                return cur.fetchone() is not None
        except Exception as e:
            logger.warning(f"DB check failed for {video_id}: {e}")
            return False
    
    def check_audio_exists_locally(self, video_id: str) -> Optional[Path]:
        """Check if audio file already exists locally"""
        if not self.storage_dir or not self.storage_dir.exists():
            return None
        
        # Check for common audio extensions
        extensions = ['.mp4', '.m4a', '.webm', '.wav', '.mp3']
        for ext in extensions:
            audio_path = self.storage_dir / f"{video_id}{ext}"
            if audio_path.exists():
                logger.debug(f"Found existing audio: {audio_path}")
                return audio_path
        
        return None
    
    def is_members_only_video(self, video_info: Dict[str, Any]) -> bool:
        """Check if video is members-only content"""
        title = video_info.get('title', '').lower()
        
        # Check for common members-only indicators in title
        members_indicators = [
            'members only',
            'members exclusive', 
            'exclusive to members',
            'member exclusive',
            'patreon exclusive',
            'subscriber exclusive',
            'premium content',
            'early access'
        ]
        
        for indicator in members_indicators:
            if indicator in title:
                return True
        
        return False
    
    def is_members_only_error(self, error_message: str) -> bool:
        """Check if error indicates members-only content"""
        error_lower = error_message.lower()
        
        members_error_indicators = [
            'join this channel to get access to members-only content',
            'membership required',
            'premium content',
            'available to members only',
            'subscribers only',
            'exclusive content'
        ]
        
        for indicator in members_error_indicators:
            if indicator in error_lower:
                return True
        
        return False
    
    def filter_existing_videos(self, video_list: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Filter out videos that already exist in DB, locally, or are members-only
        
        Returns:
            (videos_to_download, videos_already_exist_or_skip)
        """
        if not self.skip_existing:
            return video_list, []
        
        to_download = []
        already_exist = []
        
        for video_info in video_list:
            video_id = video_info['video_id']
            
            # Check for members-only content first (fastest)
            if self.skip_members_only and self.is_members_only_video(video_info):
                logger.info(f"Skipping members-only content: {video_id} - {video_info.get('title', '')[:50]}...")
                already_exist.append(video_info)
                continue
            
            # Check database (fast)
            if self.check_video_exists_in_db(video_id):
                logger.debug(f"Skipping {video_id}: already in database")
                already_exist.append(video_info)
                continue
            
            # Check local audio storage
            local_path = self.check_audio_exists_locally(video_id)
            if local_path:
                logger.debug(f"Skipping {video_id}: audio exists at {local_path}")
                already_exist.append(video_info)
                continue
            
            to_download.append(video_info)
        
        logger.info(f"Deduplication: {len(to_download)} to download, {len(already_exist)} already exist/skipped")
        return to_download, already_exist
    
    def get_yt_dlp_command(self, video_id: str, output_path: Path) -> List[str]:
        """Generate optimized yt-dlp command for async download"""
        return [
            self.yt_dlp_path,
            '--format', 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
            '--no-playlist',
            '--ignore-errors',
            # Latest nightly anti-blocking fixes
            '--extractor-args', 'youtube:player_client=web_safari',
            '-4',  # Force IPv4
            '--retry-sleep', '2',  # Faster retries for bulk downloads
            '--retries', '8',
            '--fragment-retries', '8', 
            '--sleep-requests', '1',  # Reduced sleep for bulk downloads
            '--socket-timeout', '45',
            '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '--referer', 'https://www.youtube.com/',
            '--cookies-from-browser', 'firefox',
            '-o', str(output_path),
            f'https://www.youtube.com/watch?v={video_id}'
        ]
    
    async def download_single_video(self, task: DownloadTask) -> DownloadTask:
        """Download a single video asynchronously"""
        task.status = 'downloading'
        task.start_time = time.time()
        
        # Create unique output path
        output_template = self.temp_dir / f"{task.video_id}.%(ext)s"
        cmd = self.get_yt_dlp_command(task.video_id, output_template)
        
        try:
            logger.debug(f"Starting download: {task.video_id} - {task.title[:50]}...")
            
            # Run yt-dlp in subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Find downloaded file
                audio_files = list(self.temp_dir.glob(f"{task.video_id}.*"))
                if audio_files:
                    downloaded_file = audio_files[0]
                    
                    # Move to permanent storage if configured
                    if self.storage_dir:
                        final_path = self.storage_dir / downloaded_file.name
                        self.storage_dir.mkdir(exist_ok=True)
                        shutil.move(str(downloaded_file), str(final_path))
                        task.output_path = final_path
                    else:
                        task.output_path = downloaded_file
                    
                    task.status = 'completed'
                    task.end_time = time.time()
                    self.stats['completed_downloads'] += 1
                    
                    download_time = task.end_time - task.start_time
                    self.stats['total_download_time'] += download_time
                    
                    logger.info(f"✅ Downloaded {task.video_id} in {download_time:.1f}s: {task.output_path.name}")
                else:
                    raise Exception("No audio file found after download")
            else:
                raise Exception(f"yt-dlp failed: {stderr.decode()[:200]}")
                
        except Exception as e:
            task.status = 'failed'
            task.error = str(e)[:500]
            task.end_time = time.time()
            self.stats['failed_downloads'] += 1
            logger.error(f"❌ Download failed {task.video_id}: {task.error}")
        
        return task
    
    async def download_worker(self):
        """Worker coroutine for processing download queue"""
        while True:
            try:
                task = await self.download_queue.get()
                if task is None:  # Shutdown signal
                    break
                
                completed_task = await self.download_single_video(task)
                await self.completed_queue.put(completed_task)
                self.download_queue.task_done()
                
            except Exception as e:
                logger.error(f"Download worker error: {e}")
    
    async def bulk_download(self, video_list: List[Dict[str, Any]]) -> List[DownloadTask]:
        """
        Download multiple videos concurrently
        
        Args:
            video_list: List of video info dicts with 'video_id', 'title', 'url'
            
        Returns:
            List of completed DownloadTask objects
        """
        # Filter out existing videos to avoid wasting resources
        videos_to_download, videos_existing = self.filter_existing_videos(video_list)
        
        # Create download tasks for videos that need downloading
        tasks = []
        for video_info in videos_to_download:
            task = DownloadTask(
                video_id=video_info['video_id'],
                title=video_info.get('title', 'Unknown'),
                url=video_info.get('url', f"https://www.youtube.com/watch?v={video_info['video_id']}"),
                output_path=Path()  # Will be set during download
            )
            tasks.append(task)
            self.download_tasks[task.video_id] = task
        
        # Create "completed" tasks for videos that already exist
        for video_info in videos_existing:
            existing_task = DownloadTask(
                video_id=video_info['video_id'],
                title=video_info.get('title', 'Unknown'),
                url=video_info.get('url', f"https://www.youtube.com/watch?v={video_info['video_id']}"),
                output_path=self.check_audio_exists_locally(video_info['video_id']) or Path(),
                status='completed'  # Mark as completed since it already exists
            )
            tasks.append(existing_task)
            self.download_tasks[existing_task.video_id] = existing_task
        
        self.stats['total_downloads'] = len(tasks)
        logger.info(f"Starting bulk download: {len(tasks)} videos, {self.max_concurrent_downloads} concurrent")
        
        # Start download workers
        workers = [asyncio.create_task(self.download_worker()) 
                  for _ in range(self.max_concurrent_downloads)]
        
        # Queue all downloads
        for task in tasks:
            await self.download_queue.put(task)
        
        # Wait for all downloads to complete
        completed_tasks = []
        for _ in tasks:
            completed_task = await self.completed_queue.get()
            completed_tasks.append(completed_task)
        
        # Shutdown workers
        for _ in range(self.max_concurrent_downloads):
            await self.download_queue.put(None)
        
        await asyncio.gather(*workers)
        
        # Log summary
        success_rate = (self.stats['completed_downloads'] / self.stats['total_downloads']) * 100
        avg_time = self.stats['total_download_time'] / max(1, self.stats['completed_downloads'])
        
        logger.info(f"Bulk download completed: {self.stats['completed_downloads']}/{self.stats['total_downloads']} "
                   f"({success_rate:.1f}% success), avg {avg_time:.1f}s per download")
        
        return completed_tasks
    
    def get_completed_downloads(self) -> List[DownloadTask]:
        """Get list of successfully completed downloads"""
        return [task for task in self.download_tasks.values() if task.status == 'completed']
    
    def get_failed_downloads(self) -> List[DownloadTask]:
        """Get list of failed downloads"""
        return [task for task in self.download_tasks.values() if task.status == 'failed']
    
    def cleanup_temp_files(self):
        """Clean up temporary download directory"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Failed to cleanup temp directory: {e}")

# Example usage
async def example_bulk_download():
    """Example of using AsyncAudioDownloader"""
    
    # Sample video list
    videos = [
        {'video_id': 'dQw4w9WgXcQ', 'title': 'Never Gonna Give You Up'},
        {'video_id': 'J---aiyznGQ', 'title': 'Keyboard Cat'},
        {'video_id': 'kffacxfA7G4', 'title': 'Baby Shark'},
    ]
    
    # Initialize downloader
    downloader = AsyncAudioDownloader(
        max_concurrent_downloads=6,
        storage_dir=Path('./bulk_audio_storage')
    )
    
    try:
        # Download all videos
        completed_tasks = await downloader.bulk_download(videos)
        
        # Process results
        successful = [task for task in completed_tasks if task.status == 'completed']
        failed = [task for task in completed_tasks if task.status == 'failed']
        
        print(f"Downloaded: {len(successful)}, Failed: {len(failed)}")
        
        for task in successful:
            print(f"✅ {task.video_id}: {task.output_path}")
        
        for task in failed:
            print(f"❌ {task.video_id}: {task.error}")
            
    finally:
        downloader.cleanup_temp_files()

if __name__ == '__main__':
    asyncio.run(example_bulk_download())
