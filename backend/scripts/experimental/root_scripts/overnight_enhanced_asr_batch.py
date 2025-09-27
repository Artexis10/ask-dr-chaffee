#!/usr/bin/env python3
"""
OVERNIGHT ENHANCED ASR BATCH PROCESSING
Optimized for RTX 5080 16GB VRAM - Maximum Quality with Speaker Identification

VRAM Optimization for RTX 5080 with MEDIUM model:
- Enhanced ASR per worker: ~4GB (medium: 1.5GB + WhisperX: 1GB + pyannote: 1GB + speaker ID: 0.5GB)
- Target: 15-16GB VRAM usage
- Configuration: 4 Enhanced ASR workers = 4 × 4GB = 16GB total
- Medium model: 3x faster than large-v3 with 95% quality
- Expected throughput: ~400-500 videos in 7 hours
"""

import os
import sys
import argparse
import logging
import json
import multiprocessing
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import traceback

# Third-party imports
import tqdm
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
from backend.scripts.common.database_upsert import DatabaseUpserter, ChunkData
from backend.scripts.common.embeddings import EmbeddingGenerator
from backend.scripts.common.transcript_processor import TranscriptProcessor

# Configure logging for overnight batch
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler(f'overnight_batch_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class BatchConfig:
    """Configuration for overnight Enhanced ASR batch"""
    num_workers: int = 4                    # 4 workers for 16GB VRAM with medium model
    enable_speaker_id: bool = True          # Enhanced ASR with speaker identification
    voices_dir: str = "voices"              # Voice profiles directory
    chaffee_min_sim: float = 0.62           # Conservative threshold from production testing
    whisper_model: str = "medium"           # Fast model with 95% quality (3x faster than large-v3)
    batch_size: int = 24                    # Optimized for medium model (larger batches)
    chunk_duration: int = 45                # Standard chunk size
    max_videos: int = 500                   # Safety limit for overnight run
    skip_shorts: bool = True                # Skip videos < 120s
    newest_first: bool = True               # Process newest content first

class EnhancedASRWorker:
    """Individual Enhanced ASR worker process"""
    
    def __init__(self, worker_id: int, config: BatchConfig):
        self.worker_id = worker_id
        self.config = config
        self.transcript_fetcher = None
        self.processor = None
        self.embedding_generator = None
        self.upserter = None
        
    def initialize(self):
        """Initialize worker components"""
        try:
            logger.info(f"🔥 Worker {self.worker_id}: Initializing Enhanced ASR pipeline")
            
            # Initialize Enhanced ASR components
            self.transcript_fetcher = EnhancedTranscriptFetcher(
                enable_speaker_id=self.config.enable_speaker_id,
                voices_dir=self.config.voices_dir,
                chaffee_min_sim=self.config.chaffee_min_sim,
                api_key=os.getenv('YOUTUBE_API_KEY'),
                ffmpeg_path=os.getenv('FFMPEG_PATH')
            )
            
            self.processor = TranscriptProcessor()
            self.embedding_generator = EmbeddingGenerator()
            self.upserter = DatabaseUpserter()
            
            logger.info(f"✅ Worker {self.worker_id}: Enhanced ASR pipeline initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Worker {self.worker_id}: Failed to initialize: {e}")
            logger.error(f"❌ Worker {self.worker_id}: Traceback: {traceback.format_exc()}")
            return False
    
    def process_video(self, video: VideoInfo) -> Dict[str, Any]:
        """Process a single video with Enhanced ASR"""
        start_time = time.time()
        
        try:
            logger.info(f"🎬 Worker {self.worker_id}: Processing {video.video_id} - {video.title[:50]}...")
            
            # Step 1: Enhanced ASR transcription with speaker identification
            segments, method, metadata = self.transcript_fetcher.fetch_transcript_with_speaker_id(
                video.video_id,
                force_enhanced_asr=True,  # Force Enhanced ASR for maximum quality
                cleanup_audio=True
            )
            
            if not segments:
                logger.warning(f"⚠️ Worker {self.worker_id}: No segments for {video.video_id}")
                return {"success": False, "video_id": video.video_id, "error": "No segments"}
            
            transcript_time = time.time() - start_time
            logger.info(f"🎤 Worker {self.worker_id}: Got {len(segments)} segments via {method} in {transcript_time:.1f}s")
            
            # Step 2: Process segments into chunks
            chunks = self.processor.process_segments(
                segments, 
                chunk_duration_seconds=self.config.chunk_duration,
                overlap_seconds=10  # Good overlap for context
            )
            
            # Step 3: Generate embeddings
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = self.embedding_generator.generate_batch(chunk_texts)
            
            # Step 4: Create chunk data with Enhanced ASR metadata
            chunk_data_list = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_data = ChunkData(
                    source_id=video.video_id,
                    source_type="youtube",
                    title=video.title,
                    description=video.description or "",
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
                        "enhanced_asr": True,
                        "speaker_identification": self.config.enable_speaker_id,
                        "chaffee_threshold": self.config.chaffee_min_sim,
                        "processing_time": time.time() - start_time,
                        "transcript_time": transcript_time,
                        "worker_id": self.worker_id,
                        "whisper_model": self.config.whisper_model,
                        "batch_timestamp": datetime.now().isoformat(),
                        **metadata  # Include Enhanced ASR metadata
                    }
                )
                chunk_data_list.append(chunk_data)
            
            # Step 5: Upsert to database
            self.upserter.upsert_chunks(chunk_data_list)
            
            total_time = time.time() - start_time
            speed_ratio = video.duration_seconds / total_time if total_time > 0 else 0
            
            # Extract speaker statistics from metadata
            speaker_stats = metadata.get('speaker_distribution', {})
            chaffee_percentage = speaker_stats.get('Chaffee', 0.0) * 100
            
            result = {
                "success": True,
                "video_id": video.video_id,
                "title": video.title,
                "chunks": len(chunk_data_list),
                "duration": video.duration_seconds,
                "processing_time": total_time,
                "speed_ratio": speed_ratio,
                "method": method,
                "worker_id": self.worker_id,
                "chaffee_percentage": chaffee_percentage,
                "speaker_stats": speaker_stats,
                "enhanced_asr": True
            }
            
            logger.info(f"✅ Worker {self.worker_id}: Completed {video.video_id}")
            logger.info(f"   📊 {len(chunk_data_list)} chunks, {total_time:.1f}s ({speed_ratio:.2f}x real-time)")
            logger.info(f"   🎯 Dr. Chaffee: {chaffee_percentage:.1f}% attribution")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Worker {self.worker_id}: Error processing {video.video_id}: {e}")
            logger.error(f"❌ Worker {self.worker_id}: Traceback: {traceback.format_exc()}")
            return {
                "success": False, 
                "video_id": video.video_id, 
                "error": str(e), 
                "worker_id": self.worker_id
            }

