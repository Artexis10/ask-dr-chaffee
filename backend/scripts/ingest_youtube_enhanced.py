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
import time
import json
import codecs
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

import tqdm
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Set UTF-8 encoding for stdout on Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

# Add paths for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(__file__), 'common'))

# Import all required modules
from scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from scripts.common.list_videos_api import YouTubeAPILister  
from scripts.common.local_file_lister import LocalFileLister
from scripts.common.proxy_manager import ProxyConfig, ProxyManager
from scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher  
from scripts.common.database_upsert import DatabaseUpserter
from scripts.common.segments_database import SegmentsDatabase
from scripts.common.embeddings import EmbeddingGenerator
# ChunkData not needed - using segments directly

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
    source: str = 'api'  # 'api', 'yt-dlp', or 'local' (API is now default)
    channel_url: Optional[str] = None
    from_json: Optional[Path] = None
    from_files: Optional[Path] = None  # Directory containing local video/audio files
    file_patterns: List[str] = None  # File patterns to match (e.g., ['*.mp4', '*.wav'])
    concurrency: int = 4
    skip_shorts: bool = False
    newest_first: bool = True
    limit: Optional[int] = None
    dry_run: bool = False
    whisper_model: str = 'small.en'
    max_duration: Optional[int] = None
    force_whisper: bool = False
    cleanup_audio: bool = True
    since_published: Optional[str] = None  # ISO8601 or YYYY-MM-DD format
    
    # Audio storage configuration
    store_audio_locally: bool = True   # Store downloaded audio files locally
    audio_storage_dir: Optional[Path] = None  # Directory to store audio files
    production_mode: bool = False      # Disable audio storage in production
    
    # Content filtering
    skip_live: bool = True
    skip_upcoming: bool = True
    skip_members_only: bool = True
    
    # Database
    db_url: str = None
    
    # API keys
    youtube_api_key: Optional[str] = None
    ffmpeg_path: Optional[str] = None
    
    # Proxy configuration
    proxy: Optional[str] = None
    proxy_file: Optional[str] = None
    proxy_rotate: bool = False
    proxy_rotate_interval: int = 10
    
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
        
        # Handle local file processing
        if self.source == 'local':
            if not self.from_files:
                raise ValueError("--from-files directory required for local source")
            if not self.from_files.exists():
                raise ValueError(f"Local files directory does not exist: {self.from_files}")
        
        # Set up file patterns if not provided
        if self.file_patterns is None:
            self.file_patterns = ['*.mp4', '*.mkv', '*.avi', '*.mov', '*.wav', '*.mp3', '*.m4a', '*.webm']
        
        # Handle audio storage configuration
        if self.production_mode:
            self.store_audio_locally = False
            logger.info("Production mode enabled: Audio storage disabled")
        
        if self.store_audio_locally and self.audio_storage_dir is None:
            self.audio_storage_dir = Path(os.getenv('AUDIO_STORAGE_DIR', './audio_storage'))
            self.audio_storage_dir.mkdir(exist_ok=True)
            logger.info(f"Audio will be stored in: {self.audio_storage_dir}")

@dataclass 
class ProcessingStats:
    """Track processing statistics"""
    total: int = 0
    processed: int = 0
    skipped: int = 0
    errors: int = 0
    youtube_transcripts: int = 0
    whisper_transcripts: int = 0
    segments_created: int = 0
    
    def log_summary(self):
        """Log final statistics"""
        logger.info("=== INGESTION SUMMARY ===")
        logger.info(f"Total videos: {self.total}")
        logger.info(f"Processed: {self.processed}")
        logger.info(f"Skipped: {self.skipped}")
        logger.info(f"Errors: {self.errors}")
        logger.info(f"YouTube transcripts: {self.youtube_transcripts}")
        logger.info(f"Whisper transcripts: {self.whisper_transcripts}")
        logger.info(f"Total segments created: {self.segments_created}")
        
        if self.total > 0:
            success_rate = (self.processed / self.total) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")

