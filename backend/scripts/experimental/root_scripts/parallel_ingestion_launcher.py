#!/usr/bin/env python3
"""
TRUE PARALLEL YouTube Ingestion - Multiple Independent Processes
Bypasses ALL GIL limitations by running separate Python processes
"""

import os
import sys
import time
import subprocess
import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_ingestion_process(worker_id: int, video_limit: int, offset: int = 0):
    """
    Run a single ingestion process for a subset of videos
    """
    cmd = [
        sys.executable,
        'backend/scripts/ingest_youtube_robust.py',
        '--source', 'yt-dlp',
        '--limit', str(video_limit),
        '--concurrency', '3',  # Each process uses 3 threads
        '--skip-shorts',
        '--newest-first',
        '--verbose'
    ]
    
    # Add offset for this worker
    if offset > 0:
        cmd.extend(['--skip', str(offset)])
    
    logger.info(f"🚀 Starting worker {worker_id}: processing {video_limit} videos (offset {offset})")
    
    try:
        # Run the process
        result = subprocess.run(
            cmd,
            cwd=os.getcwd(),
            capture_output=False,  # Let output stream to console
            text=True,
            timeout=7200  # 2 hour timeout per worker
        )
        
        if result.returncode == 0:
            logger.info(f"✅ Worker {worker_id} completed successfully")
            return worker_id, True, "Success"
        else:
            logger.error(f"❌ Worker {worker_id} failed with exit code {result.returncode}")
            return worker_id, False, f"Exit code {result.returncode}"
            
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ Worker {worker_id} timed out after 2 hours")
        return worker_id, False, "Timeout"
    except Exception as e:
        logger.error(f"💥 Worker {worker_id} crashed: {e}")
        return worker_id, False, str(e)

def main():
    """
    Launch multiple parallel ingestion processes
    """
    # Configuration
    TOTAL_VIDEOS = 500
    NUM_WORKERS = 4  # 4 separate processes
    VIDEOS_PER_WORKER = TOTAL_VIDEOS // NUM_WORKERS
    
    logger.info(f"🎯 STARTING TRUE PARALLEL INGESTION")
    logger.info(f"📊 Total videos: {TOTAL_VIDEOS}")
    logger.info(f"👥 Workers: {NUM_WORKERS}")
    logger.info(f"📹 Videos per worker: {VIDEOS_PER_WORKER}")
    logger.info(f"🔥 Total GPU threads: {NUM_WORKERS * 3} = TRUE PARALLELISM!")
    
    start_time = time.time()
    
    # Launch all workers simultaneously
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = []
        
        for worker_id in range(NUM_WORKERS):
            offset = worker_id * VIDEOS_PER_WORKER
            future = executor.submit(
                run_ingestion_process,
                worker_id + 1,
                VIDEOS_PER_WORKER,
                offset
            )
            futures.append(future)
        
        # Wait for all workers to complete
        results = []
        for future in futures:
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Worker failed: {e}")
                results.append((0, False, str(e)))
    
    # Report final results
    duration = time.time() - start_time
    successful_workers = sum(1 for _, success, _ in results if success)
    
    logger.info(f"")
    logger.info(f"🏁 PARALLEL INGESTION COMPLETE")
    logger.info(f"⏱️ Total time: {duration/60:.1f} minutes")
    logger.info(f"✅ Successful workers: {successful_workers}/{NUM_WORKERS}")
    logger.info(f"📈 Estimated videos processed: {successful_workers * VIDEOS_PER_WORKER}")
    
    for worker_id, success, message in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"   Worker {worker_id}: {status} - {message}")

if __name__ == "__main__":
    main()
