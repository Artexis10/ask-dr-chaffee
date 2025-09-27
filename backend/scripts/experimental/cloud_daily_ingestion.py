#!/usr/bin/env python3
"""
Cloud Daily Ingestion Orchestrator
Cost-optimized daily cron job for new YouTube videos using OpenAI Whisper API
"""

import os
import sys
import logging
import argparse
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path

# Add parent directories to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from cloud_whisper_worker import CloudProcessingConfig, process_video_with_api_whisper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - CLOUD-DAILY - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CloudDailyIngestionOrchestrator:
    """Cost-optimized daily ingestion for cloud deployment"""
    
    def __init__(self, config: CloudProcessingConfig):
        self.config = config
        self.total_cost = 0.0
        self.processed_videos = []
        
    def get_recent_videos(self, days_back: int = 2, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent videos that need processing"""
        logger.info(f"📋 Getting videos from last {days_back} days")
        
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            cursor = conn.cursor()
            
            # Get videos uploaded in last N days that aren't processed yet
            query = """
                SELECT video_id, title 
                FROM ingest_state 
                WHERE created_at >= NOW() - INTERVAL '%s days'
                AND status != 'done'
                AND (processing_method IS NULL OR processing_method != 'local_gpu')
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            cursor.execute(query, (days_back, limit))
            results = cursor.fetchall()
            
            videos = [{"video_id": row[0], "title": row[1]} for row in results]
            
            cursor.close()
            conn.close()
            
            logger.info(f"📱 Found {len(videos)} videos to process")
            return videos
            
        except Exception as e:
            logger.error(f"❌ Failed to get recent videos: {e}")
            return []
    
    def estimate_total_cost(self, videos: List[Dict[str, str]]) -> float:
        """Estimate total processing cost"""
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            cursor = conn.cursor()
            
            total_duration_minutes = 0
            
            for video in videos:
                # Try to get duration from metadata
                cursor.execute(
                    "SELECT metadata FROM ingest_state WHERE video_id = %s",
                    (video['video_id'],)
                )
                result = cursor.fetchone()
                
                if result and result[0]:
                    import json
                    metadata = json.loads(result[0]) if isinstance(result[0], str) else result[0]
                    duration = metadata.get('duration_s', 1800)  # Default 30 min
                else:
                    duration = 1800  # Default assumption
                
                total_duration_minutes += duration / 60
            
            cursor.close()
            conn.close()
            
            estimated_cost = total_duration_minutes * self.config.cost_per_minute
            logger.info(f"💰 Estimated cost: {total_duration_minutes:.1f} minutes = ${estimated_cost:.4f}")
            
            return estimated_cost
            
        except Exception as e:
            logger.warning(f"⚠️ Could not estimate cost: {e}")
            # Conservative estimate: assume 30 min per video
            return len(videos) * 30 * self.config.cost_per_minute
    
    def process_daily_videos(self, max_cost_usd: float = 5.0, limit: int = 10) -> Dict[str, Any]:
        """Process recent videos with cost protection"""
        start_time = time.time()
        
        logger.info(f"🚀 Starting daily cloud ingestion (max cost: ${max_cost_usd})")
        
        # Get recent videos
        videos = self.get_recent_videos(days_back=3, limit=limit)
        
        if not videos:
            logger.info("✅ No new videos to process")
            return {
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "total_cost": 0.0,
                "processing_time": time.time() - start_time
            }
        
        # Estimate cost
        estimated_cost = self.estimate_total_cost(videos)
        
        if estimated_cost > max_cost_usd:
            logger.warning(f"⚠️ Estimated cost ${estimated_cost:.4f} exceeds limit ${max_cost_usd}")
            # Process subset to stay under budget
            videos = videos[:int(len(videos) * max_cost_usd / estimated_cost)]
            logger.info(f"📉 Reduced to {len(videos)} videos to stay under budget")
        
        # Process videos sequentially (cloud processing doesn't need parallelism)
        results = {
            "processed": 0,
            "skipped": 0, 
            "failed": 0,
            "videos": [],
            "total_cost": 0.0
        }
        
        for i, video in enumerate(videos, 1):
            video_id = video['video_id']
            video_title = video['title']
            
            logger.info(f"🎯 Processing {i}/{len(videos)}: {video_id}")
            
            # Cost protection check
            if self.total_cost >= max_cost_usd:
                logger.warning(f"⛔ Stopping - cost limit reached: ${self.total_cost:.4f}")
                break
            
            try:
                result = process_video_with_api_whisper(video_id, video_title, self.config)
                
                if result.get('success'):
                    if result.get('skipped'):
                        results['skipped'] += 1
                        logger.info(f"⏭️ Skipped {video_id}: {result.get('reason', 'unknown')}")
                    else:
                        results['processed'] += 1
                        cost = result.get('cost_usd', 0.0)
                        self.total_cost += cost
                        results['total_cost'] += cost
                        logger.info(f"✅ Completed {video_id} - cost: ${cost:.4f}")
                else:
                    results['failed'] += 1
                    logger.error(f"❌ Failed {video_id}: {result.get('error', 'unknown')}")
                
                results['videos'].append(result)
                
            except Exception as e:
                results['failed'] += 1
                logger.error(f"💥 Exception processing {video_id}: {e}")
                results['videos'].append({
                    "video_id": video_id,
                    "success": False,
                    "error": str(e)
                })
            
            # Brief pause between videos to be respectful to APIs
            if i < len(videos):
                time.sleep(2)
        
        processing_time = time.time() - start_time
        results['processing_time'] = processing_time
        
        logger.info(f"🏁 Daily ingestion complete:")
        logger.info(f"   Processed: {results['processed']}")
        logger.info(f"   Skipped: {results['skipped']}")
        logger.info(f"   Failed: {results['failed']}")
        logger.info(f"   Total cost: ${results['total_cost']:.4f}")
        logger.info(f"   Time: {processing_time:.1f}s")
        
        return results

def main():
    """Main entry point for daily cron job"""
    parser = argparse.ArgumentParser(description="Cloud Daily YouTube Ingestion")
    parser.add_argument('--max-cost', type=float, default=5.0,
                       help='Maximum cost in USD per run (default: $5.00)')
    parser.add_argument('--limit', type=int, default=10,
                       help='Maximum number of videos to process (default: 10)')
    parser.add_argument('--days-back', type=int, default=3,
                       help='Days back to check for new videos (default: 3)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without actually processing')
    
    args = parser.parse_args()
    
    # Validate environment
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        logger.error("❌ OPENAI_API_KEY environment variable required")
        sys.exit(1)
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("❌ DATABASE_URL environment variable required")
        sys.exit(1)
    
    # Configure cloud processing
    config = CloudProcessingConfig(
        openai_api_key=openai_api_key,
        max_file_size_mb=25,
        cost_per_minute=0.006,
        max_duration_minutes=120,
        processing_method="api_whisper"
    )
    
    orchestrator = CloudDailyIngestionOrchestrator(config)
    
    if args.dry_run:
        logger.info("🔍 DRY RUN - showing what would be processed")
        videos = orchestrator.get_recent_videos(days_back=args.days_back, limit=args.limit)
        estimated_cost = orchestrator.estimate_total_cost(videos)
        
        print(f"\n📋 WOULD PROCESS:")
        for video in videos[:10]:  # Show first 10
            print(f"  - {video['video_id']}: {video['title']}")
        
        if len(videos) > 10:
            print(f"  ... and {len(videos) - 10} more")
        
        print(f"\n💰 Estimated cost: ${estimated_cost:.4f}")
        print(f"🚨 Max cost limit: ${args.max_cost:.2f}")
        
        if estimated_cost > args.max_cost:
            print(f"⚠️  Would exceed cost limit - processing would be reduced")
    else:
        # Run actual processing
        results = orchestrator.process_daily_videos(
            max_cost_usd=args.max_cost,
            limit=args.limit
        )
        
        # Log summary for monitoring
        logger.info(f"📊 DAILY SUMMARY: "
                   f"processed={results['processed']}, "
                   f"skipped={results['skipped']}, "
                   f"failed={results['failed']}, "
                   f"cost=${results['total_cost']:.4f}")

if __name__ == "__main__":
    main()