class EnhancedYouTubeIngester:
    """Enhanced YouTube ingestion pipeline with dual data sources"""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
        self.stats = ProcessingStats()
        
        # Initialize components
        self.db = DatabaseUpserter(config.db_url)  # Keep for ingest_state tracking
        self.segments_db = SegmentsDatabase(config.db_url)  # Use for segments storage
        
        # Setup proxy manager
        proxy_config = ProxyConfig(
            enabled=(config.proxy is not None or config.proxy_file is not None),
            rotation_enabled=config.proxy_rotate,
            rotation_interval=config.proxy_rotate_interval,
            proxy_list=[config.proxy] if config.proxy else None,
            proxy_file=config.proxy_file
        )
        self.proxy_manager = ProxyManager(proxy_config)
        
        # Get initial proxy
        proxies = self.proxy_manager.get_proxy()
        
        # Use Enhanced Transcript Fetcher for better functionality
        self.transcript_fetcher = EnhancedTranscriptFetcher(
            whisper_model=config.whisper_model,
            ffmpeg_path=config.ffmpeg_path,
            proxies=proxies,
            api_key=config.youtube_api_key,
            credentials_path=os.getenv('YOUTUBE_CREDENTIALS_PATH'),
            # Audio storage options
            store_audio_locally=config.store_audio_locally,
            audio_storage_dir=str(config.audio_storage_dir) if config.audio_storage_dir else None,
            production_mode=config.production_mode
        )
        self.embedder = EmbeddingGenerator()
        
        # Initialize video/file lister based on source
        if config.source == 'api':
            if not config.youtube_api_key:
                raise ValueError("YouTube API key required for API source")
            self.video_lister = YouTubeAPILister(config.youtube_api_key, config.db_url)
        elif config.source == 'yt-dlp':
            self.video_lister = YtDlpVideoLister()
        elif config.source == 'local':
            self.video_lister = LocalFileLister()
        else:
            raise ValueError(f"Unknown source: {config.source}")
    
    def list_videos(self) -> List[VideoInfo]:
        """List videos using configured source"""
        logger.info(f"Listing videos using {self.config.source} source")
        
        if self.config.source == 'local':
            # Handle local file source
            return self._list_local_files()
        elif self.config.from_json:
            # Load from JSON file (yt-dlp only)
            if self.config.source != 'yt-dlp':
                raise ValueError("--from-json only supported with yt-dlp source")
            videos = self.video_lister.list_from_json(self.config.from_json)
        else:
            # Parse since_published if provided
            since_published = None
            if self.config.since_published:
                try:
                    # Try ISO8601 format first
                    if 'T' in self.config.since_published or '+' in self.config.since_published:
                        since_published = datetime.fromisoformat(self.config.since_published.replace('Z', '+00:00'))
                    else:
                        # Try YYYY-MM-DD format
                        since_published = datetime.strptime(self.config.since_published, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                except ValueError as e:
                    logger.error(f"Invalid since_published format: {self.config.since_published}. Use ISO8601 or YYYY-MM-DD")
                    raise
            
            # List videos from channel
            logger.info(f"Listing videos from channel using {self.config.source}")
            if self.config.source == 'api' and hasattr(self.video_lister, 'list_channel_videos'):
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
                # yt-dlp lister supports members-only filtering
                videos = self.video_lister.list_channel_videos(
                    self.config.channel_url,
                    use_cache=True,
                    skip_members_only=self.config.skip_members_only
                )
        
        # Apply filters (only for non-local sources)
        if self.config.source != 'local':
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
    
    def _list_local_files(self) -> List[VideoInfo]:
        """List local video/audio files for processing"""
        logger.info(f"Scanning local files from: {self.config.from_files}")
        
        file_infos = self.video_lister.list_files_from_directory(
            self.config.from_files,
            patterns=self.config.file_patterns,
            recursive=True,  # Always scan subdirectories for local files
            max_results=self.config.limit,
            newest_first=self.config.newest_first
        )
        
        # Convert LocalFileInfo objects to VideoInfo objects
        videos = []
        for file_info in file_infos:
            # Get duration if possible
            try:
                duration = self.video_lister.get_file_duration(file_info.file_path)
                file_info.duration_s = duration
            except Exception as e:
                logger.debug(f"Could not get duration for {file_info.file_path}: {e}")
            
            # Apply duration filter for local files too
            if self.config.skip_shorts and file_info.duration_s and file_info.duration_s < 120:
                logger.debug(f"Skipping short file: {file_info.file_path} ({file_info.duration_s}s)")
                continue
            
            video_info = file_info.to_video_info()
            videos.append(video_info)
        
        logger.info(f"Found {len(videos)} local files to process")
        return videos
    
    def should_skip_video(self, video: VideoInfo) -> Tuple[bool, str]:
        """Check if video should be skipped"""
        # Check existing processing state from merged sources table
        source_id, segment_count = self.segments_db.check_video_exists(video.video_id)
        if source_id and segment_count > 0:
            return True, f"already processed ({segment_count} segments)"
        
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
            # Check if video already exists in segments database
            source_id, segment_count = self.segments_db.check_video_exists(video_id)
            if source_id and segment_count > 0:
                logger.info(f"⚡ Skipping {video_id}: already processed ({segment_count} segments)")
                self.stats.skipped += 1
                return False
            
            # Check if should skip
            should_skip, reason = self.should_skip_video(video)
            if should_skip:
                logger.debug(f"Skipping {video_id}: {reason}")
                self.stats.skipped += 1
                return True
            
            logger.info(f"Processing video {video_id}: {video.title}")
            
            # Step 1: Fetch transcript with enhanced metadata
            # Determine if this is a local file based on the source configuration
            is_local_file = self.config.source == 'local'
            
            if hasattr(self.transcript_fetcher, 'fetch_transcript_with_speaker_id'):
                # Use enhanced transcript fetcher with speaker ID support
                segments, method, metadata = self.transcript_fetcher.fetch_transcript_with_speaker_id(
                    video_id,
                    max_duration_s=self.config.max_duration,
                    force_enhanced_asr=self.config.force_whisper,
                    cleanup_audio=self.config.cleanup_audio,
                    enable_silence_removal=False,  # Conservative default
                    is_local_file=is_local_file
                )
            else:
                # Fallback to standard transcript fetcher
                segments, method, metadata = self.transcript_fetcher.fetch_transcript(
                    video_id,
                    max_duration_s=self.config.max_duration,
                    force_whisper=self.config.force_whisper,
                    cleanup_audio=self.config.cleanup_audio,
                    enable_silence_removal=False  # Conservative default
                )
            
            if not segments:
                error_msg = metadata.get('error', 'Failed to fetch transcript')
                logger.error(f"Failed to get transcript for {video_id}: {error_msg}")
                self.stats.errors += 1
                return False
            
            # Log transcript method for statistics
            logger.debug(f"Transcript method for {video_id}: {method}")
            
            # Track transcription method statistics
            if method == 'youtube':
                self.stats.youtube_transcripts += 1
            elif method in ('whisper', 'whisper_upgraded'):
                self.stats.whisper_transcripts += 1
                if method == 'whisper_upgraded':
                    logger.info(f"Used upgraded Whisper model for {video_id}")
            
            # Log quality information if available
            if 'quality_assessment' in metadata:
                quality_info = metadata['quality_assessment']
                logger.info(f"Transcript quality for {video_id}: score={quality_info['score']}, issues={quality_info.get('issues', [])}")
            
            # Extract provenance and extra metadata for database storage
            # Map transcript methods to database provenance values
            provenance_mapping = {
                'youtube': 'yt_caption',
                'whisper': 'whisper',
                'whisper_upgraded': 'whisper',
                'enhanced_asr': 'whisper',  # Enhanced ASR is still Whisper-based
                'yt_dlp': 'yt_dlp'
            }
            provenance = provenance_mapping.get(method, 'whisper')  # Default to whisper
            extra_metadata = {
                'transcript_method': method,
                'segment_count': len(segments)
            }
            
            # Add preprocessing and quality info if available
            if 'preprocessing_flags' in metadata:
                extra_metadata['preprocessing'] = metadata['preprocessing_flags']
            
            if 'quality_assessment' in metadata:
                extra_metadata['quality'] = metadata['quality_assessment']
            
            if 'model' in metadata:
                extra_metadata['whisper_model'] = metadata['model']
            
            if 'upgrade_used' in metadata:
                extra_metadata['upgrade_used'] = metadata['upgrade_used']
            
            # Step 2: Process segments with embeddings
            logger.debug(f"Processing {len(segments)} segments for {video_id}")
            
            # Step 3: Generate embeddings
            texts = [segment.get('text', '') for segment in segments]
            embeddings = self.embedder.generate_embeddings(texts)
            
            # Attach embeddings to segments
            for segment, embedding in zip(segments, embeddings):
                segment['embedding'] = embedding
            
            logger.debug(f"Generated {len(embeddings)} embeddings for {video_id}")
            
            # Step 4: Upsert source and segments to database with proper speaker attribution
            # Determine source type based on actual source
            if self.config.source == 'local':
                source_type = 'local_file'
            elif self.config.source == 'api':
                source_type = 'youtube_api'
            else:
                source_type = 'youtube'  # Default for yt-dlp
            
            source_id = self.segments_db.upsert_source(
                video_id, 
                video.title,
                source_type=source_type,
                metadata={'provenance': provenance, **extra_metadata}
            )
            
            # Insert segments with speaker attribution
            segment_count = self.segments_db.batch_insert_segments(
                segments, 
                video_id,
                chaffee_only_storage=False,  # Store all speakers
                embed_chaffee_only=True      # But only embed Chaffee content for search
            )
            
            self.stats.processed += 1
            self.stats.segments_created += segment_count
            
            # Log completion with additional info
            extra_info = ""
            if self.config.source == 'local':
                extra_info = f" (local file: {video_id})"
            elif metadata.get('stored_audio_path'):
                extra_info = f" (audio stored: {Path(metadata['stored_audio_path']).name})"
            
            logger.info(f"✅ Completed {video_id}: {len(segments)} segments, {method} transcript{extra_info}")
            return True
            
        except Exception as e:
            error_msg = str(e)[:500]  # Truncate long errors
            logger.error(f"❌ Error processing {video_id}: {error_msg}")
            
            # Log error for debugging
            logger.debug(f"Error details for {video_id}: {e}")
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
    
    async def check_video_accessibility(self, video: VideoInfo) -> bool:
        """Check if a video is accessible (not members-only) using yt-dlp"""
        try:
            cmd = [
                "yt-dlp",
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
                return True
            else:
                error_msg = stderr.decode().lower()
                if "members-only" in error_msg or "join this channel" in error_msg:
                    logger.info(f"🔒 Skipping members-only: {video.video_id} - {video.title[:50]}...")
                    return False
                else:
                    logger.warning(f"⚠️ Video inaccessible: {video.video_id}")
                    return False
                
        except Exception as e:
            logger.error(f"❌ Accessibility check failed for {video.video_id}: {e}")
            return False
    
    async def phase1_prefilter_videos(self, videos: List[VideoInfo]) -> List[VideoInfo]:
        """Phase 1: Smart pre-filtering for accessibility (3-phase optimization)"""
        if self.config.source == 'local' or len(videos) <= 10:
            logger.info("⚡ Skipping Phase 1 pre-filtering (local files or small batch)")
            return videos
            
        logger.info(f"🎯 PHASE 1: Pre-filtering {len(videos)} videos for accessibility")
        start_time = time.time()
        
        # Create semaphore for controlled concurrent checks - increased for RTX 5080
        max_concurrent_checks = min(16, len(videos))  # Doubled from 8 to 16
        semaphore = asyncio.Semaphore(max_concurrent_checks)
        
        async def check_with_semaphore(video):
            async with semaphore:
                is_accessible = await self.check_video_accessibility(video)
                return video, is_accessible
        
        # Check all videos concurrently
        logger.info(f"🔍 Checking accessibility ({max_concurrent_checks} concurrent)")
        tasks = [check_with_semaphore(video) for video in videos]
        results = await asyncio.gather(*tasks)
        
        # Filter results
        accessible_videos = []
        members_only_count = 0
        
        for video, is_accessible in results:
            if is_accessible:
                accessible_videos.append(video)
            else:
                members_only_count += 1
        
        duration = time.time() - start_time
        logger.info(f"✅ Phase 1 Complete ({duration:.1f}s):")
        logger.info(f"   📈 Accessible: {len(accessible_videos)}")
        logger.info(f"   🔒 Members-only filtered: {members_only_count}")
        logger.info(f"   📊 Success rate: {(len(accessible_videos)/len(videos)*100):.1f}%")
        logger.info(f"   💡 Saved {members_only_count * 30:.0f}s of wasted processing time")
        
        return accessible_videos

    def run(self) -> None:
        """Run the complete ingestion pipeline with smart 3-phase optimization"""
        start_time = datetime.now()
        logger.info("🚀 Starting enhanced YouTube ingestion pipeline")
        logger.info(f"Config: source={self.config.source}, concurrency={self.config.concurrency}")
        
        try:
            # List videos
            videos = self.list_videos()
            
            if not videos:
                logger.warning("No videos found to process")
                return
            
            # Smart 3-Phase Pipeline for medium/large batches - lowered threshold for better optimization
            if len(videos) > 15 and self.config.source in ['api', 'yt-dlp']:
                logger.info("📊 Using SMART 3-PHASE pipeline for large batch optimization")
                logger.info("   🎯 Phase 1: Pre-filter accessibility")
                logger.info("   📥 Phase 2: Bulk download accessible videos")  
                logger.info("   🎙️ Phase 3: Enhanced ASR processing")
                
                # Phase 1: Pre-filter videos (async)
                import asyncio
                accessible_videos = asyncio.run(self.phase1_prefilter_videos(videos))
                
                if not accessible_videos:
                    logger.warning("No accessible videos found after Phase 1 filtering")
                    return
                
                # Phase 2 & 3: Process accessible videos normally
                logger.info(f"📥 PHASE 2 & 3: Processing {len(accessible_videos)} accessible videos")
                videos = accessible_videos
            
            # Process videos (Phase 2 & 3 combined)
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

  # Process local video/audio files
  python ingest_youtube_enhanced.py --source local --from-files ./video_collection --concurrency 4

  # Process specific file types with audio storage disabled
  python ingest_youtube_enhanced.py --source local --from-files ./podcasts --file-patterns *.mp3 *.wav --no-store-audio

  # Production mode (no audio storage)
  python ingest_youtube_enhanced.py --source api --production-mode --limit 100

  # Dry run to see what would be processed
  python ingest_youtube_enhanced.py --dry-run --limit 10

  # Force Whisper transcription with larger model
  python ingest_youtube_enhanced.py --source yt-dlp --whisper-model medium.en --force-whisper
        """
    )
    
    # Source configuration
    parser.add_argument('--source', choices=['api', 'yt-dlp', 'local'], default='api',
                       help='Data source: api for YouTube Data API (default), yt-dlp for scraping fallback, local for files')
    parser.add_argument('--from-json', type=Path,
                       help='Process videos from JSON file instead of fetching (yt-dlp only)')
    parser.add_argument('--from-files', type=Path,
                       help='Process local video/audio files from directory (local source only)')
    parser.add_argument('--file-patterns', nargs='+', 
                       help='File patterns to match (e.g. *.mp4 *.wav), default: all supported formats')
    parser.add_argument('--channel-url',
                       help='YouTube channel URL (default: env YOUTUBE_CHANNEL_URL)')
    parser.add_argument('--since-published',
                       help='Only process videos published after this date (ISO8601 or YYYY-MM-DD)')
    
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
    
    # Audio storage configuration
    parser.add_argument('--store-audio-locally', action='store_true', default=True,
                       help='Store downloaded audio files locally (default: true)')
    parser.add_argument('--no-store-audio', dest='store_audio_locally', action='store_false',
                       help='Disable local audio storage')
    parser.add_argument('--audio-storage-dir', type=Path,
                       help='Directory to store audio files (default: ./audio_storage)')
    parser.add_argument('--production-mode', action='store_true',
                       help='Production mode: disables audio storage regardless of other flags')
    
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
        from_files=args.from_files,
        file_patterns=args.file_patterns,
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
        # Audio storage options
        store_audio_locally=args.store_audio_locally,
        audio_storage_dir=args.audio_storage_dir,
        production_mode=args.production_mode,
        # Content filtering options
        skip_live=args.skip_live,
        skip_upcoming=args.skip_upcoming,
        skip_members_only=args.skip_members_only
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
