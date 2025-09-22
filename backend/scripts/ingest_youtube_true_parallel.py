#!/usr/bin/env python3
"""
TRUE PARALLEL YouTube Ingestion - All 16 Models Working Simultaneously
Each model gets its own dedicated worker process for maximum RTX 5080 utilization
"""

import os
import sys
import argparse
import logging
import json
import multiprocessing
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

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_ingestion_true_parallel.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class IngestConfig:
    """Configuration for true parallel ingestion"""
    # Data source
    source: str = 'yt-dlp'
    from_json: Optional[Path] = None
    channel_url: str = None
    
    # Processing limits
    num_workers: int = 16  # One per Whisper model
    limit: Optional[int] = None
    skip_shorts: bool = False
    max_duration: Optional[int] = None
    newest_first: bool = False
    
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

def initialize_worker_whisper_model(worker_id: int, model_size: str = "base"):
    """Initialize a dedicated Whisper model for this worker process"""
    try:
        import faster_whisper
        
        logger.info(f"🔥 Worker {worker_id}: Loading dedicated Whisper model ({model_size})")
        
        model = faster_whisper.WhisperModel(
            model_size,
            device="cuda",
            compute_type="float16"
        )
        
        logger.info(f"✅ Worker {worker_id}: Whisper model loaded successfully")
        return model
        
    except Exception as e:
        logger.error(f"❌ Worker {worker_id}: Failed to load Whisper model: {e}")
        return None

