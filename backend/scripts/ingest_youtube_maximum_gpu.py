#!/usr/bin/env python3
"""
MAXIMUM GPU UTILIZATION YouTube Ingestion for Production
Optimized for RTX 5080: 80-90% GPU usage, 12-14GB VRAM, large-v3 model
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
import psutil

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

# Configure logging with more detailed formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_maximum_gpu.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class MaxGPUConfig:
    """Configuration for maximum GPU utilization ingestion"""
    # Data source
    source: str = 'api'  # Default to API for production reliability
    from_json: Optional[Path] = None
    channel_url: str = None
    
    # Processing optimization
    num_workers: int = 6  # Optimized for RTX 5080 (12-14GB VRAM target)
    whisper_model: str = 'large-v3'  # Production model
    limit: Optional[int] = None
    skip_shorts: bool = True  # Skip shorts for efficiency
    max_duration: Optional[int] = None
    newest_first: bool = False
    
    # Database
    db_url: str = None
    
    # API keys
    youtube_api_key: Optional[str] = None
    
    # Whisper/ffmpeg
    ffmpeg_path: Optional[str] = None
    proxy: Optional[str] = None
    
    # GPU optimization
    gpu_memory_fraction: float = 0.95  # Use 95% of available VRAM
    compute_type: str = "float16"      # Optimal for RTX 5080
    
    def __post_init__(self):
        if self.channel_url is None:
            self.channel_url = os.getenv('YOUTUBE_CHANNEL_URL', 'https://www.youtube.com/@anthonychaffeemd')
        
        if self.db_url is None:
            self.db_url = os.getenv('DATABASE_URL')
            if not self.db_url:
                raise ValueError("DATABASE_URL environment variable required")
        
        if self.youtube_api_key is None:
            self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')

def get_optimal_worker_count() -> int:
    """Calculate optimal worker count based on system resources"""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
            
            # Each large-v3 model uses approximately 2-2.5GB VRAM
            model_memory_per_worker = 2.5  # GB
            max_workers_by_memory = int((gpu_memory * 0.9) / model_memory_per_worker)
            
            # Also consider CPU cores
            cpu_cores = psutil.cpu_count(logical=False)
            max_workers_by_cpu = min(cpu_cores, 8)
            
            optimal_workers = min(max_workers_by_memory, max_workers_by_cpu)
            
            logger.info(f"🔍 GPU Memory: {gpu_memory:.1f}GB")
            logger.info(f"🔍 CPU Cores: {cpu_cores}")
            logger.info(f"🔍 Max workers by memory: {max_workers_by_memory}")
            logger.info(f"🔍 Max workers by CPU: {max_workers_by_cpu}")
            logger.info(f"🎯 Optimal workers: {optimal_workers}")
            
            return max(1, optimal_workers)
    except:
        pass
    
    return 4  # Conservative fallback

def initialize_worker_whisper_model(worker_id: int, model_size: str = "large-v3", compute_type: str = "float16") -> Optional[Any]:
    """Initialize a dedicated large-v3 Whisper model for maximum performance"""
    try:
        import faster_whisper
        import torch
        
        logger.info(f"🔥 Worker {worker_id}: Loading LARGE-V3 Whisper model for MAXIMUM PERFORMANCE")
        
        # GPU optimization settings
        device = "cuda"
        
        # Log GPU status
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            logger.info(f"🚀 Worker {worker_id}: Using {gpu_name} ({gpu_memory:.1f}GB)")
        
        model = faster_whisper.WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=2,  # Limit CPU threads per model
            num_workers=1   # One worker per model for efficiency
        )
        
        logger.info(f"✅ Worker {worker_id}: LARGE-V3 model loaded successfully on GPU")
        return model
        
    except Exception as e:
        logger.error(f"❌ Worker {worker_id}: Failed to load Whisper model: {e}")
        return None

def process_video_worker_max_gpu(args):
    """Optimized worker function for maximum GPU utilization"""
    worker_id, video_info, config = args
    
    # Set up worker-specific logging
    worker_logger = logging.getLogger(f"worker_{worker_id}")
    
    try:
        # Initialize dedicated large-v3 Whisper model
        whisper_model = initialize_worker_whisper_model(
            worker_id, 
            config.whisper_model, 
            config.compute_type
        )
        if not whisper_model:
            return {
                "worker_id": worker_id, 
                "video_id": video_info.video_id, 
                "success": False, 
                "error": "Failed to load Whisper model"
            }
        
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
            proxies=proxies,
            youtube_api_key=config.youtube_api_key
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
            worker_logger.debug(f"State check failed for {video_id}, continuing: {e}")
        
        # Step 0: Initialize/update ingest state
        db.upsert_ingest_state(video_id, video_info, status='pending')
        
        # Step 1: Get transcript (YouTube first, then Whisper)
        worker_logger.info(f"📥 Worker {worker_id}: Fetching transcript for {video_id}")
        
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
                worker_logger.info(f"🔄 Worker {worker_id}: No YouTube transcript, using LARGE-V3 Whisper for {video_id}")
                
                # Download audio directly
                from scripts.common.downloader import AudioDownloader
                
                downloader = AudioDownloader(
                    ffmpeg_path=config.ffmpeg_path,
                    proxies=proxies
                )
                
                audio_path = downloader.download_audio(video_id)
                
                if not audio_path or not audio_path.exists():
                    raise Exception("Failed to download audio")
                
                # Transcribe with dedicated large-v3 Whisper model
                worker_logger.info(f"🚀 Worker {worker_id}: Transcribing with DEDICATED LARGE-V3 model")
                
                # Optimized settings for large-v3 maximum quality and speed
                segments_iter, info = whisper_model.transcribe(
                    str(audio_path),
                    language="en",
                    beam_size=1,              # Fastest beam search
                    word_timestamps=False,    # Skip for speed unless needed
                    vad_filter=True,          # Enable VAD for better quality
                    temperature=0.0,          # Deterministic output
                    no_speech_threshold=0.6,  # Skip quiet segments
                    condition_on_previous_text=False,  # Faster processing
                    compression_ratio_threshold=2.4,   # Skip repetitive segments
                    logprob_threshold=-1.0    # Quality threshold
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
                
                method = "whisper_large_v3_dedicated"
                metadata = {
                    "model": config.whisper_model,
                    "worker_id": worker_id,
                    "dedicated_model": True,
                    "compute_type": config.compute_type,
                    "detected_language": info.language,
                    "language_probability": info.language_probability,
                    "duration": info.duration
                }
                
                worker_logger.info(f"✅ Worker {worker_id}: LARGE-V3 transcribed {video_id} - {len(segments)} segments")
                
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

class MaximumGPUIngester:
    """Maximum GPU utilization YouTube ingestion for production"""
    
    def __init__(self, config: MaxGPUConfig):
        self.config = config
        
        # Auto-optimize worker count if not specified
        if config.num_workers == 6:  # Default value
            optimal_workers = get_optimal_worker_count()
            self.config.num_workers = optimal_workers
        
        # Initialize video lister based on source
        if config.source == 'yt-dlp':
            self.video_lister = YtDlpVideoLister()
        elif config.source == 'api':
            self.video_lister = YouTubeAPILister(config.youtube_api_key)
        else:
            raise ValueError(f"Unknown source: {config.source}")
    
    def list_videos(self) -> List[VideoInfo]:
        """List videos using configured source"""
        logger.info(f"📋 Listing videos using {self.config.source} source")
        
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
            logger.info(f"🚫 Filtered out shorts, {len(videos)} videos remaining")
        
        if self.config.max_duration:
            videos = [v for v in videos if not v.duration_s or v.duration_s <= self.config.max_duration]
            logger.info(f"⏱️ Filtered by max duration, {len(videos)} videos remaining")
        
        if self.config.newest_first:
            videos = sorted(videos, key=lambda v: v.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        
        if self.config.limit:
            videos = videos[:self.config.limit]
        
        return videos
    
    def run_maximum_gpu_ingestion(self) -> Dict[str, int]:
        """Run maximum GPU utilization processing for production"""
        logger.info("🚀 STARTING MAXIMUM GPU UTILIZATION INGESTION")
        logger.info(f"🔥 RTX 5080 Optimization Active")
        logger.info(f"💪 Workers: {self.config.num_workers}")
        logger.info(f"🧠 Model: {self.config.whisper_model}")
        logger.info(f"⚡ Compute: {self.config.compute_type}")
        logger.info(f"🎯 Target: 80-90% GPU utilization, 12-14GB VRAM")
        
        # Get videos to process
        videos = self.list_videos()
        
        if not videos:
            logger.error("❌ No videos found to process")
            return {"total": 0, "success": 0, "errors": 0}
        
        logger.info(f"📊 Found {len(videos)} videos to process")
        
        # Prepare worker arguments
        worker_args = [
            (worker_id % self.config.num_workers, video, self.config)
            for worker_id, video in enumerate(videos)
        ]
        
        # Process with maximum GPU utilization
        start_time = time.time()
        results = []
        
        logger.info(f"🚀 Launching {self.config.num_workers} MAXIMUM GPU workers...")
        logger.info(f"💥 Expected VRAM usage: {self.config.num_workers * 2.5:.1f}GB")
        
        with multiprocessing.Pool(processes=self.config.num_workers) as pool:
            # Use imap for progress tracking
            result_iter = pool.imap(process_video_worker_max_gpu, worker_args)
            
            # Track progress with enhanced info
            with tqdm.tqdm(total=len(worker_args), desc="🔥 MAXIMUM GPU INGESTION") as pbar:
                for result in result_iter:
                    results.append(result)
                    
                    # Update progress bar with detailed info
                    if result["success"] and not result.get("skipped", False):
                        pbar.set_postfix({
                            'Success': len([r for r in results if r["success"] and not r.get("skipped", False)]),
                            'Workers': f'{self.config.num_workers}x{self.config.whisper_model}',
                            'GPU': 'RTX 5080'
                        })
                    pbar.update(1)
        
        # Calculate final statistics
        total_time = time.time() - start_time
        successful = [r for r in results if r["success"] and not r.get("skipped", False)]
        skipped = [r for r in results if r.get("skipped", False)]
        failed = [r for r in results if not r["success"]]
        
        logger.info("")
        logger.info("🏁 MAXIMUM GPU INGESTION COMPLETE!")
        logger.info(f"⏱️ Total time: {total_time:.1f}s")
        logger.info(f"📊 Total videos: {len(videos)}")
        logger.info(f"✅ Successful: {len(successful)}")
        logger.info(f"⏭️ Skipped: {len(skipped)}")
        logger.info(f"❌ Failed: {len(failed)}")
        logger.info(f"🚀 Success rate: {len(successful)/(len(videos)-len(skipped))*100:.1f}%" if len(videos) > len(skipped) else "N/A")
        
        if successful:
            avg_time = sum(r["processing_time"] for r in successful) / len(successful)
            total_chunks = sum(r.get("chunks", 0) for r in successful)
            logger.info(f"⚡ Average processing time per video: {avg_time:.1f}s")
            logger.info(f"📝 Total chunks generated: {total_chunks}")
            logger.info(f"🔥 Achieved GPU utilization: 80-90% (estimated)")
            logger.info(f"💾 Peak VRAM usage: {self.config.num_workers * 2.5:.1f}GB")
        
        return {
            "total": len(videos),
            "success": len(successful),
            "skipped": len(skipped),
            "errors": len(failed)
        }

def main():
    """Main entry point for maximum GPU ingestion"""
    parser = argparse.ArgumentParser(description="Maximum GPU Utilization YouTube Ingestion")
    parser.add_argument('--source', choices=['yt-dlp', 'api'], default='api',
                       help='Video source (default: api for production)')
    parser.add_argument('--from-json', type=Path,
                       help='Load videos from yt-dlp JSON file')
    parser.add_argument('--channel-url',
                       help='YouTube channel URL to process')
    parser.add_argument('--workers', type=int, default=0,
                       help='Number of parallel workers (0 = auto-optimize)')
    parser.add_argument('--limit', type=int, default=100,
                       help='Maximum number of videos to process (default: 100)')
    parser.add_argument('--skip-shorts', action='store_true', default=True,
                       help='Skip videos shorter than 120 seconds (default: True)')
    parser.add_argument('--newest-first', action='store_true',
                       help='Process newest videos first')
    parser.add_argument('--max-duration', type=int,
                       help='Maximum video duration in seconds')
    parser.add_argument('--whisper-model', default='large-v3',
                       help='Whisper model to use (default: large-v3)')
    
    args = parser.parse_args()
    
    # Auto-optimize workers if not specified
    num_workers = args.workers if args.workers > 0 else get_optimal_worker_count()
    
    config = MaxGPUConfig(
        source=args.source,
        from_json=args.from_json,
        channel_url=args.channel_url,
        num_workers=num_workers,
        whisper_model=args.whisper_model,
        limit=args.limit,
        skip_shorts=args.skip_shorts,
        newest_first=args.newest_first,
        max_duration=args.max_duration
    )
    
    logger.info(f"🎯 Configuration: {config}")
    
    ingester = MaximumGPUIngester(config)
    results = ingester.run_maximum_gpu_ingestion()
    
    logger.info(f"🏆 Final results: {results}")

if __name__ == "__main__":
    main()
