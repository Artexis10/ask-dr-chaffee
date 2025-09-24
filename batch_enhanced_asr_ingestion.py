#!/usr/bin/env python3
"""
Batch Enhanced ASR Ingestion - Optimized for 50 videos/8 hours with highest quality
Uses base model with HuggingFace diarization for optimal quality/speed balance
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
from backend.scripts.common.database import DatabaseManager
from backend.scripts.common.embeddings import EmbeddingGenerator
from backend.scripts.common.database_upsert import DatabaseUpserter, ChunkData

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'batch_ingestion_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BatchEnhancedIngestion:
    """Batch ingestion with Enhanced ASR and speaker identification"""
    
    def __init__(self):
        self.fetcher = EnhancedTranscriptFetcher(speaker_id=True)
        self.db_manager = DatabaseManager()
        self.embedder = EmbeddingGenerator()
        self.upserter = DatabaseUpserter(self.db_manager, self.embedder)
        
        # Statistics tracking
        self.stats = {
            'videos_processed': 0,
            'videos_successful': 0,
            'videos_failed': 0,
            'total_duration': 0,
            'processing_time': 0,
            'start_time': time.time(),
            'failed_videos': []
        }
        
    def process_video_list(self, video_ids: List[str]) -> Dict[str, Any]:
        """Process a list of YouTube video IDs"""
        logger.info(f"Starting batch ingestion of {len(video_ids)} videos")
        logger.info(f"Enhanced ASR model: {os.getenv('WHISPER_MODEL_ENHANCED', 'base')}")
        logger.info(f"HuggingFace diarization: {'enabled' if os.getenv('USE_SIMPLE_DIARIZATION', 'false').lower() == 'false' else 'disabled'}")
        
        for i, video_id in enumerate(video_ids, 1):
            try:
                logger.info(f"\n=== Processing video {i}/{len(video_ids)}: {video_id} ===")
                self.process_single_video(video_id)
                self.stats['videos_successful'] += 1
                
                # Progress update
                elapsed = time.time() - self.stats['start_time']
                avg_time_per_video = elapsed / i
                estimated_remaining = (len(video_ids) - i) * avg_time_per_video
                
                logger.info(f"Progress: {i}/{len(video_ids)} ({i/len(video_ids)*100:.1f}%)")
                logger.info(f"Estimated time remaining: {estimated_remaining/3600:.1f} hours")
                
            except Exception as e:
                logger.error(f"Failed to process video {video_id}: {e}")
                self.stats['videos_failed'] += 1
                self.stats['failed_videos'].append({'video_id': video_id, 'error': str(e)})
            
            self.stats['videos_processed'] += 1
            
            # Brief pause to prevent overwhelming the system
            time.sleep(2)
        
        # Final statistics
        self.stats['processing_time'] = time.time() - self.stats['start_time']
        self.log_final_stats()
        
        return self.stats
    
    def process_single_video(self, video_id: str):
        """Process a single video with Enhanced ASR"""
        try:
            # Fetch transcript with speaker identification
            result = self.fetcher.fetch_transcript(video_id)
            
            if not result or 'transcript' not in result:
                raise ValueError("Failed to get transcript")
            
            transcript_data = result['transcript']
            
            # Extract video metadata
            video_title = result.get('title', f'Video {video_id}')
            video_duration = result.get('duration', 0)
            speaker_stats = result.get('speaker_distribution', {})
            
            logger.info(f"Video: {video_title}")
            logger.info(f"Duration: {video_duration:.1f}s")
            if speaker_stats:
                for speaker, percentage in speaker_stats.items():
                    logger.info(f"  {speaker}: {percentage:.1f}%")
            
            # Process transcript for database insertion
            if isinstance(transcript_data, str):
                # Simple transcript - convert to segments
                segments = [{'text': transcript_data, 'timestamp': 0}]
            else:
                # Structured transcript with segments
                segments = transcript_data
            
            # Create chunks for database
            chunks = []
            for i, segment in enumerate(segments):
                if isinstance(segment, dict):
                    text = segment.get('text', str(segment))
                    timestamp = segment.get('start', segment.get('timestamp', i * 30))
                else:
                    text = str(segment)
                    timestamp = i * 30
                
                if text.strip():
                    chunk = ChunkData(
                        content=text.strip(),
                        metadata={
                            'video_id': video_id,
                            'title': video_title,
                            'timestamp': timestamp,
                            'duration': video_duration,
                            'speaker_stats': speaker_stats,
                            'chunk_index': i,
                            'processing_method': 'enhanced_asr',
                            'diarization_enabled': True,
                            'model': os.getenv('WHISPER_MODEL_ENHANCED', 'base')
                        }
                    )
                    chunks.append(chunk)
            
            if chunks:
                # Upsert to database
                logger.info(f"Upserting {len(chunks)} chunks to database...")
                self.upserter.upsert_chunks(chunks)
                self.stats['total_duration'] += video_duration
                logger.info(f"Successfully processed {video_id}")
            else:
                raise ValueError("No valid chunks created from transcript")
                
        except Exception as e:
            logger.error(f"Error processing video {video_id}: {e}")
            raise
    
    def log_final_stats(self):
        """Log final processing statistics"""
        hours = self.stats['processing_time'] / 3600
        avg_time = self.stats['processing_time'] / max(1, self.stats['videos_processed'])
        
        logger.info("\n" + "="*60)
        logger.info("BATCH INGESTION COMPLETE")
        logger.info("="*60)
        logger.info(f"Total videos processed: {self.stats['videos_processed']}")
        logger.info(f"Successful: {self.stats['videos_successful']}")
        logger.info(f"Failed: {self.stats['videos_failed']}")
        logger.info(f"Success rate: {self.stats['videos_successful']/max(1,self.stats['videos_processed'])*100:.1f}%")
        logger.info(f"Total audio duration: {self.stats['total_duration']/3600:.1f} hours")
        logger.info(f"Processing time: {hours:.2f} hours")
        logger.info(f"Average time per video: {avg_time/60:.1f} minutes")
        logger.info(f"Processing speed: {self.stats['total_duration']/max(1,self.stats['processing_time']):.2f}x real-time")
        
        if self.stats['failed_videos']:
            logger.info("\nFailed videos:")
            for failed in self.stats['failed_videos']:
                logger.info(f"  {failed['video_id']}: {failed['error']}")
        
        # Save stats to file
        stats_file = f"ingestion_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2, default=str)
        logger.info(f"Detailed stats saved to: {stats_file}")

def load_video_list(file_path: str) -> List[str]:
    """Load video IDs from file (one per line or JSON array)"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Video list file not found: {file_path}")
    
    content = path.read_text().strip()
    
    # Try JSON first
    try:
        video_list = json.loads(content)
        if isinstance(video_list, list):
            return [str(vid).strip() for vid in video_list if str(vid).strip()]
    except json.JSONDecodeError:
        pass
    
    # Fall back to line-by-line
    video_ids = []
    for line in content.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            # Extract video ID from URL if needed
            if 'youtube.com/watch?v=' in line:
                line = line.split('v=')[1].split('&')[0]
            elif 'youtu.be/' in line:
                line = line.split('/')[-1].split('?')[0]
            video_ids.append(line)
    
    return video_ids

def main():
    parser = argparse.ArgumentParser(description='Batch Enhanced ASR Ingestion')
    parser.add_argument('video_list', help='File containing video IDs (one per line or JSON array)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed without actually doing it')
    
    args = parser.parse_args()
    
    try:
        # Load video list
        video_ids = load_video_list(args.video_list)
        logger.info(f"Loaded {len(video_ids)} videos from {args.video_list}")
        
        if args.dry_run:
            logger.info("DRY RUN - Would process these videos:")
            for i, vid in enumerate(video_ids, 1):
                logger.info(f"  {i}. {vid}")
            logger.info(f"Estimated processing time: {len(video_ids) * 9.6 / 60:.1f} hours")
            return
        
        # Process videos
        ingester = BatchEnhancedIngestion()
        stats = ingester.process_video_list(video_ids)
        
        # Exit with error code if many failures
        if stats['videos_failed'] > stats['videos_successful'] * 0.2:  # >20% failure rate
            logger.error("High failure rate detected")
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("Ingestion interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Batch ingestion failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
