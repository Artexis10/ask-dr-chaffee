#!/usr/bin/env python3
"""
Parallel Ingestion Orchestrator - Maximum RTX 5080 Utilization
Launches multiple dedicated Whisper worker processes for true parallelism
"""

import os
import sys
import argparse
import logging
import multiprocessing
import subprocess
from pathlib import Path
from typing import List
import time

# Third-party imports
import tqdm
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_worker_process(worker_id: int, video_id: str, video_title: str, skip_members_only: bool = True, cookies_file: str = None):
    """Run a dedicated worker process for a single video"""
    try:
        worker_script = Path(__file__).parent / "parallel_whisper_worker_fixed.py"
        
        cmd = [
            sys.executable,
            str(worker_script),
            str(worker_id),
            video_id,
            video_title,
            str(skip_members_only).lower(),
            cookies_file or 'none'
        ]
        
        logger.info(f"🚀 Launching Worker {worker_id} for {video_id}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout per video
        )
        
        if result.returncode == 0 and "RESULT:" in result.stdout:
            # Parse result from worker output
            result_line = [line for line in result.stdout.split('\n') if line.startswith('RESULT:')][0]
            result_str = result_line.replace('RESULT: ', '')
            
            # Simple parsing (in production, use JSON)
            success = 'success": True' in result_str
            skipped = 'skipped": True' in result_str
            
            if success and skipped:
                if "members-only" in result_str:
                    logger.info(f"⏭️ Worker {worker_id} skipped {video_id} - members-only content")
                else:
                    logger.info(f"⏭️ Worker {worker_id} skipped {video_id} - already completed")
                return {"worker_id": worker_id, "video_id": video_id, "success": True, "skipped": True}
            elif success:
                logger.info(f"✅ Worker {worker_id} completed {video_id}")
                return {"worker_id": worker_id, "video_id": video_id, "success": True}
            else:
                logger.error(f"❌ Worker {worker_id} failed {video_id}")
                return {"worker_id": worker_id, "video_id": video_id, "success": False}
        else:
            logger.error(f"❌ Worker {worker_id} process failed: {result.stderr}")
            return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": result.stderr}
            
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ Worker {worker_id} timed out for {video_id}")
        return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": "Timeout"}
    except Exception as e:
        logger.error(f"💥 Worker {worker_id} crashed: {e}")
        return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": str(e)}

class ParallelIngestionOrchestrator:
    """Orchestrates multiple parallel Whisper workers for maximum GPU utilization"""
    
    def __init__(self, num_workers: int = 8, skip_members_only: bool = True, cookies_file: str = None):
        self.num_workers = num_workers
        self.skip_members_only = skip_members_only
        self.cookies_file = cookies_file
        self.video_lister = YtDlpVideoLister()
    
    def get_pending_videos(self, limit: int = None) -> List[VideoInfo]:
        """Get videos that need processing"""
        logger.info("📋 Getting videos from database that need processing")
        
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            cursor = conn.cursor()
            
            # Get videos that are pending or need processing
            query = """
                SELECT video_id, title FROM ingest_state 
                WHERE status IN ('pending', 'error') 
                ORDER BY updated_at DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            videos = []
            for video_id, title in results:
                video_info = VideoInfo(
                    video_id=video_id,
                    title=title or f"Video {video_id}",
                    published_at=None,
                    duration_s=None
                )
                videos.append(video_info)
            
            logger.info(f"📊 Found {len(videos)} videos needing processing")
            return videos
            
        except Exception as e:
            logger.error(f"Database error: {e}")
            return []
    
    def run_parallel_processing(self, limit: int = None) -> dict:
        """Run parallel processing with dedicated workers"""
        logger.info(f"🚀 STARTING PARALLEL INGESTION ORCHESTRATOR")
        logger.info(f"🔥 Workers: {self.num_workers}")
        logger.info(f"💪 Each worker = dedicated Whisper model on RTX 5080")
        
        # Get videos to process
        videos = self.get_pending_videos(limit)
        
        if not videos:
            logger.info("No videos need processing")
            return {"total": 0, "success": 0, "errors": 0}
        
        logger.info(f"📊 Processing {len(videos)} videos with {self.num_workers} parallel workers")
        
        start_time = time.time()
        results = []
        
        # Process in batches to avoid overwhelming the system
        batch_size = self.num_workers
        
        for i in range(0, len(videos), batch_size):
            batch = videos[i:i+batch_size]
            logger.info(f"🔄 Processing batch {i//batch_size + 1}: {len(batch)} videos")
            
            # Launch all workers in this batch simultaneously
            with multiprocessing.Pool(processes=len(batch)) as pool:
                worker_args = [
                    (worker_id, video.video_id, video.title, self.skip_members_only, self.cookies_file)
                    for worker_id, video in enumerate(batch)
                ]
                
                batch_results = pool.starmap(run_worker_process, worker_args)
                results.extend(batch_results)
            
            # Brief pause between batches
            if i + batch_size < len(videos):
                logger.info("⏸️ Brief pause between batches...")
                time.sleep(5)
        
        # Final statistics
        total_time = time.time() - start_time
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        logger.info("")
        logger.info("🏁 PARALLEL PROCESSING COMPLETE!")
        logger.info(f"⏱️ Total time: {total_time:.1f}s")
        logger.info(f"📊 Total videos: {len(videos)}")
        logger.info(f"✅ Successful: {len(successful)}")
        logger.info(f"❌ Failed: {len(failed)}")
        logger.info(f"🚀 Success rate: {len(successful)/len(videos)*100:.1f}%")
        logger.info(f"⚡ Average time per video: {total_time/len(successful) if successful else 0:.1f}s")
        
        return {
            "total": len(videos),
            "success": len(successful),
            "errors": len(failed),
            "processing_time": total_time
        }

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Parallel YouTube Ingestion Orchestrator")
    parser.add_argument('--workers', type=int, default=8,
                       help='Number of parallel workers (default: 8)')
    parser.add_argument('--limit', type=int,
                       help='Maximum number of videos to process')
    parser.add_argument('--skip-members-only', action='store_true', default=True,
                       help='Skip members-only videos (default: True)')
    parser.add_argument('--no-skip-members-only', dest='skip_members_only', action='store_false',
                       help='Process members-only videos (requires authentication)')
    parser.add_argument('--cookies-file', type=str,
                       help='Path to YouTube cookies file for member authentication')
    parser.add_argument('--username', type=str,
                       help='YouTube username/email for authentication')
    parser.add_argument('--password', type=str,
                       help='YouTube password for authentication (use cookies instead if possible)')
    
    args = parser.parse_args()
    
    # Pass credentials to environment for workers
    if args.username:
        os.environ['YOUTUBE_USERNAME'] = args.username
    if args.password:
        os.environ['YOUTUBE_PASSWORD'] = args.password
    
    orchestrator = ParallelIngestionOrchestrator(
        num_workers=args.workers,
        skip_members_only=args.skip_members_only,
        cookies_file=args.cookies_file
    )
    results = orchestrator.run_parallel_processing(limit=args.limit)
    
    logger.info(f"Final results: {results}")

if __name__ == "__main__":
    main()
