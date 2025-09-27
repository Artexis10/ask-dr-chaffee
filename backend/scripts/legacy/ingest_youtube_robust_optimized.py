#!/usr/bin/env python3
"""
OPTIMIZED YouTube Ingestion - Separate Download and GPU Processing Phases
Phase 1: Download ALL audio files concurrently (30+ threads, I/O bound)
Phase 2: Process ALL with 16 GPU models concurrently (GPU bound)
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
import tempfile

# Third-party imports
import tqdm
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from scripts.common.list_videos_api import YouTubeAPILister
from scripts.common.transcript_fetch import TranscriptFetcher
from scripts.common.database_upsert import DatabaseUpserter, ChunkData
from scripts.common.embeddings import EmbeddingGenerator
from scripts.common.transcript_processor import TranscriptProcessor
from scripts.common.downloader import AudioDownloader
from scripts.common.multi_model_whisper import get_multi_model_manager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_ingestion_optimized.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class IngestConfig:
    """Configuration for the optimized ingestion pipeline"""
    # Data source
    source: str = 'yt-dlp'  # 'yt-dlp' or 'api'
    from_json: Optional[Path] = None
    channel_url: str = None
    
    # Processing limits
    download_concurrency: int = 30  # High concurrency for I/O-bound downloads
    processing_concurrency: int = 16  # Match number of Whisper models
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
class DownloadResult:
    """Result of audio download attempt"""
    video_info: VideoInfo
    audio_file: Optional[Path]
    success: bool
    error: Optional[str] = None

@dataclass 
class ProcessingResult:
    """Result of video processing"""
    video_id: str
    success: bool
    segments_count: int = 0
    method: str = ""
    error: Optional[str] = None

class OptimizedYouTubeIngester:
    """Optimized YouTube ingestion with separated download/processing phases"""
    
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
    
    def download_audio_batch(self, videos: List[VideoInfo], temp_dir: Path) -> List[DownloadResult]:
        """PHASE 1: Download all audio files with high concurrency"""
        logger.info(f"🔄 PHASE 1: Downloading {len(videos)} audio files with {self.config.download_concurrency} concurrent downloads")
        
        def download_single(video_info: VideoInfo) -> DownloadResult:
            """Download audio for single video"""
            try:
                video_id = video_info.video_id
                
                # Check if should skip
                should_skip, reason = self.should_skip_video(video_info)
                if should_skip:
                    logger.debug(f"Skipping download {video_id}: {reason}")
                    return DownloadResult(video_info, None, False, f"Skipped: {reason}")
                
                # Download audio using existing infrastructure
                audio_path = self.transcript_fetcher.download_audio(video_id)
                
                if audio_path and audio_path.exists():
                    # Move to temp directory for batch processing
                    temp_audio_path = temp_dir / f"{video_id}.wav"
                    audio_path.rename(temp_audio_path)
                    
                    logger.info(f"✅ Downloaded: {video_id}")
                    return DownloadResult(video_info, temp_audio_path, True)
                else:
                    logger.warning(f"❌ Download failed: {video_id}")
                    return DownloadResult(video_info, None, False, "Download failed")
                    
            except Exception as e:
                logger.error(f"💥 Download error {video_info.video_id}: {e}")
                return DownloadResult(video_info, None, False, str(e))
        
        # High concurrency download (I/O bound)
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.download_concurrency) as executor:
            future_to_video = {
                executor.submit(download_single, video): video
                for video in videos
            }
            
            for future in tqdm.tqdm(concurrent.futures.as_completed(future_to_video), 
                                  total=len(videos), desc="Downloading Audio"):
                result = future.result()
                results.append(result)
        
        successful = [r for r in results if r.success]
        logger.info(f"🎯 PHASE 1 COMPLETE: {len(successful)}/{len(videos)} audio files downloaded")
        return results
    
    def process_downloaded_batch(self, download_results: List[DownloadResult]) -> List[ProcessingResult]:
        """PHASE 2: Process all downloaded files with GPU models"""
        successful_downloads = [r for r in download_results if r.success]
        
        if not successful_downloads:
            logger.error("No successful downloads to process!")
            return []
        
        logger.info(f"🔥 PHASE 2: Processing {len(successful_downloads)} files with 16 GPU models")
        
        # Initialize multi-model manager
        manager = get_multi_model_manager(num_models=16, model_size="base")
        if not manager.initialize_models():
            logger.error("Failed to initialize GPU models!")
            return []
        
        def process_single_downloaded(download_result: DownloadResult) -> ProcessingResult:
            """Process a single downloaded video through the pipeline"""
            video_info = download_result.video_info
            audio_file = download_result.audio_file
            video_id = video_info.video_id
            
            try:
                logger.info(f"🎯 Processing {video_id}: {video_info.title}")
                
                # Update database status
                self.db.upsert_ingest_state(video_id, video_info, status='pending')
                
                # Transcribe using multi-model approach
                segments, metadata = manager.transcribe_with_multi_model(audio_file)
                
                if not segments:
                    self.db.update_ingest_status(
                        video_id, 'error',
                        error="Failed to transcribe audio",
                        increment_retries=True
                    )
                    return ProcessingResult(video_id, False, 0, "failed", "Transcription failed")
                
                method = "whisper_multi_model"
                
                # Update transcript status
                self.db.update_ingest_status(
                    video_id, 'transcribed',
                    has_yt_transcript=False,
                    has_whisper=True
                )
                
                # Chunk transcript 
                chunks = []
                for i, segment in enumerate(segments):
                    chunk = ChunkData.from_transcript_segment(segment, video_id)
                    chunks.append(chunk)
                
                self.db.update_ingest_status(
                    video_id, 'chunked',
                    chunk_count=len(chunks)
                )
                
                # Generate embeddings
                texts = [chunk.text for chunk in chunks]
                embeddings = self.embedder.generate_embeddings(texts)
                
                # Attach embeddings to chunks
                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding
                
                self.db.update_ingest_status(
                    video_id, 'embedded',
                    embedding_count=len(embeddings)
                )
                
                # Upsert to database
                source_id = self.db.upsert_source(video_info, source_type='youtube')
                
                # Update chunks with correct source_id
                for chunk in chunks:
                    chunk.source_id = source_id
                
                chunk_count = self.db.upsert_chunks(chunks)
                self.db.update_ingest_status(video_id, 'upserted')
                
                # Final status
                self.db.update_ingest_status(video_id, 'done')
                
                logger.info(f"✅ Completed {video_id}: {len(chunks)} chunks, {method}")
                return ProcessingResult(video_id, True, len(chunks), method)
                
            except Exception as e:
                logger.error(f"❌ Processing failed {video_id}: {e}")
                self.db.update_ingest_status(
                    video_id, 'error',
                    error=str(e),
                    increment_retries=True
                )
                return ProcessingResult(video_id, False, 0, "failed", str(e))
            finally:
                # Cleanup audio file
                try:
                    if audio_file and audio_file.exists():
                        audio_file.unlink()
                except Exception as e:
                    logger.debug(f"Failed to cleanup {audio_file}: {e}")
        
        # Process with GPU models (lower concurrency, GPU bound)
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.processing_concurrency) as executor:
            future_to_result = {
                executor.submit(process_single_downloaded, download_result): download_result
                for download_result in successful_downloads
            }
            
            for future in tqdm.tqdm(concurrent.futures.as_completed(future_to_result), 
                                  total=len(successful_downloads), desc="GPU Processing"):
                result = future.result()
                results.append(result)
        
        successful_processing = [r for r in results if r.success]
        logger.info(f"🎯 PHASE 2 COMPLETE: {len(successful_processing)}/{len(successful_downloads)} videos processed")
        return results
    
    def should_skip_video(self, video_info: VideoInfo) -> Tuple[bool, str]:
        """Check if video should be skipped based on current state"""
        state = self.db.get_ingest_state(video_info.video_id)
        
        if state:
            if state.status == 'done':
                return True, "Already completed"
            elif state.status == 'error' and state.retry_count >= 3:
                return True, f"Max retries exceeded ({state.retry_count})"
                
        return False, ""
    
    def run_optimized_pipeline(self) -> Dict[str, int]:
        """Run the optimized two-phase pipeline"""
        logger.info("🚀 STARTING OPTIMIZED TWO-PHASE PIPELINE")
        
        # Get list of videos
        videos = self.list_videos()
        
        if not videos:
            logger.error("No videos found to process")
            return {"total": 0, "downloaded": 0, "processed": 0, "success": 0}
        
        logger.info(f"📊 Found {len(videos)} videos to process")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            start_time = time.time()
            
            # PHASE 1: Download all audio files
            download_results = self.download_audio_batch(videos, temp_path)
            phase1_time = time.time() - start_time
            
            successful_downloads = [r for r in download_results if r.success]
            
            if not successful_downloads:
                logger.error("No successful downloads - aborting processing phase")
                return {"total": len(videos), "downloaded": 0, "processed": 0, "success": 0}
            
            # PHASE 2: Process all downloaded files with GPU
            phase2_start = time.time()
            processing_results = self.process_downloaded_batch(download_results)
            phase2_time = time.time() - phase2_start
            
            successful_processing = [r for r in processing_results if r.success]
            total_time = time.time() - start_time
            
            # Final statistics
            logger.info("") 
            logger.info("🏁 OPTIMIZED PIPELINE COMPLETE!")
            logger.info(f"📊 Phase 1 (Download): {phase1_time:.1f}s - {len(successful_downloads)} files")
            logger.info(f"🔥 Phase 2 (GPU Processing): {phase2_time:.1f}s - {len(successful_processing)} videos")
            logger.info(f"⏱️ Total time: {total_time:.1f}s")
            logger.info(f"✅ Success rate: {len(successful_processing)}/{len(videos)} = {len(successful_processing)/len(videos)*100:.1f}%")
            
            return {
                "total": len(videos),
                "downloaded": len(successful_downloads),
                "processed": len(processing_results), 
                "success": len(successful_processing)
            }
    
    def list_videos(self) -> List[VideoInfo]:
        """List videos using configured source"""
        logger.info(f"Listing videos using {self.config.source} source")
        
        if self.config.from_json:
            # Load from JSON file (yt-dlp only)
            if self.config.source != 'yt-dlp':
                raise ValueError("--from-json only supported with yt-dlp source")
            videos = self.video_lister.list_from_json(self.config.from_json)
        else:
            # Fetch from channel
            if hasattr(self.video_lister, 'list_channel_videos'):
                videos = self.video_lister.list_channel_videos(self.config.channel_url)
            else:
                # API lister method
                videos = self.video_lister.list_videos(
                    self.config.channel_url, 
                    limit=self.config.limit
                )
        
        # Apply filters
        if self.config.skip_shorts:
            videos = [v for v in videos if not v.duration_s or v.duration_s >= 120]
            logger.info(f"Filtered out shorts, {len(videos)} videos remaining")
        
        if self.config.max_duration:
            videos = [v for v in videos if not v.duration_s or v.duration_s <= self.config.max_duration]
            logger.info(f"Filtered by max duration, {len(videos)} videos remaining")
        
        if self.config.newest_first:
            videos = sorted(videos, key=lambda v: v.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        
        return videos

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Optimized YouTube Ingestion Pipeline")
    parser.add_argument('--source', choices=['yt-dlp', 'api'], default='yt-dlp',
                       help='Video source (default: yt-dlp)')
    parser.add_argument('--from-json', type=Path,
                       help='Load videos from yt-dlp JSON file')
    parser.add_argument('--channel-url',
                       help='YouTube channel URL to process')
    parser.add_argument('--download-concurrency', type=int, default=30,
                       help='Download concurrent workers (default: 30)')
    parser.add_argument('--processing-concurrency', type=int, default=16,
                       help='Processing concurrent workers (default: 16)') 
    parser.add_argument('--limit', type=int,
                       help='Maximum number of videos to process')
    parser.add_argument('--skip-shorts', action='store_true',
                       help='Skip videos shorter than 120 seconds')
    parser.add_argument('--newest-first', action='store_true',
                       help='Process newest videos first')
    parser.add_argument('--max-duration', type=int,
                       help='Maximum video duration in seconds')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without doing it')
    
    args = parser.parse_args()
    
    config = IngestConfig(
        source=args.source,
        from_json=args.from_json,
        channel_url=args.channel_url,
        download_concurrency=args.download_concurrency,
        processing_concurrency=args.processing_concurrency,
        limit=args.limit,
        skip_shorts=args.skip_shorts,
        newest_first=args.newest_first,
        max_duration=args.max_duration,
        dry_run=args.dry_run
    )
    
    ingester = OptimizedYouTubeIngester(config)
    results = ingester.run_optimized_pipeline()
    
    logger.info(f"Final results: {results}")

if __name__ == "__main__":
    main()