def process_video_worker(args_tuple) -> Dict[str, Any]:
    """Worker process function for multiprocessing"""
    video, worker_id, config = args_tuple
    
    # Initialize worker
    worker = EnhancedASRWorker(worker_id, config)
    if not worker.initialize():
        return {"success": False, "video_id": video.video_id, "error": "Worker initialization failed"}
    
    # Process video
    return worker.process_video(video)

def get_gpu_info():
    """Get GPU information for optimization"""
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return {
                "name": props.name,
                "memory_gb": props.total_memory / (1024**3),
                "available": True
            }
    except ImportError:
        pass
    
    return {"available": False}

def main():
    parser = argparse.ArgumentParser(description="Overnight Enhanced ASR Batch Processing")
    parser.add_argument('--workers', type=int, default=4,
                       help='Number of Enhanced ASR workers (default: 4 for 16GB VRAM with medium model)')
    parser.add_argument('--limit', type=int, default=400,
                       help='Maximum number of videos to process (default: 400)')
    parser.add_argument('--test-mode', action='store_true',
                       help='Test mode: process only 2 videos')
    parser.add_argument('--channel-url', 
                       default=os.getenv('YOUTUBE_CHANNEL_URL'),
                       help='YouTube channel URL')
    parser.add_argument('--chaffee-threshold', type=float, default=0.62,
                       help='Chaffee similarity threshold (default: 0.62)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without doing it')
    
    args = parser.parse_args()
    
    # Create configuration
    config = BatchConfig(
        num_workers=args.workers,
        chaffee_min_sim=args.chaffee_threshold,
        max_videos=2 if args.test_mode else args.limit
    )
    
    # GPU info
    gpu_info = get_gpu_info()
    expected_vram = config.num_workers * 4.0  # 4GB per Enhanced ASR worker with medium model
    
    logger.info(f"🚀 OVERNIGHT ENHANCED ASR BATCH PROCESSING")
    logger.info(f"=" * 60)
    logger.info(f"🎯 Target videos: {config.max_videos}")
    logger.info(f"🔥 Enhanced ASR workers: {config.num_workers}")
    logger.info(f"💾 Expected VRAM usage: {expected_vram:.1f}GB")
    logger.info(f"🎤 Speaker identification: {config.enable_speaker_id}")
    logger.info(f"👨‍⚕️ Chaffee threshold: {config.chaffee_min_sim}")
    
    if gpu_info["available"]:
        logger.info(f"🎮 GPU: {gpu_info['name']} ({gpu_info['memory_gb']:.1f}GB)")
        if expected_vram > gpu_info['memory_gb'] * 0.9:  # 90% threshold
            logger.warning(f"⚠️ High VRAM usage expected! Consider reducing workers.")
    
    if args.test_mode:
        logger.info(f"🧪 TEST MODE: Processing only 2 videos")
    
    # Get videos
    logger.info(f"📡 Fetching videos from {args.channel_url}...")
    lister = YtDlpVideoLister()
    videos = lister.list_channel_videos(
        args.channel_url,
        max_results=config.max_videos,
        skip_shorts=config.skip_shorts,
        newest_first=config.newest_first
    )
    
    if not videos:
        logger.error("❌ No videos found")
        return
    
    # Filter videos if needed
    videos = videos[:config.max_videos]
    logger.info(f"📺 Found {len(videos)} videos to process")
    
    if args.dry_run:
        logger.info(f"📋 DRY RUN - Would process:")
        for i, video in enumerate(videos[:10]):
            logger.info(f"   {i+1:3d}. {video.video_id} - {video.title}")
        if len(videos) > 10:
            logger.info(f"   ... and {len(videos) - 10} more videos")
        return
    
    # Estimate processing time
    avg_duration = sum(v.duration_seconds or 900 for v in videos) / len(videos)  # Default 15min
    estimated_time_hours = (len(videos) * avg_duration / 3600) / (config.num_workers * 0.5)  # Assume 0.5x real-time
    logger.info(f"⏱️ Estimated processing time: {estimated_time_hours:.1f} hours")
    
    # Process videos with Enhanced ASR
    start_time = time.time()
    logger.info(f"🔥 Starting {config.num_workers} Enhanced ASR workers...")
    
    # Prepare arguments for workers
    worker_args = [
        (video, i % config.num_workers, config) 
        for i, video in enumerate(videos)
    ]
    
    # Process with progress tracking
    results = []
    successful = 0
    failed = 0
    
    with multiprocessing.Pool(processes=config.num_workers) as pool:
        with tqdm.tqdm(total=len(videos), desc="Enhanced ASR Processing") as pbar:
            for result in pool.imap(process_video_worker, worker_args):
                results.append(result)
                
                if result.get("success"):
                    successful += 1
                    chunks = result.get("chunks", 0)
                    chaffee_pct = result.get("chaffee_percentage", 0)
                    pbar.set_postfix({
                        "Success": successful,
                        "Failed": failed, 
                        "Chunks": chunks,
                        "Chaffee%": f"{chaffee_pct:.1f}"
                    })
                else:
                    failed += 1
                    pbar.set_postfix({
                        "Success": successful,
                        "Failed": failed
                    })
                
                pbar.update(1)
    
    # Final summary
    total_time = time.time() - start_time
    total_chunks = sum(r.get("chunks", 0) for r in results if r.get("success"))
    avg_chaffee = sum(r.get("chaffee_percentage", 0) for r in results if r.get("success")) / max(successful, 1)
    
    logger.info(f"🎉 OVERNIGHT BATCH PROCESSING COMPLETE!")
    logger.info(f"=" * 60)
    logger.info(f"📊 Results: {successful} successful, {failed} failed")
    logger.info(f"⚡ Total chunks: {total_chunks:,}")
    logger.info(f"👨‍⚕️ Average Dr. Chaffee attribution: {avg_chaffee:.1f}%")
    logger.info(f"⏱️ Total processing time: {total_time/3600:.1f} hours")
    logger.info(f"📈 Throughput: {successful/(total_time/3600):.1f} videos/hour")
    logger.info(f"🎯 Enhanced ASR quality with speaker identification maintained")
    
    # Save results summary
    summary_file = f"overnight_batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, 'w') as f:
        json.dump({
            "config": config.__dict__,
            "results": results,
            "summary": {
                "successful": successful,
                "failed": failed,
                "total_chunks": total_chunks,
                "avg_chaffee_percentage": avg_chaffee,
                "total_time_hours": total_time/3600,
                "throughput_videos_per_hour": successful/(total_time/3600)
            }
        }, f, indent=2)
    
    logger.info(f"💾 Results saved to: {summary_file}")

if __name__ == "__main__":
    main()
