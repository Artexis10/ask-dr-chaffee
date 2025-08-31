#!/usr/bin/env python3
"""
Enhanced YouTube transcript ingestion script for Ask Dr. Chaffee.

Supports dual data sources (yt-dlp and YouTube Data API) with robust 
concurrent processing pipeline and comprehensive error handling.
"""

import os
import sys
import argparse
import logging
import asyncio
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import json

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

# Configure logging with Unicode support for Windows
import sys
import codecs

# Set UTF-8 encoding for stdout on Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_ingestion_enhanced.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class IngestionConfig:
    """Configuration for ingestion pipeline"""
    source: str = 'yt-dlp'  # 'yt-dlp' or 'api'
    channel_url: str = None
    from_json: Optional[Path] = None
    concurrency: int = 4
    skip_shorts: bool = False
    newest_first: bool = True
    limit: Optional[int] = None
    dry_run: bool = False
    whisper_model: str = 'small.en'
    max_duration: Optional[int] = None
    force_whisper: bool = False
    cleanup_audio: bool = True
    
    # Database
    db_url: str = None
    
    # API keys
    youtube_api_key: Optional[str] = None
    
    def __post_init__(self):
        """Set defaults from environment"""
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
class ProcessingStats:
    """Track processing statistics"""
    total: int = 0
    processed: int = 0
    skipped: int = 0
    errors: int = 0
    youtube_transcripts: int = 0
    whisper_transcripts: int = 0
    chunks_created: int = 0
    
    def log_summary(self):
        """Log final statistics"""
        logger.info("=== INGESTION SUMMARY ===")
        logger.info(f"Total videos: {self.total}")
        logger.info(f"Processed: {self.processed}")
        logger.info(f"Skipped: {self.skipped}")
        logger.info(f"Errors: {self.errors}")
        logger.info(f"YouTube transcripts: {self.youtube_transcripts}")
        logger.info(f"Whisper transcripts: {self.whisper_transcripts}")
        logger.info(f"Total chunks created: {self.chunks_created}")
        
        if self.total > 0:
            success_rate = (self.processed / self.total) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")

