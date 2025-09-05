#!/usr/bin/env python3
"""
Robust, resumable YouTube ingestion pipeline for Ask Dr. Chaffee.

Features:
- Resumable pipeline with ingest_state tracking
- Batch processing with concurrency controls
- Support for yt-dlp JSON dumps and API sources
- Idempotent operations with ON CONFLICT handling
- Comprehensive error tracking and retry logic
- Production-ready logging and monitoring
"""

import os
import sys
import argparse
import logging
import json
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import time

# Third-party imports
import tqdm
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from scripts.common.list_videos_api import YouTubeAPILister
from scripts.common.transcript_fetch import TranscriptFetcher, TranscriptSegment
from scripts.common.database_upsert import DatabaseUpserter, ChunkData
from scripts.common.embeddings import EmbeddingGenerator
from scripts.common.transcript_processor import TranscriptProcessor

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_ingestion.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class IngestConfig:
    """Configuration for the ingestion pipeline"""
    # Data source
    source: str = 'yt-dlp'  # 'yt-dlp' or 'api'
    from_json: Optional[Path] = None
    channel_url: str = None
    
    # Processing limits
    concurrency: int = 4
    limit: Optional[int] = None
    skip_shorts: bool = False
    max_duration: Optional[int] = None
    newest_first: bool = False
    
    # Execution modes
    dry_run: bool = False
    
    # Database
    db_url: str = None
    
    # API keys
    youtube_api_key: Optional[str] = None
    
    # Whisper/ffmpeg
    ffmpeg_path: Optional[str] = None
    proxy: Optional[str] = None
    
    def __post_init__(self):
        if self.channel_url is None:
            self.channel_url = os.getenv('YOUTUBE_CHANNEL_URL', 'https://www.youtube.com/@anthonychaffeemd')
        
        if self.db_url is None:
            self.db_url = os.getenv('DATABASE_URL')
            if not self.db_url:
                raise ValueError("DATABASE_URL environment variable required")
        
        if self.source == 'api':
            if self.youtube_api_key is None:
                self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')
            if not self.youtube_api_key:
                raise ValueError("YOUTUBE_API_KEY required for API source")

@dataclass
class BatchStats:
    """Statistics for a processing batch"""
    total: int = 0
    processed: int = 0
    skipped: int = 0
    errors: int = 0
    done: int = 0
    
    def log_batch_summary(self, batch_num: int):
        """Log summary for this batch"""
        logger.info(f"=== BATCH {batch_num} SUMMARY ===")
        logger.info(f"Processed: {self.processed}, Done: {self.done}, Errors: {self.errors}, Skipped: {self.skipped}")
        
        if self.total > 0:
            success_rate = (self.done / self.total) * 100
            logger.info(f"Batch success rate: {success_rate:.1f}%")

