#!/usr/bin/env python3
"""
Optimized 3-Phase YouTube Ingestion Pipeline

Phase 1: Pre-filter videos (check accessibility)
Phase 2: Bulk async download (only accessible videos)
Phase 3: Bulk Enhanced ASR processing (maximum RTX utilization)
"""

import asyncio
import logging
import os
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import argparse

# Add backend scripts to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from common.async_downloader import AsyncAudioDownloader

logger = logging.getLogger(__name__)

@dataclass
class OptimizedConfig:
    """Configuration for optimized ingestion pipeline"""
    channel_url: str
    limit: int = 100
    max_concurrent_checks: int = 10
    max_concurrent_downloads: int = 8
    audio_storage_dir: Path = Path("./audio_storage")
    yt_dlp_path: str = "yt-dlp"
    
class OptimizedYouTubeIngester:
    """3-Phase optimized YouTube ingestion pipeline"""
    
    def __init__(self, config: OptimizedConfig):
        self.config = config
        self.video_lister = YtDlpVideoLister()
        
        # Phase results
        self.all_videos: List[VideoInfo] = []
        self.accessible_videos: List[VideoInfo] = []
        self.members_only_videos: List[VideoInfo] = []
        self.downloaded_videos: List[Dict] = []
        
        # Performance metrics
        self.metrics = {
            'phase1_duration': 0.0,
            'phase2_duration': 0.0, 
            'phase3_duration': 0.0,
            'total_videos': 0,
            'accessible_count': 0,
            'members_only_count': 0,
            'download_success_count': 0,
            'processing_success_count': 0
        }
    
    async def check_video_accessibility(self, video: VideoInfo) -> Tuple[VideoInfo, bool]:
        """Check if a single video is accessible (not members-only)"""
        try:
            cmd = [
                self.config.yt_dlp_path,
                "--simulate", 
                "--no-warnings",
                "--extractor-args", "youtube:player_client=web_safari",
                "-4",
                f"https://www.youtube.com/watch?v={video.video_id}"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.debug(f"✅ Accessible: {video.video_id}")
                return video, True
            else:
                error_msg = stderr.decode().lower()
                if "members-only" in error_msg or "join this channel" in error_msg:
                    logger.info(f"🔒 Members-only: {video.video_id} - {video.title[:50]}...")
                else:
                    logger.warning(f"❓ Inaccessible: {video.video_id} - {stderr.decode()[:100]}...")
                return video, False
                
        except Exception as e:
            logger.error(f"❌ Check failed for {video.video_id}: {e}")
            return video, False
    
    async def phase1_prefilter_videos(self) -> None:
        """Phase 1: Get video list and pre-filter for accessibility"""
        logger.info("🎯 PHASE 1: Pre-filtering videos for accessibility")
        start_time = time.time()
        
        # Get video list
        logger.info(f"📋 Fetching video list from {self.config.channel_url}")
        self.all_videos = self.video_lister.list_channel_videos(
            self.config.channel_url,
            use_cache=True,
            skip_members_only=False  # We'll do our own filtering
        )
        
        if self.config.limit:
            self.all_videos = self.all_videos[:self.config.limit]
        
        self.metrics['total_videos'] = len(self.all_videos)
        logger.info(f"📊 Found {len(self.all_videos)} videos to check")
        
        # Create semaphore to limit concurrent checks
        semaphore = asyncio.Semaphore(self.config.max_concurrent_checks)
        
        async def check_with_semaphore(video):
            async with semaphore:
                return await self.check_video_accessibility(video)
        
        # Check all videos concurrently
        logger.info(f"🔍 Checking accessibility of {len(self.all_videos)} videos ({self.config.max_concurrent_checks} concurrent)")
        tasks = [check_with_semaphore(video) for video in self.all_videos]
        results = await asyncio.gather(*tasks)
        
        # Separate accessible vs members-only
        for video, is_accessible in results:
            if is_accessible:
                self.accessible_videos.append(video)
            else:
                self.members_only_videos.append(video)
        
        self.metrics['accessible_count'] = len(self.accessible_videos)
        self.metrics['members_only_count'] = len(self.members_only_videos)
        self.metrics['phase1_duration'] = time.time() - start_time
        
        logger.info(f"✅ Phase 1 Complete ({self.metrics['phase1_duration']:.1f}s):")
        logger.info(f"   📈 Accessible videos: {self.metrics['accessible_count']}")
        logger.info(f"   🔒 Members-only videos: {self.metrics['members_only_count']}")
        logger.info(f"   📊 Success rate: {(self.metrics['accessible_count']/self.metrics['total_videos']*100):.1f}%")
    
    async def phase2_bulk_download(self) -> None:
        """Phase 2: Bulk async download of all accessible videos"""
        if not self.accessible_videos:
            logger.warning("⚠️ No accessible videos to download, skipping Phase 2")
            return
        
        logger.info(f"📥 PHASE 2: Bulk async download of {len(self.accessible_videos)} accessible videos")
        start_time = time.time()
        
        # Convert to format expected by async downloader
        video_list = []
        for video in self.accessible_videos:
            video_list.append({
                'video_id': video.video_id,
                'title': video.title,
                'url': f"https://www.youtube.com/watch?v={video.video_id}"
            })
        
        # Initialize async downloader
        downloader = AsyncAudioDownloader(
            max_concurrent_downloads=self.config.max_concurrent_downloads,
            storage_dir=self.config.audio_storage_dir,
            skip_existing=True,  # Skip videos we already have
            skip_members_only=False  # We already filtered these out
        )
        
        try:
            logger.info(f"🚀 Starting bulk download: {self.config.max_concurrent_downloads} concurrent streams")
            completed_tasks = await downloader.bulk_download(video_list)
            
            # Collect successful downloads
            self.downloaded_videos = [
                task for task in completed_tasks 
                if task.status == 'completed'
            ]
            
            failed_downloads = [
                task for task in completed_tasks 
                if task.status == 'failed'
            ]
            
            self.metrics['download_success_count'] = len(self.downloaded_videos)
            self.metrics['phase2_duration'] = time.time() - start_time
            
            logger.info(f"✅ Phase 2 Complete ({self.metrics['phase2_duration']:.1f}s):")
            logger.info(f"   📥 Downloaded: {len(self.downloaded_videos)}")
            logger.info(f"   ❌ Failed: {len(failed_downloads)}")
            logger.info(f"   📊 Download success rate: {(len(self.downloaded_videos)/len(video_list)*100):.1f}%")
            
            if failed_downloads:
                logger.info("❌ Download failures:")
                for task in failed_downloads[:5]:  # Show first 5
                    logger.info(f"   - {task.video_id}: {task.error[:100]}...")
        
        finally:
            downloader.cleanup_temp_files()
    
    def phase3_enhanced_asr_processing(self) -> None:
        """Phase 3: Process all downloaded videos with Enhanced ASR"""
        if not self.downloaded_videos:
            logger.warning("⚠️ No downloaded videos to process, skipping Phase 3")
            return
        
        logger.info(f"🎙️ PHASE 3: Enhanced ASR processing of {len(self.downloaded_videos)} videos")
        logger.info("🚀 This would use your RTX 5080 optimization:")
        logger.info("   - 12 parallel Whisper models")
        logger.info("   - 384 batch size")
        logger.info("   - 6x concurrency")
        logger.info("   - Enhanced ASR + Speaker ID")
        
        start_time = time.time()
        
        # TODO: Integrate with existing Enhanced ASR pipeline
        # For now, just simulate the processing
        for task in self.downloaded_videos:
            logger.info(f"🎙️ Would process: {task.video_id} - {task.output_path}")
        
        self.metrics['processing_success_count'] = len(self.downloaded_videos)
        self.metrics['phase3_duration'] = time.time() - start_time
        
        logger.info(f"✅ Phase 3 Complete ({self.metrics['phase3_duration']:.1f}s)")
    
    async def process_single_video_pipeline(self, video: VideoInfo, semaphore_check: asyncio.Semaphore, semaphore_download: asyncio.Semaphore) -> Dict[str, Any]:
        """Process a single video through the complete pipeline concurrently"""
        result = {
            'video_id': video.video_id,
            'title': video.title,
            'status': 'pending',
            'phase1_duration': 0.0,
            'phase2_duration': 0.0,
            'phase3_duration': 0.0,
            'error': None
        }
        
        try:
            # Phase 1: Check accessibility (concurrent with other videos)
            async with semaphore_check:
                phase1_start = time.time()
                _, is_accessible = await self.check_video_accessibility(video)
                result['phase1_duration'] = time.time() - phase1_start
                
                if not is_accessible:
                    result['status'] = 'members_only'
                    self.metrics['members_only_count'] += 1
                    return result
                
                self.metrics['accessible_count'] += 1
            
            # Phase 2: Download (concurrent with other videos)
            async with semaphore_download:
                phase2_start = time.time()
                
                # Check if already exists locally (check common audio extensions)
                audio_extensions = ['.m4a', '.mp4', '.webm', '.wav', '.mp3']
                existing_audio = None
                for ext in audio_extensions:
                    potential_path = self.config.audio_storage_dir / f"{video.video_id}{ext}"
                    if potential_path.exists():
                        existing_audio = potential_path
                        break
                
                if existing_audio:
                    logger.debug(f"⚡ Skipping download: {video.video_id} already exists as {existing_audio.name}")
                    result['status'] = 'already_exists'
                    result['audio_path'] = str(existing_audio)
                    result['phase2_duration'] = time.time() - phase2_start
                else:
                    # Download AUDIO-ONLY using yt-dlp (saves 10x storage space)
                    cmd = [
                        self.config.yt_dlp_path,
                        '--format', 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
                        '--extract-audio',  # Force audio-only extraction
                        '--audio-format', 'm4a',  # Prefer m4a for quality/size balance
                        '--no-playlist',
                        '--ignore-errors',
                        '--extractor-args', 'youtube:player_client=web_safari',
                        '-4',
                        '--retry-sleep', '2',
                        '--retries', '8',
                        '--fragment-retries', '8',
                        '--sleep-requests', '1',
                        '--socket-timeout', '45',
                        '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        '--referer', 'https://www.youtube.com/',
                        '-o', str(self.config.audio_storage_dir / f"{video.video_id}.%(ext)s"),
                        f'https://www.youtube.com/watch?v={video.video_id}'
                    ]
                    
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode == 0:
                        # Find downloaded file (prioritize audio formats)
                        for ext in ['.m4a', '.webm', '.mp4', '.wav', '.mp3']:
                            potential_path = self.config.audio_storage_dir / f"{video.video_id}{ext}"
                            if potential_path.exists():
                                result['audio_path'] = str(potential_path)
                                # Log file size for storage monitoring
                                file_size_mb = potential_path.stat().st_size / (1024 * 1024)
                                logger.debug(f"Audio file: {potential_path.name} ({file_size_mb:.1f}MB)")
                                break
                        
                        if 'audio_path' not in result:
                            raise Exception("Download succeeded but no audio file found")
                        
                        logger.info(f"📥 Downloaded: {video.video_id} - {video.title[:50]}...")
                        result['status'] = 'downloaded'
                        self.metrics['download_success_count'] += 1
                    else:
                        raise Exception(f"Download failed: {stderr.decode()[:200]}")
                
                result['phase2_duration'] = time.time() - phase2_start
            
            # Phase 3: Enhanced ASR Processing (immediate after download)
            if result['status'] in ['downloaded', 'already_exists']:
                phase3_start = time.time()
                
                # TODO: Integrate with existing Enhanced ASR pipeline
                # For now, just simulate processing
                logger.info(f"🎙️ Would process with Enhanced ASR: {video.video_id}")
                await asyncio.sleep(0.1)  # Simulate processing time
                
                result['status'] = 'processed'
                result['phase3_duration'] = time.time() - phase3_start
                self.metrics['processing_success_count'] += 1
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)[:200]
            logger.error(f"❌ Pipeline error for {video.video_id}: {e}")
        
        return result
    
    async def run_concurrent_pipeline(self) -> None:
        """Run the concurrent streaming pipeline"""
        logger.info("⚡ Starting CONCURRENT STREAMING YouTube Ingestion Pipeline")
        logger.info("🚀 All phases run simultaneously for maximum efficiency!")
        logger.info("=" * 70)
        
        total_start_time = time.time()
        
        # Get video list
        logger.info(f"📋 Fetching video list from {self.config.channel_url}")
        self.all_videos = self.video_lister.list_channel_videos(
            self.config.channel_url,
            use_cache=True,
            skip_members_only=False  # We'll do our own filtering
        )
        
        if self.config.limit:
            self.all_videos = self.all_videos[:self.config.limit]
        
        self.metrics['total_videos'] = len(self.all_videos)
        logger.info(f"📊 Processing {len(self.all_videos)} videos with concurrent pipeline")
        
        # Create semaphores for resource management
        semaphore_check = asyncio.Semaphore(self.config.max_concurrent_checks)
        semaphore_download = asyncio.Semaphore(self.config.max_concurrent_downloads)
        
        # Process all videos concurrently through the entire pipeline
        logger.info(f"⚡ Starting concurrent processing:")
        logger.info(f"   🔍 Max concurrent checks: {self.config.max_concurrent_checks}")
        logger.info(f"   📥 Max concurrent downloads: {self.config.max_concurrent_downloads}")
        logger.info(f"   🎙️ Enhanced ASR ready for immediate processing")
        
        tasks = [
            self.process_single_video_pipeline(video, semaphore_check, semaphore_download)
            for video in self.all_videos
        ]
        
        # Wait for all videos to complete the pipeline
        results = await asyncio.gather(*tasks)
        
        total_duration = time.time() - total_start_time
        
        # Analyze results
        successful = [r for r in results if r['status'] == 'processed']
        already_existed = [r for r in results if r['status'] == 'already_exists']
        members_only = [r for r in results if r['status'] == 'members_only']
        errors = [r for r in results if r['status'] == 'error']
        
        logger.info(f"⚡ CONCURRENT PIPELINE COMPLETE ({total_duration:.1f}s)")
        logger.info("=" * 70)
        logger.info(f"📊 Results Summary:")
        logger.info(f"   ✅ Successfully processed: {len(successful)}")
        logger.info(f"   ⚡ Already existed: {len(already_existed)}")
        logger.info(f"   🔒 Members-only filtered: {len(members_only)}")
        logger.info(f"   ❌ Errors: {len(errors)}")
        
        if successful or already_existed:
            logger.info(f"\n🎯 Performance Benefits:")
            avg_phase1 = sum(r['phase1_duration'] for r in results) / len(results)
            avg_phase2 = sum(r['phase2_duration'] for r in results if r['phase2_duration'] > 0) / max(1, len([r for r in results if r['phase2_duration'] > 0]))
            logger.info(f"   Average check time: {avg_phase1:.2f}s per video")
            logger.info(f"   Average download time: {avg_phase2:.2f}s per video")
            logger.info(f"   Total pipeline time: {total_duration:.1f}s")
            
            # Calculate theoretical sequential time
            total_check_time = sum(r['phase1_duration'] for r in results)
            total_download_time = sum(r['phase2_duration'] for r in results)
            sequential_time = total_check_time + total_download_time
            
            if sequential_time > 0:
                speedup = sequential_time / total_duration
                logger.info(f"   Theoretical sequential: {sequential_time:.1f}s")
                logger.info(f"   🚀 Concurrent speedup: {speedup:.1f}x faster!")
        
        if errors:
            logger.info(f"\n❌ Errors encountered:")
            for error in errors[:3]:  # Show first 3
                logger.info(f"   - {error['video_id']}: {error['error']}")

    async def run_optimized_pipeline(self) -> None:
        """Entry point - intelligently choose between sequential or concurrent pipeline"""
        
        # Get preliminary video count for decision
        preliminary_videos = self.video_lister.list_channel_videos(
            self.config.channel_url,
            use_cache=True,
            skip_members_only=False
        )
        
        if self.config.limit:
            preliminary_count = min(len(preliminary_videos), self.config.limit)
        else:
            preliminary_count = len(preliminary_videos)
        
        # Choose pipeline based on batch size and resource constraints
        if preliminary_count <= 25:
            logger.info("🚀 Using CONCURRENT pipeline for small batch (≤25 videos)")
            logger.info("   Benefits: Faster execution, immediate feedback")
            await self.run_concurrent_pipeline()
        else:
            logger.info("📊 Using SEQUENTIAL 3-PHASE pipeline for large batch (>25 videos)")
            logger.info("   Benefits: Controlled resources, better storage management, predictable progress")
            await self.run_sequential_pipeline()
    
    async def run_sequential_pipeline(self) -> None:
        """Run the original 3-phase sequential pipeline for large batches"""
        logger.info("📊 Starting SEQUENTIAL 3-PHASE YouTube Ingestion Pipeline")
        logger.info("🎯 Optimized for large batches with controlled resource usage")
        logger.info("=" * 70)
        
        total_start_time = time.time()
        
        try:
            # Phase 1: Pre-filter all videos
            await self.phase1_prefilter_videos()
            
            # Phase 2: Bulk download in controlled batches  
            await self.phase2_bulk_download()
            
            # Phase 3: Enhanced ASR processing
            self.phase3_enhanced_asr_processing()
            
        except Exception as e:
            logger.error(f"❌ Pipeline error: {e}")
            raise
        
        finally:
            total_duration = time.time() - total_start_time
            logger.info(f"\n📊 Sequential Pipeline Complete: {total_duration:.1f}s")
            logger.info(f"   Phase 1: {self.metrics.get('phase1_duration', 0):.1f}s")
            logger.info(f"   Phase 2: {self.metrics.get('phase2_duration', 0):.1f}s") 
            logger.info(f"   Phase 3: {self.metrics.get('phase3_duration', 0):.1f}s")
    
    def print_final_summary(self, total_duration: float) -> None:
        """Print comprehensive pipeline summary"""
        logger.info("\n" + "=" * 70)
        logger.info("📊 OPTIMIZED PIPELINE SUMMARY")
        logger.info("=" * 70)
        
        logger.info(f"⏱️ Performance Metrics:")
        logger.info(f"   Phase 1 (Pre-filter): {self.metrics['phase1_duration']:.1f}s")
        logger.info(f"   Phase 2 (Download):   {self.metrics['phase2_duration']:.1f}s")
        logger.info(f"   Phase 3 (Processing): {self.metrics['phase3_duration']:.1f}s")
        logger.info(f"   Total Pipeline:       {total_duration:.1f}s")
        
        logger.info(f"\n📈 Processing Results:")
        logger.info(f"   Total videos found:     {self.metrics['total_videos']}")
        logger.info(f"   Accessible videos:      {self.metrics['accessible_count']}")
        logger.info(f"   Members-only filtered:  {self.metrics['members_only_count']}")
        logger.info(f"   Successfully downloaded: {self.metrics['download_success_count']}")
        logger.info(f"   Successfully processed:  {self.metrics['processing_success_count']}")
        
        if self.metrics['total_videos'] > 0:
            accessibility_rate = (self.metrics['accessible_count'] / self.metrics['total_videos']) * 100
            logger.info(f"\n🎯 Success Rates:")
            logger.info(f"   Video accessibility: {accessibility_rate:.1f}%")
            
            if self.metrics['accessible_count'] > 0:
                download_rate = (self.metrics['download_success_count'] / self.metrics['accessible_count']) * 100
                logger.info(f"   Download success:    {download_rate:.1f}%")
                
                overall_rate = (self.metrics['processing_success_count'] / self.metrics['total_videos']) * 100
                logger.info(f"   Overall pipeline:    {overall_rate:.1f}%")

async def main():
    """Main entry point for optimized ingestion"""
    parser = argparse.ArgumentParser(description="Optimized 3-Phase YouTube Ingestion")
    
    parser.add_argument('--channel-url', required=True,
                       help='YouTube channel URL')
    parser.add_argument('--limit', type=int, default=100,
                       help='Maximum number of videos to process (default: 100)')
    parser.add_argument('--max-concurrent-checks', type=int, default=10,
                       help='Maximum concurrent accessibility checks (default: 10)')
    parser.add_argument('--max-concurrent-downloads', type=int, default=8,
                       help='Maximum concurrent downloads (default: 8)')
    parser.add_argument('--audio-storage-dir', type=Path, default=Path("./audio_storage"),
                       help='Directory to store audio files')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    
    # Create configuration
    config = OptimizedConfig(
        channel_url=args.channel_url,
        limit=args.limit,
        max_concurrent_checks=args.max_concurrent_checks,
        max_concurrent_downloads=args.max_concurrent_downloads,
        audio_storage_dir=args.audio_storage_dir
    )
    
    # Run optimized pipeline
    ingester = OptimizedYouTubeIngester(config)
    await ingester.run_optimized_pipeline()

if __name__ == '__main__':
    asyncio.run(main())