class EnhancedYouTubeIngester:
    """Enhanced YouTube ingestion pipeline with dual data sources"""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
        self.stats = ProcessingStats()
        
        # Initialize components
        self.db = DatabaseUpserter(config.db_url)
        self.transcript_fetcher = TranscriptFetcher(
            whisper_model=config.whisper_model
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
        
        # Apply sorting
        if self.config.newest_first:
            videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)
        
        # Apply limit
        if self.config.limit:
            videos = videos[:self.config.limit]
        
        logger.info(f"Found {len(videos)} videos to process")
        return videos
    
    def should_skip_video(self, video: VideoInfo) -> Tuple[bool, str]:
        """Check if video should be skipped"""
        # Check existing ingest state
        state = self.db.get_ingest_state(video.video_id)
        if state:
            if state['status'] in ('done', 'upserted'):
                return True, f"already processed (status: {state['status']})"
            elif state['status'] == 'error' and state['retries'] >= 3:
                return True, f"max retries exceeded ({state['retries']})"
        
        # Check duration limit for Whisper fallback
        if (self.config.max_duration and 
            video.duration_s and 
            video.duration_s > self.config.max_duration):
            return True, f"duration {video.duration_s}s exceeds limit {self.config.max_duration}s"
        
        return False, ""
    
    def process_single_video(self, video: VideoInfo) -> bool:
        """Process a single video through the full pipeline"""
        video_id = video.video_id
        
        try:
            # Check if should skip
            should_skip, reason = self.should_skip_video(video)
            if should_skip:
                logger.debug(f"Skipping {video_id}: {reason}")
                self.stats.skipped += 1
                return True
            
            logger.info(f"Processing video {video_id}: {video.title}")
            
            # Initialize/update ingest state
            self.db.upsert_ingest_state(video_id, video, status='pending')
            
            # Step 1: Fetch transcript
            segments, method = self.transcript_fetcher.fetch_transcript(
                video_id,
                max_duration_s=self.config.max_duration,
                force_whisper=self.config.force_whisper,
                cleanup_audio=self.config.cleanup_audio
            )
            
            if not segments:
                self.db.update_ingest_status(
                    video_id, 'error', 
                    error="Failed to fetch transcript",
                    increment_retries=True
                )
                self.stats.errors += 1
                return False
            
            # Update transcript status
            transcript_status = {
                'has_yt_transcript': method == 'youtube',
                'has_whisper': method == 'whisper',
                'status': 'has_yt_transcript' if method == 'youtube' else 'transcribed'
            }
            self.db.update_ingest_status(video_id, **transcript_status)
            
            if method == 'youtube':
                self.stats.youtube_transcripts += 1
            else:
                self.stats.whisper_transcripts += 1
            
            # Step 2: Chunk transcript
            chunks = []
            for segment in segments:
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
            # Always use 'youtube' as the source_type regardless of the data source method
            source_type = 'youtube'
            
            source_id = self.db.upsert_source(video, source_type=source_type)
            
            # Update chunks with correct source_id
            for chunk in chunks:
                chunk.source_id = source_id
            
            chunk_count = self.db.upsert_chunks(chunks)
            
            self.db.update_ingest_status(video_id, 'done')
            
            self.stats.processed += 1
            self.stats.chunks_created += chunk_count
            
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
            
            self.stats.errors += 1
            return False
    
    def run_sequential(self, videos: List[VideoInfo]) -> None:
        """Run processing sequentially with progress bar"""
        self.stats.total = len(videos)
        
        with tqdm.tqdm(total=len(videos), desc="Processing videos") as pbar:
            for video in videos:
                if self.config.dry_run:
                    logger.info(f"DRY RUN: Would process {video.video_id}: {video.title}")
                    continue
                
                self.process_single_video(video)
                pbar.update(1)
                
                # Update progress bar description
                pbar.set_postfix({
                    'processed': self.stats.processed,
                    'errors': self.stats.errors,
                    'skipped': self.stats.skipped
                })
    
    def run_concurrent(self, videos: List[VideoInfo]) -> None:
        """Run processing with concurrent workers"""
        self.stats.total = len(videos)
        
        if self.config.dry_run:
            for video in videos:
                logger.info(f"DRY RUN: Would process {video.video_id}: {video.title}")
            return
        
        # Use ThreadPoolExecutor for I/O bound tasks
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            with tqdm.tqdm(total=len(videos), desc="Processing videos") as pbar:
                # Submit all tasks
                future_to_video = {
                    executor.submit(self.process_single_video, video): video 
                    for video in videos
                }
                
                # Process completed tasks
                for future in concurrent.futures.as_completed(future_to_video):
                    video = future_to_video[future]
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"Unexpected error for {video.video_id}: {e}")
                        self.stats.errors += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({
                        'processed': self.stats.processed,
                        'errors': self.stats.errors,
                        'skipped': self.stats.skipped
                    })
    
    def run(self) -> None:
        """Run the complete ingestion pipeline"""
        start_time = datetime.now()
        logger.info("🚀 Starting enhanced YouTube ingestion pipeline")
        logger.info(f"Config: source={self.config.source}, concurrency={self.config.concurrency}")
        
        try:
            # List videos
            videos = self.list_videos()
            
            if not videos:
                logger.warning("No videos found to process")
                return
            
            # Process videos
            if self.config.concurrency > 1:
                self.run_concurrent(videos)
            else:
                self.run_sequential(videos)
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise
        finally:
            # Log final statistics
            end_time = datetime.now()
            duration = end_time - start_time
            logger.info(f"Pipeline completed in {duration}")
            self.stats.log_summary()
            
            # Close database connection
            self.db.close_connection()

def parse_args() -> IngestionConfig:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Enhanced YouTube transcript ingestion for Ask Dr. Chaffee',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic yt-dlp ingestion
  python ingest_youtube_enhanced.py --source yt-dlp --limit 20

  # Use YouTube Data API
  python ingest_youtube_enhanced.py --source api --limit 50 --newest-first

  # Process from pre-dumped JSON
  python ingest_youtube_enhanced.py --from-json backend/data/videos.json --concurrency 8

  # Dry run to see what would be processed
  python ingest_youtube_enhanced.py --dry-run --limit 10

  # Force Whisper transcription with larger model
  python ingest_youtube_enhanced.py --source yt-dlp --whisper-model medium.en --force-whisper
        """
    )
    
    # Source configuration
    parser.add_argument('--source', choices=['yt-dlp', 'api'], default='yt-dlp',
                       help='Data source (default: yt-dlp)')
    parser.add_argument('--channel-url', 
                       help='YouTube channel URL (default: env YOUTUBE_CHANNEL_URL)')
    parser.add_argument('--from-json', type=Path,
                       help='Load video list from JSON file (yt-dlp only)')
    
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
    
    # Whisper configuration
    parser.add_argument('--whisper-model', default='small.en',
                       choices=['tiny.en', 'base.en', 'small.en', 'medium.en', 'large-v3'],
                       help='Whisper model size (default: small.en)')
    parser.add_argument('--max-duration', type=int,
                       help='Skip videos longer than N seconds for Whisper fallback')
    parser.add_argument('--force-whisper', action='store_true',
                       help='Use Whisper even when YouTube transcript available')
    
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
        youtube_api_key=args.youtube_api_key
    )
    
    return config

def main():
    """Main entry point"""
    try:
        config = parse_args()
        ingester = EnhancedYouTubeIngester(config)
        ingester.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
