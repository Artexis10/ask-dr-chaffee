#!/usr/bin/env python3
"""
Test script for large-scale batch ingestion.

This script performs a controlled test of the batch ingestion pipeline
with a configurable number of videos, providing detailed metrics and
performance analysis.
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import concurrent.futures
import random
import traceback

import tqdm
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.list_videos_api import YouTubeAPILister
from scripts.common.database_upsert import DatabaseUpserter
from scripts.batch_ingestion import BatchIngestionManager, IngestionConfig
from scripts.common.monitoring import IngestionMonitor

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('batch_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class BatchTestRunner:
    """Run controlled tests of the batch ingestion pipeline"""
    
    def __init__(
        self, 
        config: IngestionConfig,
        test_size: int = 100,
        batch_size: int = 20,
        checkpoint_file: str = 'test_checkpoint.json',
        log_dir: str = 'test_logs'
    ):
        self.config = config
        self.test_size = test_size
        self.batch_size = batch_size
        self.checkpoint_file = checkpoint_file
        self.log_dir = log_dir
        
        # Initialize components
        self.db = DatabaseUpserter(config.db_url)
        self.monitor = IngestionMonitor(config.db_url, log_dir=log_dir)
        
        # Initialize video lister based on source
        if config.source == 'api':
            if not config.youtube_api_key:
                raise ValueError("YouTube API key required for API source")
            self.video_lister = YouTubeAPILister(config.youtube_api_key, config.db_url)
        else:
            raise ValueError(f"Only API source supported for testing")
    
    def run_test(self):
        """Run the batch ingestion test"""
        start_time = datetime.now()
        logger.info(f"🧪 Starting batch ingestion test with {self.test_size} videos")
        
        try:
            # Get initial database stats
            initial_stats = self.db.get_ingestion_stats()
            logger.info(f"Initial database state: {initial_stats['total_videos']} videos, {initial_stats['total_chunks']} chunks")
            
            # List videos from channel
            all_videos = self.video_lister.list_channel_videos(
                self.config.channel_url,
                max_results=self.test_size * 2,  # Get more than we need to allow for filtering
                newest_first=self.config.newest_first,
                skip_live=self.config.skip_live,
                skip_upcoming=self.config.skip_upcoming,
                skip_members_only=self.config.skip_members_only
            )
            
            # Apply filters
            if self.config.skip_shorts:
                all_videos = [v for v in all_videos if not v.duration_s or v.duration_s >= 120]
            
            # Select test videos (prioritize videos not already in the database)
            test_videos = []
            for video in all_videos:
                state = self.db.get_ingest_state(video.video_id)
                if not state:
                    test_videos.append(video)
                    if len(test_videos) >= self.test_size:
                        break
            
            # If we don't have enough new videos, include some already processed ones
            if len(test_videos) < self.test_size:
                logger.info(f"Only found {len(test_videos)} new videos, adding some existing ones to reach {self.test_size}")
                remaining = self.test_size - len(test_videos)
                existing_videos = [v for v in all_videos if v not in test_videos][:remaining]
                test_videos.extend(existing_videos)
            
            # Limit to test size
            test_videos = test_videos[:self.test_size]
            logger.info(f"Selected {len(test_videos)} videos for testing")
            
            # Create batch manager
            batch_manager = BatchIngestionManager(
                config=self.config,
                batch_size=self.batch_size,
                checkpoint_file=self.checkpoint_file
            )
            
            # Run the test
            test_start = time.time()
            batch_manager.run()
            test_duration = time.time() - test_start
            
            # Get final stats
            final_stats = self.db.get_ingestion_stats()
            
            # Generate test report
            report = self._generate_test_report(
                initial_stats=initial_stats,
                final_stats=final_stats,
                test_duration=test_duration,
                test_videos=test_videos
            )
            
            # Save report
            report_file = os.path.join(self.log_dir, f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            os.makedirs(os.path.dirname(report_file), exist_ok=True)
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
            
            logger.info(f"Test report saved to {report_file}")
            
            # Print summary
            self._print_test_summary(report)
            
            return report
            
        except Exception as e:
            logger.error(f"Test error: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            # Log final statistics
            end_time = datetime.now()
            duration = end_time - start_time
            logger.info(f"Test completed in {duration}")
    
    def _generate_test_report(self, initial_stats, final_stats, test_duration, test_videos):
        """Generate comprehensive test report"""
        # Calculate changes
        videos_added = final_stats['total_videos'] - initial_stats['total_videos']
        chunks_added = final_stats['total_chunks'] - initial_stats['total_chunks']
        
        # Calculate processing rates
        videos_per_hour = (videos_added / test_duration) * 3600
        chunks_per_hour = (chunks_added / test_duration) * 3600
        seconds_per_video = test_duration / videos_added if videos_added > 0 else 0
        
        # Get error information
        error_count = final_stats['status_counts'].get('error', 0) - initial_stats['status_counts'].get('error', 0)
        success_rate = ((videos_added - error_count) / videos_added) * 100 if videos_added > 0 else 0
        
        # Get transcript source breakdown
        youtube_transcripts = 0
        whisper_transcripts = 0
        
        for video in test_videos:
            state = self.db.get_ingest_state(video.video_id)
            if state:
                if state.get('has_yt_transcript'):
                    youtube_transcripts += 1
                elif state.get('has_whisper'):
                    whisper_transcripts += 1
        
        # Calculate estimated time for full channel
        channel_size = 500  # Estimate for a medium-sized channel
        estimated_full_hours = (channel_size / videos_per_hour) if videos_per_hour > 0 else 0
        
        # Generate report
        report = {
            "test_config": {
                "test_size": self.test_size,
                "batch_size": self.batch_size,
                "source": self.config.source,
                "concurrency": self.config.concurrency,
                "skip_shorts": self.config.skip_shorts,
                "whisper_model": self.config.whisper_model
            },
            "performance": {
                "test_duration_seconds": test_duration,
                "test_duration_formatted": str(timedelta(seconds=int(test_duration))),
                "videos_processed": videos_added,
                "chunks_created": chunks_added,
                "videos_per_hour": round(videos_per_hour, 2),
                "chunks_per_hour": round(chunks_per_hour, 2),
                "seconds_per_video": round(seconds_per_video, 2),
                "estimated_full_channel_hours": round(estimated_full_hours, 2)
            },
            "quality": {
                "success_rate": round(success_rate, 2),
                "error_count": error_count,
                "youtube_transcripts": youtube_transcripts,
                "whisper_transcripts": whisper_transcripts,
                "youtube_transcript_percent": round((youtube_transcripts / videos_added) * 100, 2) if videos_added > 0 else 0,
                "whisper_transcript_percent": round((whisper_transcripts / videos_added) * 100, 2) if videos_added > 0 else 0
            },
            "initial_stats": initial_stats,
            "final_stats": final_stats,
            "timestamp": datetime.now().isoformat()
        }
        
        return report
    
    def _print_test_summary(self, report):
        """Print test summary to console"""
        print("\n" + "="*50)
        print(f"BATCH INGESTION TEST SUMMARY")
        print("="*50)
        
        print(f"\nTest Configuration:")
        print(f"  Test size: {report['test_config']['test_size']} videos")
        print(f"  Batch size: {report['test_config']['batch_size']} videos")
        print(f"  Source: {report['test_config']['source']}")
        print(f"  Concurrency: {report['test_config']['concurrency']} workers")
        
        print(f"\nPerformance Metrics:")
        print(f"  Test duration: {report['performance']['test_duration_formatted']}")
        print(f"  Videos processed: {report['performance']['videos_processed']}")
        print(f"  Chunks created: {report['performance']['chunks_created']}")
        print(f"  Processing rate: {report['performance']['videos_per_hour']} videos/hour")
        print(f"  Average time per video: {report['performance']['seconds_per_video']} seconds")
        
        print(f"\nQuality Metrics:")
        print(f"  Success rate: {report['quality']['success_rate']}%")
        print(f"  Error count: {report['quality']['error_count']}")
        print(f"  YouTube transcripts: {report['quality']['youtube_transcripts']} ({report['quality']['youtube_transcript_percent']}%)")
        print(f"  Whisper transcripts: {report['quality']['whisper_transcripts']} ({report['quality']['whisper_transcript_percent']}%)")
        
        print(f"\nEstimated Full Channel Processing:")
        print(f"  Estimated time for 500 videos: {report['performance']['estimated_full_channel_hours']} hours")
        
        print("\nRecommendations:")
        if report['performance']['videos_per_hour'] < 10:
            print("  ⚠️ Processing rate is low. Consider increasing concurrency or optimizing pipeline.")
        else:
            print("  ✅ Processing rate is good.")
            
        if report['quality']['success_rate'] < 90:
            print("  ⚠️ Success rate is below 90%. Review error patterns.")
        else:
            print("  ✅ Success rate is good.")
            
        if report['quality']['youtube_transcript_percent'] < 70:
            print("  ⚠️ Low YouTube transcript availability. Whisper fallback is being used frequently.")
        else:
            print("  ✅ YouTube transcript availability is good.")
        
        print("\n" + "="*50)

def parse_args() -> Tuple[IngestionConfig, int, int]:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Test batch ingestion with a large number of videos',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Test configuration
    parser.add_argument('--test-size', type=int, default=100,
                       help='Number of videos to process in the test (default: 100)')
    parser.add_argument('--batch-size', type=int, default=20,
                       help='Number of videos per batch (default: 20)')
    parser.add_argument('--checkpoint-file', default='test_checkpoint.json',
                       help='Checkpoint file path (default: test_checkpoint.json)')
    parser.add_argument('--log-dir', default='test_logs',
                       help='Log directory (default: test_logs)')
    
    # Source configuration
    parser.add_argument('--channel-url',
                       help='YouTube channel URL (default: env YOUTUBE_CHANNEL_URL)')
    
    # Processing configuration
    parser.add_argument('--concurrency', type=int, default=4,
                       help='Concurrent workers for processing (default: 4)')
    parser.add_argument('--skip-shorts', action='store_true',
                       help='Skip videos shorter than 120 seconds')
    parser.add_argument('--newest-first', action='store_true', default=True,
                       help='Process newest videos first (default: true)')
    
    # Content filtering options
    parser.add_argument('--include-live', action='store_false', dest='skip_live',
                       help='Include live streams (skipped by default)')
    parser.add_argument('--include-upcoming', action='store_false', dest='skip_upcoming',
                       help='Include upcoming streams (skipped by default)')
    parser.add_argument('--include-members-only', action='store_false', dest='skip_members_only',
                       help='Include members-only content (skipped by default)')
    
    # Whisper configuration
    parser.add_argument('--whisper-model', default='small.en',
                       choices=['tiny.en', 'base.en', 'small.en', 'medium.en', 'large-v3'],
                       help='Whisper model size (default: small.en)')
    parser.add_argument('--max-duration', type=int,
                       help='Skip videos longer than N seconds for Whisper fallback')
    parser.add_argument('--force-whisper', action='store_true',
                       help='Use Whisper even when YouTube transcript available')
    parser.add_argument('--ffmpeg-path', 
                       help='Path to ffmpeg executable for audio processing')
    
    # Database configuration
    parser.add_argument('--db-url',
                       help='Database URL (default: env DATABASE_URL)')
    
    # API configuration
    parser.add_argument('--youtube-api-key',
                       help='YouTube Data API key (default: env YOUTUBE_API_KEY)')
    
    # Debug options
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create config
    config = IngestionConfig(
        source='api',  # Only API source supported for testing
        channel_url=args.channel_url,
        concurrency=args.concurrency,
        skip_shorts=args.skip_shorts,
        newest_first=args.newest_first,
        whisper_model=args.whisper_model,
        max_duration=args.max_duration,
        force_whisper=args.force_whisper,
        db_url=args.db_url,
        youtube_api_key=args.youtube_api_key,
        # Content filtering options
        skip_live=args.skip_live,
        skip_upcoming=args.skip_upcoming,
        skip_members_only=args.skip_members_only
    )
    
    # Add batch-specific attributes
    setattr(config, 'batch_delay_seconds', 10)  # Shorter delay for testing
    setattr(config, 'retry_failed', True)
    
    return config, args.test_size, args.batch_size, args.checkpoint_file, args.log_dir

def main():
    """Main entry point"""
    try:
        config, test_size, batch_size, checkpoint_file, log_dir = parse_args()
        
        # Create and run test
        test_runner = BatchTestRunner(
            config=config,
            test_size=test_size,
            batch_size=batch_size,
            checkpoint_file=checkpoint_file,
            log_dir=log_dir
        )
        test_runner.run_test()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
