#!/usr/bin/env python3
"""
Hybrid Orchestrator - Smart routing between local GPU and cloud API processing
Optimizes for quality, cost, and processing speed based on environment
"""

import os
import sys
import logging
import argparse
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

# Add parent directories to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - HYBRID - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProcessingMode(Enum):
    LOCAL_GPU = "local_gpu"
    CLOUD_API = "cloud_api"
    AUTO = "auto"

@dataclass
class HybridConfig:
    """Configuration for hybrid processing strategy"""
    processing_mode: ProcessingMode = ProcessingMode.AUTO
    max_api_cost_per_session: float = 10.0
    prefer_local_for_backlog: bool = True
    api_cost_per_minute: float = 0.006
    local_gpu_available: bool = True
    openai_api_key: Optional[str] = None
    
    # Quality preferences
    prefer_whisper_over_auto: bool = True
    skip_members_only: bool = True
    
    # Performance tuning
    local_workers: int = 8
    api_batch_size: int = 5

class HybridIngestionOrchestrator:
    """Smart orchestrator that chooses optimal processing strategy"""
    
    def __init__(self, config: HybridConfig):
        self.config = config
        self.session_api_cost = 0.0
        
    def analyze_processing_context(self, videos: List[Dict]) -> Dict[str, Any]:
        """Analyze videos and environment to determine optimal processing strategy"""
        
        context = {
            "video_count": len(videos),
            "estimated_hours": 0.0,
            "has_gpu": self.config.local_gpu_available,
            "has_api_key": bool(self.config.openai_api_key),
            "recommended_mode": ProcessingMode.AUTO
        }
        
        # Estimate total processing time
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            cursor = conn.cursor()
            
            total_duration = 0
            for video in videos[:10]:  # Sample first 10 for estimation
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
                    duration = 1800
                
                total_duration += duration
            
            cursor.close()
            conn.close()
            
            # Extrapolate to all videos
            context['estimated_hours'] = (total_duration * len(videos) / len(videos[:10])) / 3600
            
        except Exception:
            # Conservative estimate: 30 min per video
            context['estimated_hours'] = len(videos) * 0.5
        
        # Calculate costs
        context['estimated_api_cost'] = context['estimated_hours'] * 60 * self.config.api_cost_per_minute
        context['local_gpu_time_hours'] = context['estimated_hours'] / max(self.config.local_workers, 1)
        
        # Determine recommendation
        if context['video_count'] <= 5:
            context['recommended_mode'] = ProcessingMode.CLOUD_API
            context['reason'] = "Small batch - API is cost-effective"
        elif context['estimated_api_cost'] > self.config.max_api_cost_per_session:
            context['recommended_mode'] = ProcessingMode.LOCAL_GPU
            context['reason'] = f"Large batch - API cost ${context['estimated_api_cost']:.2f} exceeds limit"
        elif not context['has_gpu']:
            context['recommended_mode'] = ProcessingMode.CLOUD_API
            context['reason'] = "No local GPU available"
        elif not context['has_api_key']:
            context['recommended_mode'] = ProcessingMode.LOCAL_GPU
            context['reason'] = "No OpenAI API key configured"
        else:
            # Auto-decision based on efficiency
            if self.config.prefer_local_for_backlog and context['video_count'] > 10:
                context['recommended_mode'] = ProcessingMode.LOCAL_GPU
                context['reason'] = "Backlog processing - local GPU more efficient"
            else:
                context['recommended_mode'] = ProcessingMode.CLOUD_API
                context['reason'] = "Daily processing - API suitable"
        
        return context
    
    def get_videos_to_process(self, limit: Optional[int] = None, days_back: int = 7) -> List[Dict]:
        """Get videos that need processing"""
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            cursor = conn.cursor()
            
            # Get unprocessed videos, excluding those processed locally if running in cloud mode
            base_query = """
                SELECT video_id, title, created_at 
                FROM ingest_state 
                WHERE status != 'done'
                AND created_at >= NOW() - INTERVAL '%s days'
            """
            
            params = [days_back]
            
            if limit:
                base_query += " LIMIT %s"
                params.append(limit)
            
            cursor.execute(base_query, params)
            results = cursor.fetchall()
            
            videos = [
                {
                    "video_id": row[0], 
                    "title": row[1],
                    "created_at": row[2]
                } 
                for row in results
            ]
            
            cursor.close()
            conn.close()
            
            return videos
            
        except Exception as e:
            logger.error(f"❌ Failed to get videos: {e}")
            return []
    
    def process_with_local_gpu(self, videos: List[Dict]) -> Dict[str, Any]:
        """Process videos using local GPU parallel workers"""
        logger.info(f"🚀 Processing {len(videos)} videos with local GPU ({self.config.local_workers} workers)")
        
        try:
            from parallel_ingestion_orchestrator import ParallelIngestionOrchestrator
            
            # Convert to VideoInfo format
            from scripts.common.list_videos_yt_dlp import VideoInfo
            video_infos = []
            
            for video in videos:
                video_info = VideoInfo(
                    video_id=video['video_id'],
                    title=video['title'],
                    published_at=None,
                    duration_s=None
                )
                video_infos.append(video_info)
            
            # Use existing parallel orchestrator
            orchestrator = ParallelIngestionOrchestrator(
                num_workers=self.config.local_workers,
                skip_members_only=self.config.skip_members_only
            )
            
            # Mark videos as local_gpu processing method
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            cursor = conn.cursor()
            
            for video in videos:
                cursor.execute(
                    "UPDATE ingest_state SET processing_method = 'local_gpu' WHERE video_id = %s",
                    (video['video_id'],)
                )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            # Process with parallel workers
            return orchestrator.run_parallel_processing_from_videos(video_infos)
            
        except Exception as e:
            logger.error(f"❌ Local GPU processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    def process_with_cloud_api(self, videos: List[Dict]) -> Dict[str, Any]:
        """Process videos using cloud API"""
        logger.info(f"☁️ Processing {len(videos)} videos with OpenAI API")
        
        try:
            from cloud_whisper_worker import CloudProcessingConfig, process_video_with_api_whisper
            
            config = CloudProcessingConfig(
                openai_api_key=self.config.openai_api_key,
                processing_method="api_whisper"
            )
            
            results = {
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "total_cost": 0.0,
                "videos": []
            }
            
            for video in videos:
                # Cost protection
                if self.session_api_cost >= self.config.max_api_cost_per_session:
                    logger.warning(f"⛔ Cost limit reached: ${self.session_api_cost:.4f}")
                    break
                
                result = process_video_with_api_whisper(
                    video['video_id'], 
                    video['title'], 
                    config
                )
                
                if result.get('success'):
                    if result.get('skipped'):
                        results['skipped'] += 1
                    else:
                        results['processed'] += 1
                        cost = result.get('cost_usd', 0.0)
                        results['total_cost'] += cost
                        self.session_api_cost += cost
                else:
                    results['failed'] += 1
                
                results['videos'].append(result)
                
                # Brief pause between API calls
                time.sleep(1)
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Cloud API processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    def run_hybrid_processing(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Main hybrid processing orchestration"""
        start_time = time.time()
        
        logger.info(f"🎯 Starting hybrid ingestion (mode: {self.config.processing_mode.value})")
        
        # Get videos to process
        videos = self.get_videos_to_process(limit=limit)
        
        if not videos:
            logger.info("✅ No videos to process")
            return {
                "videos_processed": 0,
                "processing_mode": "none",
                "processing_time": time.time() - start_time
            }
        
        # Analyze processing context
        context = self.analyze_processing_context(videos)
        
        logger.info(f"📊 Processing context:")
        logger.info(f"   Videos: {context['video_count']}")
        logger.info(f"   Estimated time: {context['estimated_hours']:.1f} hours")
        logger.info(f"   Estimated API cost: ${context['estimated_api_cost']:.4f}")
        logger.info(f"   Recommended: {context['recommended_mode'].value}")
        logger.info(f"   Reason: {context['reason']}")
        
        # Choose processing mode
        if self.config.processing_mode == ProcessingMode.AUTO:
            chosen_mode = context['recommended_mode']
        else:
            chosen_mode = self.config.processing_mode
        
        logger.info(f"🎯 Using processing mode: {chosen_mode.value}")
        
        # Execute processing
        if chosen_mode == ProcessingMode.LOCAL_GPU:
            results = self.process_with_local_gpu(videos)
        elif chosen_mode == ProcessingMode.CLOUD_API:
            results = self.process_with_cloud_api(videos)
        else:
            raise ValueError(f"Unsupported processing mode: {chosen_mode}")
        
        # Add context to results
        results['processing_mode'] = chosen_mode.value
        results['context'] = context
        results['total_processing_time'] = time.time() - start_time
        
        return results

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Hybrid YouTube Ingestion Orchestrator")
    parser.add_argument('--mode', choices=['auto', 'local', 'cloud'], default='auto',
                       help='Processing mode (default: auto)')
    parser.add_argument('--limit', type=int,
                       help='Maximum number of videos to process')
    parser.add_argument('--max-cost', type=float, default=10.0,
                       help='Maximum API cost per session (default: $10.00)')
    parser.add_argument('--workers', type=int, default=8,
                       help='Number of local GPU workers (default: 8)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Analyze and show recommendations without processing')
    
    args = parser.parse_args()
    
    # Map mode arguments
    mode_map = {
        'auto': ProcessingMode.AUTO,
        'local': ProcessingMode.LOCAL_GPU,
        'cloud': ProcessingMode.CLOUD_API
    }
    
    # Check GPU availability (simple NVIDIA-SMI check)
    gpu_available = False
    try:
        import subprocess
        result = subprocess.run(['nvidia-smi'], capture_output=True, timeout=5)
        gpu_available = result.returncode == 0
    except:
        pass
    
    # Configure hybrid processing
    config = HybridConfig(
        processing_mode=mode_map[args.mode],
        max_api_cost_per_session=args.max_cost,
        local_gpu_available=gpu_available,
        openai_api_key=os.getenv('OPENAI_API_KEY'),
        local_workers=args.workers
    )
    
    orchestrator = HybridIngestionOrchestrator(config)
    
    if args.dry_run:
        logger.info("🔍 DRY RUN - analyzing processing context")
        videos = orchestrator.get_videos_to_process(limit=args.limit)
        context = orchestrator.analyze_processing_context(videos)
        
        print(f"\n📋 ANALYSIS RESULTS:")
        print(f"   Videos to process: {context['video_count']}")
        print(f"   Estimated duration: {context['estimated_hours']:.1f} hours")
        print(f"   Estimated API cost: ${context['estimated_api_cost']:.4f}")
        print(f"   GPU available: {context['has_gpu']}")
        print(f"   API key configured: {context['has_api_key']}")
        print(f"   Recommended mode: {context['recommended_mode'].value}")
        print(f"   Reason: {context['reason']}")
        
        if context['recommended_mode'] == ProcessingMode.LOCAL_GPU:
            print(f"   Local processing time: {context['local_gpu_time_hours']:.1f} hours ({config.local_workers} workers)")
        
    else:
        # Run actual processing
        results = orchestrator.run_hybrid_processing(limit=args.limit)
        
        logger.info(f"🏁 Hybrid processing complete:")
        logger.info(f"   Mode: {results['processing_mode']}")
        logger.info(f"   Processed: {results.get('processed', 0)}")
        logger.info(f"   Total time: {results['total_processing_time']:.1f}s")
        
        if 'total_cost' in results:
            logger.info(f"   Total cost: ${results['total_cost']:.4f}")

if __name__ == "__main__":
    main()
