#!/usr/bin/env python3
"""
SPEED-OPTIMIZED YouTube Ingestion for Dr. Chaffee
Balances quality and performance for faster processing

Key optimizations:
1. medium model instead of large-v3 (3x faster, 95% quality)
2. Optimized batch size and beam settings
3. VAD (Voice Activity Detection) to skip silence
4. Faster embedding generation
5. More aggressive parallelism
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
from backend.scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from backend.scripts.common.list_videos_api import YouTubeAPILister
from backend.scripts.common.transcript_fetch import TranscriptFetcher
from backend.scripts.common.database_upsert import DatabaseUpserter, ChunkData
from backend.scripts.common.embeddings import EmbeddingGenerator
from backend.scripts.common.transcript_processor import TranscriptProcessor

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration for speed optimization
WHISPER_MODEL_OPTIMIZED = os.getenv('WHISPER_MODEL_OPTIMIZED', 'medium')  # 3x faster than large-v3
WHISPER_COMPUTE_TYPE = os.getenv('WHISPER_COMPUTE_TYPE', 'float16')
CHUNK_DURATION = int(os.getenv('CHUNK_DURATION_SECONDS', '45'))
BATCH_SIZE_OPTIMIZED = int(os.getenv('BATCH_SIZE_OPTIMIZED', '16'))  # Larger batches
BEAM_SIZE_OPTIMIZED = int(os.getenv('BEAM_SIZE_OPTIMIZED', '1'))     # Faster beam search
TEMPERATURE_OPTIMIZED = float(os.getenv('TEMPERATURE_OPTIMIZED', '0.0'))

@dataclass
class IngestionConfig:
    """Configuration for optimized ingestion"""
    whisper_model: str = WHISPER_MODEL_OPTIMIZED
    compute_type: str = WHISPER_COMPUTE_TYPE
    batch_size: int = BATCH_SIZE_OPTIMIZED
    beam_size: int = BEAM_SIZE_OPTIMIZED
    temperature: float = TEMPERATURE_OPTIMIZED
    enable_vad: bool = True  # Voice Activity Detection
    num_workers: int = 6     # More workers for speed
    chunk_duration: int = CHUNK_DURATION

def get_optimal_workers_speed() -> int:
    """Calculate optimal worker count for speed optimization"""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            
            # medium model uses ~1.5GB per worker (vs 5GB for large-v3)
            # This allows us to run more workers simultaneously
            if gpu_memory >= 16:      # RTX 5080
                return 6              # 6x medium models = ~9GB total
            elif gpu_memory >= 12:    # RTX 4080
                return 4              # 4x medium models = ~6GB total  
            elif gpu_memory >= 8:     # RTX 4070
                return 3              # 3x medium models = ~4.5GB total
            else:
                return 2              # 2x medium models = ~3GB total
        
        # CPU fallback
        cpu_count = multiprocessing.cpu_count()
        return min(cpu_count // 2, 4)
        
    except Exception as e:
        logger.warning(f"Could not determine optimal workers: {e}")
        return 4

def initialize_worker_optimized(worker_id: int, config: IngestionConfig) -> Optional[Any]:
    """Initialize optimized Whisper model for this worker"""
    try:
        import faster_whisper
        import torch
        
        logger.info(f"🚀 Worker {worker_id}: Loading OPTIMIZED {config.whisper_model.upper()} model")
        
        # Log GPU status
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            logger.info(f"⚡ Worker {worker_id}: Using {gpu_name} ({gpu_memory:.1f}GB)")
        
        # Optimized model loading
        model = faster_whisper.WhisperModel(
            config.whisper_model,
            device="cuda" if torch.cuda.is_available() else "cpu",
            compute_type=config.compute_type,
            cpu_threads=1,        # Minimal CPU threads per worker
            num_workers=1         # One worker per model instance
        )
        
        logger.info(f"✅ Worker {worker_id}: {config.whisper_model.upper()} model loaded successfully")
        return model
        
    except Exception as e:
        logger.error(f"❌ Worker {worker_id}: Failed to load model: {e}")
        return None

def process_video_optimized(args_tuple) -> Dict[str, Any]:
    """Process a single video with speed optimizations"""
    video, worker_id, config = args_tuple
    
    try:
        logger.info(f"🎬 Worker {worker_id}: Processing {video.video_id} - {video.title[:50]}...")
        
        # Initialize components
        model = initialize_worker_optimized(worker_id, config)
        if not model:
            raise Exception("Failed to initialize Whisper model")
        
        transcript_fetcher = TranscriptFetcher(
            api_key=os.getenv('YOUTUBE_API_KEY'),
            ffmpeg_path=os.getenv('FFMPEG_PATH')
        )
        
        processor = TranscriptProcessor()
        embedding_generator = EmbeddingGenerator()
        upserter = DatabaseUpserter()
        
        # Step 1: Get transcript with optimized settings
        start_time = time.time()
        
        # Try API transcript first (fastest), then fallback to Whisper
        segments = []
        method = "unknown"
        
        try:
            # Quick API attempt
            segments, method, metadata = transcript_fetcher.fetch_transcript(video.video_id)
            logger.info(f"🏃 Worker {worker_id}: Got {method} transcript in {time.time() - start_time:.1f}s")
        except:
            # Fallback to optimized Whisper
            logger.info(f"⚡ Worker {worker_id}: Using optimized Whisper transcription")
            
            # Download and process audio
            audio_path = transcript_fetcher.download_audio(video.video_id)
            if not audio_path or not os.path.exists(audio_path):
                raise Exception("Failed to download audio")
            
            # Optimized transcription
            result = model.transcribe(
                audio_path,
                batch_size=config.batch_size,
                beam_size=config.beam_size,
                temperature=config.temperature,
                vad_filter=config.enable_vad,          # Skip silence
                word_timestamps=True,
                language="en"
            )
            
            # Convert to segments
            segments = []
            for segment in result[0]:
                segments.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text.strip()
                })
            
            method = f"whisper_{config.whisper_model}_optimized"
            
            # Cleanup
            try:
                os.remove(audio_path)
            except:
                pass
        
        if not segments:
            logger.warning(f"⚠️ Worker {worker_id}: No segments for {video.video_id}")
            return {"success": False, "video_id": video.video_id, "error": "No segments"}
        
        transcript_time = time.time() - start_time
        
        # Step 2: Process into chunks (optimized)
        chunks = processor.process_segments(
            segments, 
            chunk_duration_seconds=config.chunk_duration,
            overlap_seconds=5  # Reduced overlap for speed
        )
        
        # Step 3: Generate embeddings (batch processing for speed)
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = embedding_generator.generate_batch(chunk_texts)  # Batch generation
        
        # Step 4: Create chunk data
        chunk_data_list = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_data = ChunkData(
                source_id=video.video_id,
                source_type="youtube",
                title=video.title,
                description="",  # Skip description for speed
                chunk_index=i,
                start_time_seconds=chunk.start_time_seconds,
                end_time_seconds=chunk.end_time_seconds,
                text=chunk.text,
                embedding=embedding,
                word_count=len(chunk.text.split()),
                url=f"https://www.youtube.com/watch?v={video.video_id}",
                published_at=video.published_at,
                duration_seconds=video.duration_seconds,
                metadata={
                    "transcript_method": method,
                    "processing_time": time.time() - start_time,
                    "transcript_time": transcript_time,
                    "worker_id": worker_id,
                    "model": config.whisper_model,
                    "optimized": True
                }
            )
            chunk_data_list.append(chunk_data)
        
        # Step 5: Upsert to database
        upserter.upsert_chunks(chunk_data_list)
        
        total_time = time.time() - start_time
        speed_ratio = video.duration_seconds / total_time if total_time > 0 else 0
        
        result = {
            "success": True,
            "video_id": video.video_id,
            "title": video.title,
            "chunks": len(chunk_data_list),
            "duration": video.duration_seconds,
            "processing_time": total_time,
            "speed_ratio": speed_ratio,
            "method": method,
            "worker_id": worker_id,
            "model": config.whisper_model
        }
        
        logger.info(f"✅ Worker {worker_id}: Completed {video.video_id} - {len(chunk_data_list)} chunks in {total_time:.1f}s ({speed_ratio:.2f}x real-time)")
        return result
        
    except Exception as e:
        logger.error(f"❌ Worker {worker_id}: Error processing {video.video_id}: {e}")
        return {"success": False, "video_id": video.video_id, "error": str(e), "worker_id": worker_id}

def main():
    parser = argparse.ArgumentParser(description="Speed-Optimized YouTube Ingestion")
    parser.add_argument('--source', choices=['yt-dlp', 'api'], default='yt-dlp',
                       help='Data source (default: yt-dlp)')
    parser.add_argument('--channel-url', 
                       default=os.getenv('YOUTUBE_CHANNEL_URL'),
                       help='YouTube channel URL')
    parser.add_argument('--limit', type=int, default=50,
                       help='Maximum number of videos to process')
    parser.add_argument('--workers', type=int, default=0,
                       help='Number of workers (0 = auto-detect)')
    parser.add_argument('--model', choices=['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3'],
                       default=WHISPER_MODEL_OPTIMIZED,
                       help=f'Whisper model (default: {WHISPER_MODEL_OPTIMIZED})')
    parser.add_argument('--skip-shorts', action='store_true',
                       help='Skip videos shorter than 120 seconds')
    parser.add_argument('--newest-first', action='store_true', default=True,
                       help='Process newest videos first')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without doing it')
    
    args = parser.parse_args()
    
    # Create optimized configuration
    config = IngestionConfig(
        whisper_model=args.model,
        num_workers=args.workers or get_optimal_workers_speed()
    )
    
    logger.info(f"🚀 Starting SPEED-OPTIMIZED YouTube Ingestion")
    logger.info(f"⚡ Model: {config.whisper_model.upper()} (optimized for speed)")
    logger.info(f"🔥 Workers: {config.num_workers}")
    logger.info(f"🎯 Target: {args.limit} videos")
    
    # Get videos
    if args.source == 'api':
        lister = YouTubeAPILister()
    else:
        lister = YtDlpVideoLister()
    
    logger.info(f"📡 Fetching videos from {args.channel_url}...")
    videos = lister.list_channel_videos(
        args.channel_url,
        limit=args.limit,
        skip_shorts=args.skip_shorts,
        newest_first=args.newest_first
    )
    
    if not videos:
        logger.error("❌ No videos found")
        return
    
    logger.info(f"📺 Found {len(videos)} videos to process")
    
    if args.dry_run:
        for video in videos[:10]:
            logger.info(f"Would process: {video.video_id} - {video.title}")
        return
    
    # Process videos with optimized multiprocessing
    start_time = time.time()
    
    # Prepare arguments for workers
    worker_args = [
        (video, i % config.num_workers, config) 
        for i, video in enumerate(videos)
    ]
    
    logger.info(f"🔥 Starting {config.num_workers} optimized workers...")
    
    with multiprocessing.Pool(processes=config.num_workers) as pool:
        results = list(tqdm.tqdm(
            pool.imap(process_video_optimized, worker_args),
            total=len(videos),
            desc="Processing videos"
        ))
    
    # Summary
    total_time = time.time() - start_time
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    
    total_chunks = sum(r.get("chunks", 0) for r in successful)
    avg_speed = sum(r.get("speed_ratio", 0) for r in successful) / len(successful) if successful else 0
    
    logger.info(f"🎉 SPEED-OPTIMIZED INGESTION COMPLETE!")
    logger.info(f"📊 Results: {len(successful)} successful, {len(failed)} failed")
    logger.info(f"⚡ Total chunks: {total_chunks}")
    logger.info(f"🏃 Average speed: {avg_speed:.2f}x real-time")
    logger.info(f"⏱️ Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    logger.info(f"📈 Throughput: {len(successful)/(total_time/60):.1f} videos/minute")

if __name__ == "__main__":
    main()
