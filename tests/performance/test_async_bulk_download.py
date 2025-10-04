#!/usr/bin/env python3
"""
Test async bulk download with deduplication for current batch processing.
This script demonstrates the async downloader with your current 100-video batch.
"""

import asyncio
import sys
import os
from pathlib import Path
import psycopg2
from typing import List, Dict, Any

# Add backend scripts to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'scripts'))

from common.async_downloader import AsyncAudioDownloader
from common.list_videos_yt_dlp import YtDlpVideoLister

async def test_async_bulk_download():
    """Test async bulk download with the current Dr. Chaffee channel"""
    
    print("TESTING Async Bulk Download with Deduplication")
    print("=" * 60)
    
    # Get database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/ask_dr_chaffee')
    try:
        db_conn = psycopg2.connect(db_url)
        print(f"[OK] Database connected: {db_url.split('@')[1] if '@' in db_url else 'localhost'}")
    except Exception as e:
        print(f"[WARN] Database connection failed: {e}")
        db_conn = None
    
    # Initialize video lister  
    print("\n[INFO] Fetching video list from Dr. Chaffee channel...")
    video_lister = YtDlpVideoLister()
    
    try:
        # Get videos (use cached if available)
        videos = video_lister.list_channel_videos(
            "https://www.youtube.com/@anthonychaffeemd",
            use_cache=True
        )
        
        # Take first 20 videos for testing
        test_videos = videos[:20]
        print(f"[OK] Found {len(videos)} total videos, testing with {len(test_videos)} videos")
        
        # Convert to format expected by async downloader
        video_list = []
        for video in test_videos:
            video_list.append({
                'video_id': video.video_id,
                'title': video.title,
                'url': f"https://www.youtube.com/watch?v={video.video_id}"
            })
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch video list: {e}")
        return
    
    # Initialize async downloader with deduplication
    print(f"\n[FAST] Initializing Async Downloader...")
    storage_dir = Path('./audio_storage')
    
    downloader = AsyncAudioDownloader(
        max_concurrent_downloads=8,  # Max out your concurrency
        storage_dir=storage_dir,
        db_connection=db_conn,
        skip_existing=True  # Enable deduplication
    )
    
    try:
        print(f"[CHECK] Checking for existing videos (DB + local files)...")
        
        # Test deduplication first
        to_download, already_exist = downloader.filter_existing_videos(video_list)
        
        print(f"[STATS] Deduplication Results:")
        print(f"   - Videos to download: {len(to_download)}")
        print(f"   - Videos already exist: {len(already_exist)}")
        
        if already_exist:
            print(f"\n[OK] Skipping these existing videos:")
            for i, video in enumerate(already_exist[:5]):  # Show first 5
                print(f"   {i+1}. {video['video_id']}: {video['title'][:50]}...")
            if len(already_exist) > 5:
                print(f"   ... and {len(already_exist) - 5} more")
        
        if not to_download:
            print(f"\n[SUCCESS] All videos already exist! No downloads needed.")
            print(f"[INFO] This demonstrates perfect deduplication - no wasted resources!")
            return
        
        print(f"\n[START] Starting async bulk download for {len(to_download)} videos...")
        print(f"[FAST] Using {downloader.max_concurrent_downloads} concurrent downloads")
        
        # Start the bulk download
        import time
        start_time = time.time()
        
        completed_tasks = await downloader.bulk_download(to_download)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Show results
        successful = [task for task in completed_tasks if task.status == 'completed']
        failed = [task for task in completed_tasks if task.status == 'failed']
        
        print(f"\n[STATS] Async Bulk Download Results:")
        print(f"   - Total time: {total_time:.1f}s")
        print(f"   - Successful: {len(successful)}")
        print(f"   - Failed: {len(failed)}")
        print(f"   - Average per video: {total_time/max(1, len(to_download)):.1f}s")
        
        if successful:
            print(f"\n[OK] Successfully downloaded:")
            for i, task in enumerate(successful[:5]):  # Show first 5
                duration = (task.end_time - task.start_time) if task.end_time and task.start_time else 0
                print(f"   {i+1}. {task.video_id}: {task.output_path.name} ({duration:.1f}s)")
            if len(successful) > 5:
                print(f"   ... and {len(successful) - 5} more")
        
        if failed:
            print(f"\n[ERROR] Failed downloads:")
            for task in failed:
                print(f"   - {task.video_id}: {task.error[:100]}...")
        
        print(f"\n[PERF] Performance Benefits:")
        if len(to_download) > 1:
            sequential_estimate = len(to_download) * 15  # Rough estimate: 15s per video
            speedup = sequential_estimate / total_time
            print(f"   - Estimated sequential time: {sequential_estimate:.1f}s")
            print(f"   - Actual async time: {total_time:.1f}s")
            print(f"   - Speedup: {speedup:.1f}x faster!")
        
        print(f"\n[INFO] Resource Savings from Deduplication:")
        total_videos = len(video_list)
        saved_downloads = len(already_exist)
        if saved_downloads > 0:
            saved_time = saved_downloads * 15  # Rough estimate
            print(f"   - Avoided {saved_downloads}/{total_videos} downloads")
            print(f"   - Estimated time saved: {saved_time:.0f}s")
            print(f"   - Bandwidth saved: ~{saved_downloads * 50}MB (est.)")
        
    except Exception as e:
        print(f"[ERROR] Async download failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        downloader.cleanup_temp_files()
        if db_conn:
            db_conn.close()

def main():
    """Run the async bulk download test"""
    try:
        asyncio.run(test_async_bulk_download())
    except KeyboardInterrupt:
        print("\n[WARN]  Test interrupted by user")
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