def process_video_worker(args):
    """Worker function that processes a single video with its dedicated Whisper model"""
    worker_id, video_info, config = args
    
    # Set up worker-specific logging
    worker_logger = logging.getLogger(f"worker_{worker_id}")
    
    try:
        # Initialize dedicated Whisper model for this worker
        whisper_model = initialize_worker_whisper_model(worker_id)
        if not whisper_model:
            return {"worker_id": worker_id, "video_id": video_info.video_id, "success": False, "error": "Failed to load Whisper model"}
        
        # Initialize components for this worker
        db = DatabaseUpserter(config.db_url)
        
        # Setup proxies if provided
        proxies = None
        if config.proxy:
            proxies = {
                'http': config.proxy,
                'https': config.proxy
            }
        
        transcript_fetcher = TranscriptFetcher(
            ffmpeg_path=config.ffmpeg_path,
            proxies=proxies
        )
        embedder = EmbeddingGenerator()
        
        video_id = video_info.video_id
        
        worker_logger.info(f"🎯 Worker {worker_id}: Processing {video_id} - {video_info.title}")
        
        start_time = time.time()
        
        # Check if should skip
        try:
            state = db.get_ingest_state(video_id)
            if state and hasattr(state, 'status'):
                if state.status == 'done':
                    worker_logger.info(f"⏭️ Worker {worker_id}: Skipping {video_id} - already completed")
                    return {"worker_id": worker_id, "video_id": video_id, "success": True, "skipped": True}
                elif state.status == 'error' and hasattr(state, 'retry_count') and state.retry_count >= 3:
                    worker_logger.info(f"⏭️ Worker {worker_id}: Skipping {video_id} - max retries exceeded")
                    return {"worker_id": worker_id, "video_id": video_id, "success": True, "skipped": True}
        except Exception as e:
            # If state check fails, continue with processing
            worker_logger.debug(f"State check failed for {video_id}, continuing: {e}")
        
        # Step 0: Initialize/update ingest state
        db.upsert_ingest_state(video_id, video_info, status='pending')
        
        # Step 1: Download audio
        worker_logger.info(f"📥 Worker {worker_id}: Downloading audio for {video_id}")
        
        # Get audio using existing infrastructure but bypass the transcript fetcher's Whisper
        audio_path = None
        try:
            # Try to get YouTube transcript first (fast)
            segments, method, metadata = transcript_fetcher.fetch_transcript(
                video_id,
                max_duration_s=config.max_duration
            )
            
            # If we got a transcript from YouTube, use it
            if segments and method == 'youtube':
                worker_logger.info(f"✅ Worker {worker_id}: Using YouTube transcript for {video_id}")
            else:
                # Need to transcribe with Whisper - download audio
                worker_logger.info(f"🔄 Worker {worker_id}: No YouTube transcript, downloading audio for {video_id}")
                
                # Download audio directly
                import tempfile
                from scripts.common.downloader import AudioDownloader
                
                downloader = AudioDownloader(
                    ffmpeg_path=config.ffmpeg_path,
                    proxies=proxies
                )
                
                audio_path = downloader.download_audio(video_id)
                
                if not audio_path or not audio_path.exists():
                    raise Exception("Failed to download audio")
                
                # Transcribe with dedicated Whisper model
                worker_logger.info(f"🎯 Worker {worker_id}: Transcribing with dedicated Whisper model")
                
                segments_iter, info = whisper_model.transcribe(
                    str(audio_path),
                    language="en",
                    beam_size=1,          # Fastest settings
                    word_timestamps=False,
                    vad_filter=False,
                    temperature=0.0,
                    no_speech_threshold=0.6
                )
                
                # Convert to transcript segments
                from scripts.common.transcript_common import TranscriptSegment
                segments = []
                
                for segment in segments_iter:
                    if len(segment.text.strip()) > 3:
                        ts = TranscriptSegment(
                            start=segment.start,
                            end=segment.end,
                            text=segment.text.strip()
                        )
                        segments.append(ts)
                
                method = "whisper_dedicated"
                metadata = {
                    "model": "base",
                    "worker_id": worker_id,
                    "dedicated_model": True,
                    "detected_language": info.language,
                    "language_probability": info.language_probability,
                    "duration": info.duration
                }
                
                worker_logger.info(f"✅ Worker {worker_id}: Transcribed {video_id} - {len(segments)} segments")
                
        except Exception as e:
            worker_logger.error(f"❌ Worker {worker_id}: Transcription failed for {video_id}: {e}")
            db.update_ingest_status(
                video_id, 'error',
                error=str(e),
                increment_retries=True
            )
            return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": str(e)}
        
        finally:
            # Cleanup audio file
            if audio_path and audio_path.exists():
                try:
                    audio_path.unlink()
                except:
                    pass
        
        if not segments:
            error = "No transcript segments generated"
            worker_logger.error(f"❌ Worker {worker_id}: {error} for {video_id}")
            db.update_ingest_status(video_id, 'error', error=error, increment_retries=True)
            return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": error}
        
        # Update transcript status
        db.update_ingest_status(
            video_id, 'transcribed',
            has_yt_transcript=(method == 'youtube'),
            has_whisper=(method != 'youtube')
        )
        
        # Step 2: Chunk transcript 
        chunks = []
        for i, segment in enumerate(segments):
            chunk = ChunkData.from_transcript_segment(segment, video_id)
            chunks.append(chunk)
        
        db.update_ingest_status(
            video_id, 'chunked',
            chunk_count=len(chunks)
        )
        
        # Step 3: Generate embeddings
        texts = [chunk.text for chunk in chunks]
        embeddings = embedder.generate_embeddings(texts)
        
        # Attach embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        db.update_ingest_status(
            video_id, 'embedded',
            embedding_count=len(embeddings)
        )
        
        # Step 4: Upsert to database
        source_id = db.upsert_source(video_info, source_type='youtube')
        
        # Update chunks with correct source_id
        for chunk in chunks:
            chunk.source_id = source_id
        
        chunk_count = db.upsert_chunks(chunks)
        db.update_ingest_status(video_id, 'upserted')
        
        # Final status
        db.update_ingest_status(video_id, 'done')
        
        processing_time = time.time() - start_time
        
        worker_logger.info(f"✅ Worker {worker_id}: COMPLETED {video_id} in {processing_time:.1f}s - {len(chunks)} chunks, {method}")
        
        return {
            "worker_id": worker_id,
            "video_id": video_id,
            "success": True,
            "processing_time": processing_time,
            "chunks": len(chunks),
            "method": method
        }
        
    except Exception as e:
        worker_logger.error(f"❌ Worker {worker_id}: FAILED {video_info.video_id}: {e}")
        return {"worker_id": worker_id, "video_id": video_info.video_id, "success": False, "error": str(e)}