class RobustYouTubeIngester:
    """Production-ready YouTube ingestion pipeline with resumability"""
    
    def __init__(self, config: IngestConfig):
        self.config = config
        
        # Initialize components
        self.db = DatabaseUpserter(config.db_url)
        
        # Setup proxies if provided
        proxies = None
        if config.proxy:
            proxies = {
                'http': config.proxy,
                'https': config.proxy
            }
            
        self.transcript_fetcher = TranscriptFetcher(
            ffmpeg_path=config.ffmpeg_path,
            proxies=proxies
        )
        self.embedder = EmbeddingGenerator()
        self.processor = TranscriptProcessor(
            chunk_duration_seconds=int(os.getenv('CHUNK_DURATION_SECONDS', 45))
        )
        
        # Initialize video lister based on source
        if config.source == 'yt-dlp':
            self.video_lister = YtDlpVideoLister()
        elif config.source == 'api':
            self.video_lister = YouTubeAPILister(config.youtube_api_key)
        else:
            raise ValueError(f"Unknown source: {config.source}")
    
    def list_videos(self) -> List[VideoInfo]:
        """List videos using configured source"""
        logger.info(f"Listing videos using {self.config.source} source")
        
        if self.config.from_json:
            # Load from JSON file (yt-dlp only)
            if self.config.source != 'yt-dlp':
                raise ValueError("--from-json only supported with yt-dlp source")
            videos = self.video_lister.list_from_json(self.config.from_json)
        else:
            # List from channel
            if self.config.source == 'yt-dlp':
                videos = self.video_lister.list_channel_videos(self.config.channel_url)
            else:  # api
                videos = self.video_lister.list_channel_videos(
                    self.config.channel_url,
                    max_results=self.config.limit
                )
        
        # Apply filters
        if self.config.skip_shorts:
            videos = [v for v in videos if not v.duration_s or v.duration_s >= 120]
            logger.info(f"Filtered out shorts, {len(videos)} videos remaining")
        
        if self.config.max_duration:
            videos = [v for v in videos if not v.duration_s or v.duration_s <= self.config.max_duration]
            logger.info(f"Filtered by max duration, {len(videos)} videos remaining")
        
        # Apply sorting
        if self.config.newest_first:
            videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)
        else:
            videos.sort(key=lambda v: v.published_at or datetime.min)
        
        # Apply limit
        if self.config.limit:
            videos = videos[:self.config.limit]
        
        logger.info(f"Found {len(videos)} videos to process")
        return videos
    
    def get_pending_videos(self, batch_size: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get videos that need processing (resumable queue)"""
        # Get videos in pending or error state (with retry limits)
        pending_videos = self.db.get_videos_by_status('pending', limit=batch_size)
        error_videos = []
        
        # Add error videos that haven't exceeded retry limit
        all_error_videos = self.db.get_videos_by_status('error', limit=batch_size * 2 if batch_size else None)
        for video in all_error_videos:
            if video.get('retries', 0) < 3:
                error_videos.append(video)
        
        combined = pending_videos + error_videos
        
        if batch_size:
            combined = combined[:batch_size]
        
        logger.info(f"Found {len(pending_videos)} pending + {len(error_videos)} retryable error videos")
        return combined
    
    def should_skip_video(self, video_info: VideoInfo) -> Tuple[bool, str]:
        """Check if video should be skipped based on current state"""
        state = self.db.get_ingest_state(video_info.video_id)
        
        if state:
            if state['status'] in ('done', 'upserted'):
                return True, f"already completed (status: {state['status']})"
            elif state['status'] == 'error' and state.get('retries', 0) >= 3:
                return True, f"max retries exceeded ({state.get('retries', 0)})"
        
        return False, ""
    
    def process_single_video(self, video_info: VideoInfo) -> bool:
        """Process a single video through the complete pipeline"""
        video_id = video_info.video_id
        
        try:
            # Check if should skip
            should_skip, reason = self.should_skip_video(video_info)
            if should_skip:
                logger.debug(f"Skipping {video_id}: {reason}")
                return True
            
            logger.info(f"Processing {video_id}: {video_info.title}")
            
            # Step 0: Initialize/update ingest state
            self.db.upsert_ingest_state(video_id, video_info, status='pending')
            
            # Step 1: Fetch transcript
            segments, method = self.transcript_fetcher.fetch_transcript(
                video_id,
                max_duration_s=self.config.max_duration
            )
            
            if not segments:
                self.db.update_ingest_status(
                    video_id, 'error',
                    error="Failed to fetch transcript",
                    increment_retries=True
                )
                return False
            
            # Update transcript status
            status = 'transcribed'  # Use valid status from constraint
            self.db.update_ingest_status(
                video_id, status,
                has_yt_transcript=(method == 'youtube'),
                has_whisper=(method == 'whisper')
            )
            
            # Step 2: Chunk transcript 
            chunks = []
            for i, segment in enumerate(segments):
                chunk = ChunkData.from_transcript_segment(segment, video_id)
                chunks.append(chunk)
            
            self.db.update_ingest_status(
                video_id, 'chunked',
                chunk_count=len(chunks)
            )
            
            # Step 3: Generate embeddings
            texts = [chunk.text for chunk in chunks]
            embeddings = self.embedder.generate_embeddings(texts)
            
            # Attach embeddings to chunks
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding
            
            self.db.update_ingest_status(
                video_id, 'embedded',
                embedding_count=len(embeddings)
            )
            
            # Step 4: Upsert to database
            source_id = self.db.upsert_source(video_info, source_type='youtube')
            
            # Update chunks with correct source_id
            for chunk in chunks:
                chunk.source_id = source_id
            
            chunk_count = self.db.upsert_chunks(chunks)
            self.db.update_ingest_status(video_id, 'upserted')
            
            # Final status
            self.db.update_ingest_status(video_id, 'done')
            
            logger.info(f"✅ Completed {video_id}: {len(chunks)} chunks, {method} transcript")
            return True
            
        except Exception as e:
            error_msg = str(e)[:500]  # Truncate long errors
            logger.error(f"❌ Error processing {video_id}: {error_msg}")
            
            try:
                self.db.update_ingest_status(
                    video_id, 'error',
                    error=error_msg,
                    increment_retries=True
                )
            except Exception as db_error:
                logger.error(f"Failed to update error status: {db_error}")
            
            return False
    
    def process_batch_concurrent(self, videos: List[VideoInfo], batch_num: int = 1) -> BatchStats:
        """Process a batch of videos with concurrency"""
        stats = BatchStats(total=len(videos))
        
        if self.config.dry_run:
            for video in videos:
                logger.info(f"DRY RUN: Would process {video.video_id}: {video.title}")
            return stats
        
        # Use ThreadPoolExecutor for I/O bound tasks
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            with tqdm.tqdm(total=len(videos), desc=f"Batch {batch_num}") as pbar:
                # Submit all tasks
                future_to_video = {
                    executor.submit(self.process_single_video, video): video
                    for video in videos
                }
                
                # Process completed tasks
                for future in concurrent.futures.as_completed(future_to_video):
                    video = future_to_video[future]
                    try:
                        success = future.result()
                        if success:
                            # Check final status to update stats
                            state = self.db.get_ingest_state(video.video_id)
                            if state and state['status'] == 'done':
                                stats.done += 1
                            else:
                                stats.processed += 1
                        else:
                            stats.errors += 1
                    except Exception as e:
                        logger.error(f"Unexpected error for {video.video_id}: {e}")
                        stats.errors += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({
                        'done': stats.done,
                        'errors': stats.errors
                    })
        
        stats.log_batch_summary(batch_num)
        return stats
    
    def run_backfill(self) -> None:
        """Run backfill operation (resumable)"""
        start_time = datetime.now()
        logger.info("🚀 Starting YouTube backfill pipeline")
        logger.info(f"Config: source={self.config.source}, concurrency={self.config.concurrency}, limit={self.config.limit}")
        
        total_stats = BatchStats()
        batch_num = 1
        
        try:
            # For backfill, we first populate ingest_state with all videos
            logger.info("Populating ingest_state with videos...")
            videos = self.list_videos()
            
            if videos:
                # Add all videos to ingest_state (idempotent)
                for video in videos:
                    self.db.upsert_ingest_state(video.video_id, video, status='pending')
                
                logger.info(f"Added {len(videos)} videos to ingest queue")
            else:
                logger.warning("No videos found from source - check your JSON file or API configuration")
            
            # Now process in batches from the queue
            batch_size = self.config.limit or 50  # Default batch size
            
            while True:
                # Get next batch of pending videos
                pending = self.get_pending_videos(batch_size)
                
                if not pending:
                    logger.info("No more videos to process")
                    break
                
                # Convert to VideoInfo objects for processing
                video_batch = []
                for video_data in pending:
                    video_info = VideoInfo(
                        video_id=video_data['video_id'],
                        title=video_data.get('title', ''),
                        published_at=video_data.get('published_at'),
                        duration_s=video_data.get('duration_s'),
                        view_count=video_data.get('view_count'),
                        description=video_data.get('description')
                    )
                    video_batch.append(video_info)
                
                logger.info(f"Processing batch {batch_num} with {len(video_batch)} videos")
                
                # Process batch
                batch_stats = self.process_batch_concurrent(video_batch, batch_num)
                
                # Update total stats
                total_stats.total += batch_stats.total
                total_stats.processed += batch_stats.processed
                total_stats.done += batch_stats.done
                total_stats.errors += batch_stats.errors
                total_stats.skipped += batch_stats.skipped
                
                batch_num += 1
                
                # Optional delay between batches to be nice to services
                if batch_num > 1:
                    time.sleep(2)
                    
        except KeyboardInterrupt:
            logger.info("\nReceived interrupt signal - pipeline is resumable")
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise
        finally:
            # Log final statistics
            end_time = datetime.now()
            duration = end_time - start_time
            
            logger.info("\n" + "="*50)
            logger.info(f"FINAL STATISTICS (completed in {duration})")
            logger.info(f"Total videos processed: {total_stats.total}")
            logger.info(f"Successfully completed: {total_stats.done}")
            logger.info(f"Processed (partial): {total_stats.processed}")
            logger.info(f"Errors: {total_stats.errors}")
            logger.info(f"Skipped: {total_stats.skipped}")
            
            if total_stats.total > 0:
                success_rate = (total_stats.done / total_stats.total) * 100
                logger.info(f"Success rate: {success_rate:.1f}%")
            
            # Close database connection
            self.db.close_connection()

def parse_args() -> IngestConfig:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Robust YouTube transcript ingestion for Ask Dr. Chaffee',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic backfill with yt-dlp
  python ingest_youtube.py --source yt-dlp --limit 50 --newest-first

  # Use YouTube Data API
  python ingest_youtube.py --source api --concurrency 2 --newest-first

  # Process from pre-dumped JSON
  python ingest_youtube.py --from-json backend/data/videos.json --concurrency 4

  # Dry run to see what would be processed
  python ingest_youtube.py --dry-run --limit 10

  # Skip shorts and limit duration
  python ingest_youtube.py --skip-shorts --max-duration 3600
        """
    )
    
    # Source configuration
    parser.add_argument('--source', choices=['yt-dlp', 'api'], default='yt-dlp',
                       help='Data source (default: yt-dlp)')
    parser.add_argument('--from-json', type=Path,
                       help='Load video list from JSON file (yt-dlp only)')
    parser.add_argument('--channel-url',
                       help='YouTube channel URL (default: env YOUTUBE_CHANNEL_URL)')
    
    # Processing configuration
    parser.add_argument('--concurrency', type=int, default=4,
                       help='Concurrent workers (default: 4)')
    parser.add_argument('--limit', type=int,
                       help='Maximum number of videos to process')
    parser.add_argument('--skip-shorts', action='store_true',
                       help='Skip videos shorter than 120 seconds')
    parser.add_argument('--newest-first', action='store_true',
                       help='Process newest videos first')
    parser.add_argument('--max-duration', type=int,
                       help='Skip videos longer than N seconds')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without writing to DB')
    
    # Database configuration
    parser.add_argument('--db-url',
                       help='Database URL (default: env DATABASE_URL)')
    
    # API configuration
    parser.add_argument('--youtube-api-key',
                       help='YouTube Data API key (default: env YOUTUBE_API_KEY)')
    
    # Whisper/ffmpeg configuration
    parser.add_argument('--ffmpeg-path',
                       help='Path to ffmpeg executable for audio processing')
    parser.add_argument('--proxy',
                       help='HTTP/HTTPS proxy to use for YouTube requests (e.g., http://user:pass@host:port)')
    
    # Debug options
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create config
    config = IngestConfig(
        source=args.source,
        from_json=args.from_json,
        channel_url=args.channel_url,
        concurrency=args.concurrency,
        limit=args.limit,
        skip_shorts=args.skip_shorts,
        newest_first=args.newest_first,
        max_duration=args.max_duration,
        dry_run=args.dry_run,
        db_url=args.db_url,
        youtube_api_key=args.youtube_api_key,
        ffmpeg_path=args.ffmpeg_path,
        proxy=args.proxy
    )
    
    return config

def main():
    """Main entry point"""
    try:
        config = parse_args()
        ingester = RobustYouTubeIngester(config)
        ingester.run_backfill()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
