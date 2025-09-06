#!/usr/bin/env python3
"""
Batch ingestion script for Ask Dr. Chaffee.

This script provides a robust, resumable batch processing system for ingesting
hundreds of YouTube videos with automatic error recovery, monitoring, and
checkpointing.
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import concurrent.futures
import signal
import traceback

import tqdm
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.list_videos_api import YouTubeAPILister
from scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from scripts.common.database_upsert import DatabaseUpserter
from scripts.ingest_youtube_enhanced import EnhancedYouTubeIngester, IngestionConfig

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('batch_ingestion.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class BatchIngestionManager:
    """Manages batch ingestion of YouTube videos with checkpointing and recovery"""
    
    def __init__(self, config: IngestionConfig, batch_size: int = 50, checkpoint_file: str = 'ingestion_checkpoint.json'):
        self.config = config
        self.batch_size = batch_size
        self.checkpoint_file = checkpoint_file
        self.db = DatabaseUpserter(config.db_url)
        self.shutdown_requested = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Initialize video lister based on source
        if config.source == 'api':
            if not config.youtube_api_key:
                raise ValueError("YouTube API key required for API source")
            self.video_lister = YouTubeAPILister(config.youtube_api_key, config.db_url)
        elif config.source == 'yt-dlp':
            self.video_lister = YtDlpVideoLister()
        else:
            raise ValueError(f"Unknown source: {config.source}")
    
    def _signal_handler(self, sig, frame):
        """Handle termination signals gracefully"""
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    def load_checkpoint(self) -> Tuple[List[str], List[str]]:
        """Load checkpoint of processed and failed video IDs"""
        if not os.path.exists(self.checkpoint_file):
            return [], []
        
        try:
            with open(self.checkpoint_file, 'r') as f:
                checkpoint = json.load(f)
                return checkpoint.get('processed', []), checkpoint.get('failed', [])
        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")
            return [], []
    
    def save_checkpoint(self, processed: List[str], failed: List[str]):
        """Save checkpoint of processed and failed video IDs"""
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump({
                    'processed': processed,
                    'failed': failed,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            logger.info(f"Checkpoint saved: {len(processed)} processed, {len(failed)} failed")
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")
    
    def list_all_videos(self) -> List[VideoInfo]:
        """List all videos from the channel"""
        logger.info(f"Listing all videos using {self.config.source} source")
        
        # Parse since_published if provided
        since_published = None
        if self.config.since_published:
            try:
                # Try ISO8601 format first
                if 'T' in self.config.since_published or '+' in self.config.since_published:
                    since_published = datetime.fromisoformat(
                        self.config.since_published.replace('Z', '+00:00')
                    )
                else:
                    # Try YYYY-MM-DD format
                    since_published = datetime.strptime(
                        self.config.since_published, '%Y-%m-%d'
                    ).replace(tzinfo=timezone.utc)
            except ValueError as e:
                logger.error(f"Invalid since_published format: {self.config.since_published}")
                raise
        
        # List videos from channel
        if self.config.source == 'api':
            videos = self.video_lister.list_channel_videos(
                self.config.channel_url,
                max_results=self.config.limit,
                newest_first=self.config.newest_first,
                since_published=since_published,
                skip_live=self.config.skip_live,
                skip_upcoming=self.config.skip_upcoming,
                skip_members_only=self.config.skip_members_only
            )
        else:
            videos = self.video_lister.list_channel_videos(
                self.config.channel_url,
                max_results=self.config.limit,
                newest_first=self.config.newest_first
            )
        
        # Apply filters
        if self.config.skip_shorts:
            videos = [v for v in videos if not v.duration_s or v.duration_s >= 120]
            logger.info(f"Filtered out shorts, {len(videos)} videos remaining")
        
        # Apply sorting
        if self.config.newest_first:
            videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)
        
        # Apply limit
        if self.config.limit:
            videos = videos[:self.config.limit]
        
        logger.info(f"Found {len(videos)} videos to process")
        return videos
    
    def filter_videos_by_checkpoint(self, videos: List[VideoInfo], processed: List[str], failed: List[str]) -> List[VideoInfo]:
        """Filter videos based on checkpoint and database state"""
        # Skip videos that were already successfully processed
        videos_to_process = [v for v in videos if v.video_id not in processed]
        
        # Check database for completed videos
        for video in list(videos_to_process):
            state = self.db.get_ingest_state(video.video_id)
            if state and state['status'] in ('done', 'upserted'):
                videos_to_process.remove(video)
                if video.video_id not in processed:
                    processed.append(video.video_id)
        
        # Handle failed videos based on retry policy
        if self.config.retry_failed:
            # Include failed videos for retry
            logger.info(f"Will retry {len(failed)} previously failed videos")
        else:
            # Skip failed videos
            videos_to_process = [v for v in videos_to_process if v.video_id not in failed]
        
        logger.info(f"After filtering: {len(videos_to_process)} videos to process")
        return videos_to_process
    
    def process_batch(self, videos: List[VideoInfo], processed: List[str], failed: List[str]) -> Tuple[List[str], List[str]]:
        """Process a batch of videos"""
        if not videos:
            return processed, failed
        
        logger.info(f"Processing batch of {len(videos)} videos")
        
        # Create ingester with current config
        ingester = EnhancedYouTubeIngester(self.config)
        
        # Process videos with concurrent workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            with tqdm.tqdm(total=len(videos), desc="Processing batch") as pbar:
                # Submit all tasks
                future_to_video = {
                    executor.submit(ingester.process_single_video, video): video 
                    for video in videos
                }
                
                # Process completed tasks
                for future in concurrent.futures.as_completed(future_to_video):
                    video = future_to_video[future]
                    try:
                        success = future.result()
                        if success:
                            processed.append(video.video_id)
                        else:
                            failed.append(video.video_id)
                    except Exception as e:
                        logger.error(f"Unexpected error for {video.video_id}: {e}")
                        failed.append(video.video_id)
                    
                    pbar.update(1)
                    pbar.set_postfix({
                        'processed': len(processed),
                        'failed': len(failed)
                    })
                    
                    # Check for shutdown request
                    if self.shutdown_requested:
                        logger.info("Shutdown requested, stopping batch processing")
                        break
        
        # Log batch results
        logger.info(f"Batch completed: {len(processed)} processed, {len(failed)} failed")
        return processed, failed
    
    def run(self):
        """Run the batch ingestion process"""
        start_time = datetime.now()
        logger.info("🚀 Starting batch ingestion process")
        
        try:
            # Load checkpoint
            processed, failed = self.load_checkpoint()
            logger.info(f"Loaded checkpoint: {len(processed)} processed, {len(failed)} failed")
            
            # List all videos
            all_videos = self.list_all_videos()
            
            # Filter videos based on checkpoint
            videos_to_process = self.filter_videos_by_checkpoint(all_videos, processed, failed)
            
            # Process in batches
            total_batches = (len(videos_to_process) + self.batch_size - 1) // self.batch_size
            logger.info(f"Processing {len(videos_to_process)} videos in {total_batches} batches")
            
            for batch_num in range(total_batches):
                if self.shutdown_requested:
                    logger.info("Shutdown requested, stopping ingestion")
                    break
                
                batch_start = batch_num * self.batch_size
                batch_end = min(batch_start + self.batch_size, len(videos_to_process))
                batch = videos_to_process[batch_start:batch_end]
                
                logger.info(f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} videos)")
                processed, failed = self.process_batch(batch, processed, failed)
                
                # Save checkpoint after each batch
                self.save_checkpoint(processed, failed)
                
                # Sleep between batches to avoid API rate limits
                if batch_num < total_batches - 1 and not self.shutdown_requested:
                    logger.info(f"Sleeping for {self.config.batch_delay_seconds} seconds between batches")
                    time.sleep(self.config.batch_delay_seconds)
            
            # Final checkpoint save
            self.save_checkpoint(processed, failed)
            
        except Exception as e:
            logger.error(f"Batch ingestion error: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            # Log final statistics
            end_time = datetime.now()
            duration = end_time - start_time
            logger.info(f"Batch ingestion completed in {duration}")
            
            # Get final stats
            stats = self.db.get_ingestion_stats()
            logger.info(f"Final statistics:")
            logger.info(f"  Total videos: {stats['total_videos']}")
            logger.info(f"  Total sources: {stats['total_sources']}")
            logger.info(f"  Total chunks: {stats['total_chunks']}")
            logger.info(f"  Status breakdown:")
            for status, count in stats['status_counts'].items():
                logger.info(f"    {status}: {count}")
            
            # Close database connection
            self.db.close_connection()

def parse_args() -> Tuple[IngestionConfig, int, int, bool, str]:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Batch YouTube transcript ingestion for Ask Dr. Chaffee',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all videos in batches of 50
  python batch_ingestion.py --batch-size 50
  
  # Process videos published since 2023
  python batch_ingestion.py --since-published 2023-01-01
  
  # Resume from checkpoint with retries
  python batch_ingestion.py --retry-failed
        """
    )
    
    # Source configuration
    parser.add_argument('--source', choices=['api', 'yt-dlp'], default='api',
                       help='Data source: api for YouTube Data API (default), yt-dlp for scraping fallback')
    parser.add_argument('--from-json', type=Path,
                       help='Process videos from JSON file instead of fetching')
    parser.add_argument('--channel-url',
                       help='YouTube channel URL (default: env YOUTUBE_CHANNEL_URL)')
    parser.add_argument('--since-published',
                       help='Only process videos published after this date (ISO8601 or YYYY-MM-DD)')
    
    # Batch processing configuration
    parser.add_argument('--batch-size', type=int, default=50,
                       help='Number of videos to process in each batch (default: 50)')
    parser.add_argument('--batch-delay', type=int, default=60,
                       help='Seconds to wait between batches (default: 60)')
    parser.add_argument('--checkpoint-file', default='ingestion_checkpoint.json',
                       help='Checkpoint file path (default: ingestion_checkpoint.json)')
    parser.add_argument('--retry-failed', action='store_true',
                       help='Retry previously failed videos')
    
    # Processing configuration
    parser.add_argument('--concurrency', type=int, default=4,
                       help='Concurrent workers for processing (default: 4)')
    parser.add_argument('--skip-shorts', action='store_true',
                       help='Skip videos shorter than 120 seconds')
    parser.add_argument('--newest-first', action='store_true', default=True,
                       help='Process newest videos first (default: true)')
    parser.add_argument('--limit', type=int,
                       help='Maximum number of videos to process')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without writing to DB')
    
    # Content filtering options
    parser.add_argument('--include-live', action='store_false', dest='skip_live',
                       help='Include live streams (skipped by default)')
    parser.add_argument('--include-upcoming', action='store_false', dest='skip_upcoming',
                       help='Include upcoming streams (skipped by default)')
    parser.add_argument('--include-members-only', action='store_false', dest='skip_members_only',
                       help='Include members-only content (skipped by default)')
    
    # Whisper configuration
    parser.add_argument('--whisper-model', default='small.en',
                       choices=['tiny.en', 'base.en', 'small.en', 'medium.en', 'large-v3'],
                       help='Whisper model size (default: small.en)')
    parser.add_argument('--max-duration', type=int,
                       help='Skip videos longer than N seconds for Whisper fallback')
    parser.add_argument('--force-whisper', action='store_true',
                       help='Use Whisper even when YouTube transcript available')
    parser.add_argument('--ffmpeg-path', 
                       help='Path to ffmpeg executable for audio processing')
                       
    # Proxy configuration
    parser.add_argument('--proxy',
                       help='HTTP/HTTPS proxy to use for YouTube requests (e.g., http://user:pass@host:port)')
    parser.add_argument('--proxy-file',
                       help='Path to file containing list of proxies (one per line)')
    parser.add_argument('--proxy-rotate', action='store_true',
                       help='Enable proxy rotation')
    parser.add_argument('--proxy-rotate-interval', type=int, default=10,
                       help='Minutes between proxy rotations (default: 10)')
    
    # Database configuration
    parser.add_argument('--db-url',
                       help='Database URL (default: env DATABASE_URL)')
    
    # API configuration
    parser.add_argument('--youtube-api-key',
                       help='YouTube Data API key (default: env YOUTUBE_API_KEY)')
    
    # Debug options
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create config
    config = IngestionConfig(
        source=args.source,
        channel_url=args.channel_url,
        from_json=args.from_json,
        concurrency=args.concurrency,
        skip_shorts=args.skip_shorts,
        newest_first=args.newest_first,
        limit=args.limit,
        dry_run=args.dry_run,
        whisper_model=args.whisper_model,
        max_duration=args.max_duration,
        force_whisper=args.force_whisper,
        db_url=args.db_url,
        youtube_api_key=args.youtube_api_key,
        # Content filtering options
        skip_live=args.skip_live,
        skip_upcoming=args.skip_upcoming,
        skip_members_only=args.skip_members_only
    )
    
    # Add batch-specific attributes
    setattr(config, 'batch_delay_seconds', args.batch_delay)
    setattr(config, 'retry_failed', args.retry_failed)
    
    return config, args.batch_size, args.batch_delay, args.retry_failed, args.checkpoint_file

def main():
    """Main entry point"""
    try:
        config, batch_size, batch_delay, retry_failed, checkpoint_file = parse_args()
        
        # Create and run batch manager
        batch_manager = BatchIngestionManager(
            config=config,
            batch_size=batch_size,
            checkpoint_file=checkpoint_file
        )
        batch_manager.run()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