class TrueParallelYouTubeIngester:
    """True parallel YouTube ingestion with dedicated Whisper models per worker"""
    
    def __init__(self, config: IngestConfig):
        self.config = config
        
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
            if self.config.source != 'yt-dlp':
                raise ValueError("--from-json only supported with yt-dlp source")
            videos = self.video_lister.list_from_json(self.config.from_json)
        else:
            if hasattr(self.video_lister, 'list_channel_videos'):
                videos = self.video_lister.list_channel_videos(self.config.channel_url)
            else:
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
        
        if self.config.limit:
            videos = videos[:self.config.limit]
        
        return videos
    
    def run_true_parallel(self) -> Dict[str, int]:
        """Run true parallel processing with dedicated models per worker"""
        logger.info(f"🚀 STARTING TRUE PARALLEL PROCESSING")
        logger.info(f"🔥 Workers: {self.config.num_workers}")
        logger.info(f"💪 Each worker gets dedicated Whisper model on RTX 5080")
        
        # Get videos to process
        videos = self.list_videos()
        
        if not videos:
            logger.error("No videos found to process")
            return {"total": 0, "success": 0, "errors": 0}
        
        logger.info(f"📊 Found {len(videos)} videos to process")
        
        # Prepare worker arguments
        worker_args = [
            (worker_id, video, self.config)
            for worker_id, video in enumerate(videos)
        ]
        
        # Process with true parallelism - all workers simultaneously
        start_time = time.time()
        results = []
        
        logger.info(f"🚀 Launching {min(len(worker_args), self.config.num_workers)} parallel workers...")
        
        with multiprocessing.Pool(processes=self.config.num_workers) as pool:
            # Use imap for progress tracking
            result_iter = pool.imap(process_video_worker, worker_args)
            
            # Track progress
            for result in tqdm.tqdm(result_iter, total=len(worker_args), desc="TRUE PARALLEL PROCESSING"):
                results.append(result)
        
        # Calculate final statistics
        total_time = time.time() - start_time
        successful = [r for r in results if r["success"] and not r.get("skipped", False)]
        skipped = [r for r in results if r.get("skipped", False)]
        failed = [r for r in results if not r["success"]]
        
        logger.info("")
        logger.info("🏁 TRUE PARALLEL PROCESSING COMPLETE!")
        logger.info(f"⏱️ Total time: {total_time:.1f}s")
        logger.info(f"📊 Total videos: {len(videos)}")
        logger.info(f"✅ Successful: {len(successful)}")
        logger.info(f"⏭️ Skipped: {len(skipped)}")
        logger.info(f"❌ Failed: {len(failed)}")
        logger.info(f"🚀 Success rate: {len(successful)/(len(videos)-len(skipped))*100:.1f}%" if len(videos) > len(skipped) else "N/A")
        
        if successful:
            avg_time = sum(r["processing_time"] for r in successful) / len(successful)
            logger.info(f"⚡ Average processing time per video: {avg_time:.1f}s")
            logger.info(f"🔥 Expected GPU utilization: 60-80% during processing")
        
        return {
            "total": len(videos),
            "success": len(successful),
            "skipped": len(skipped),
            "errors": len(failed)
        }

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="True Parallel YouTube Ingestion")
    parser.add_argument('--source', choices=['yt-dlp', 'api'], default='yt-dlp',
                       help='Video source (default: yt-dlp)')
    parser.add_argument('--from-json', type=Path,
                       help='Load videos from yt-dlp JSON file')
    parser.add_argument('--channel-url',
                       help='YouTube channel URL to process')
    parser.add_argument('--workers', type=int, default=16,
                       help='Number of parallel workers (default: 16)')
    parser.add_argument('--limit', type=int,
                       help='Maximum number of videos to process')
    parser.add_argument('--skip-shorts', action='store_true',
                       help='Skip videos shorter than 120 seconds')
    parser.add_argument('--newest-first', action='store_true',
                       help='Process newest videos first')
    parser.add_argument('--max-duration', type=int,
                       help='Maximum video duration in seconds')
    
    args = parser.parse_args()
    
    config = IngestConfig(
        source=args.source,
        from_json=args.from_json,
        channel_url=args.channel_url,
        num_workers=args.workers,
        limit=args.limit,
        skip_shorts=args.skip_shorts,
        newest_first=args.newest_first,
        max_duration=args.max_duration
    )
    
    ingester = TrueParallelYouTubeIngester(config)
    results = ingester.run_true_parallel()
    
    logger.info(f"Final results: {results}")

if __name__ == "__main__":
    main()
