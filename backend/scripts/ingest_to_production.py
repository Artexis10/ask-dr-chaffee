#!/usr/bin/env python3
"""
Production Ingestion Script - RTX 5080 → Cloud Database
Processes videos locally and uploads directly to production database
"""

import os
import sys
import asyncio
import logging
import time
import json
from typing import List, Dict, Any
from datetime import datetime
import asyncpg
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from scripts.common.transcript_fetch import TranscriptFetcher, TranscriptSegment  
from scripts.common.embeddings import EmbeddingGenerator
from scripts.common.transcript_processor import TranscriptProcessor

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('production_ingestion.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class ProductionIngestionNode:
    """Local RTX 5080 processing node that feeds production database"""
    
    def __init__(self):
        self.transcript_fetcher = TranscriptFetcher()
        self.embedding_generator = EmbeddingGenerator()
        self.transcript_processor = TranscriptProcessor()
        self.production_db_url = os.getenv('PRODUCTION_DATABASE_URL')
        
        # Production settings
        self.batch_size = 10
        self.max_concurrent = 3
        self.upload_batch_size = 50
        
        # Progress tracking
        self.start_time = time.time()
        self.processed_count = 0
        self.total_chunks = 0
        self.errors = []
        
        if not self.production_db_url:
            raise ValueError("PRODUCTION_DATABASE_URL environment variable required")
    
    async def process_channel_to_production(self, channel_url: str, limit: int = None):
        """Process entire channel and upload to production database"""
        
        logger.info("="*60)
        logger.info("PRODUCTION INGESTION - RTX 5080 → Cloud Database")
        logger.info("="*60)
        
        # Get all videos from channel
        video_lister = YtDlpVideoLister()
        logger.info(f"Fetching video list from: {channel_url}")
        
        all_videos = video_lister.list_channel_videos(channel_url)
        if limit:
            all_videos = all_videos[:limit]
        
        logger.info(f"Found {len(all_videos)} videos to process")
        
        # Process in batches
        total_batches = (len(all_videos) + self.batch_size - 1) // self.batch_size
        
        for batch_idx, batch_start in enumerate(range(0, len(all_videos), self.batch_size)):
            batch_videos = all_videos[batch_start:batch_start + self.batch_size]
            
            logger.info(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch_videos)} videos)")
            
            # Process batch
            results = await self.process_video_batch(batch_videos)
            
            # Log results
            success_count = sum(1 for r in results if r['status'] == 'success')
            error_count = len(results) - success_count
            
            logger.info(f"Batch {batch_idx + 1} complete: {success_count} success, {error_count} errors")
            
            # Update progress
            self.processed_count += len(batch_videos)
            elapsed_hours = (time.time() - self.start_time) / 3600
            rate = self.processed_count / elapsed_hours if elapsed_hours > 0 else 0
            
            remaining_videos = len(all_videos) - self.processed_count
            eta_hours = remaining_videos / rate if rate > 0 else 0
            
            logger.info(f"Overall Progress: {self.processed_count}/{len(all_videos)} ({self.processed_count/len(all_videos)*100:.1f}%)")
            logger.info(f"Processing rate: {rate:.1f} videos/hour")
            logger.info(f"Total chunks uploaded: {self.total_chunks:,}")
            logger.info(f"ETA: {eta_hours:.1f} hours")
            
            # Brief pause between batches
            await asyncio.sleep(10)
        
        logger.info("="*60)
        logger.info("PRODUCTION INGESTION COMPLETE!")
        logger.info(f"Total videos processed: {self.processed_count}")
        logger.info(f"Total chunks uploaded: {self.total_chunks:,}")
        logger.info(f"Total errors: {len(self.errors)}")
        logger.info("="*60)
    
    async def process_video_batch(self, videos: List[VideoInfo]) -> List[Dict[str, Any]]:
        """Process a batch of videos concurrently"""
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [self.process_single_video(video, semaphore) for video in videos]
        
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def process_single_video(self, video: VideoInfo, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
        """Process a single video and upload to production database"""
        
        async with semaphore:
            try:
                start_time = time.time()
                logger.info(f"Processing: {video.video_id} - {video.title[:50]}...")
                
                # Step 1: Local RTX 5080 transcription (FREE!)
                segments, method, metadata = self.transcript_fetcher.fetch_transcript(video.video_id)
                
                if not segments:
                    return {
                        "video_id": video.video_id,
                        "status": "error", 
                        "error": f"No transcript available via {method}"
                    }
                
                # Step 2: Process into chunks
                chunks = self.transcript_processor.process_transcript(
                    segments=segments,
                    video_id=video.video_id,
                    title=video.title,
                    url=f"https://www.youtube.com/watch?v={video.video_id}"
                )
                
                # Step 3: Generate embeddings locally (FREE!)
                embedded_chunks = await self.embedding_generator.generate_embeddings_for_chunks(chunks)
                
                # Step 4: Upload to production database
                await self.upload_to_production_db(video, embedded_chunks, metadata, method)
                
                processing_time = time.time() - start_time
                self.total_chunks += len(embedded_chunks)
                
                logger.info(f"✅ {video.video_id}: {len(embedded_chunks)} chunks → Production DB ({processing_time:.1f}s)")
                
                return {
                    "video_id": video.video_id,
                    "status": "success",
                    "chunks": len(embedded_chunks),
                    "method": method,
                    "processing_time": processing_time
                }
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ {video.video_id}: {error_msg}")
                self.errors.append({
                    "video_id": video.video_id,
                    "error": error_msg,
                    "timestamp": datetime.now().isoformat()
                })
                
                return {
                    "video_id": video.video_id,
                    "status": "error",
                    "error": error_msg
                }
    
    async def upload_to_production_db(self, video: VideoInfo, chunks: List, metadata: Dict, method: str):
        """Upload processed video and chunks to production database"""
        
        async with asyncpg.connect(self.production_db_url) as conn:
            # Prepare source metadata
            source_metadata = {
                "title": video.title,
                "published_at": video.published_at.isoformat() if video.published_at else None,
                "duration_s": video.duration_s,
                "view_count": video.view_count,
                "description": video.description,
                "transcription_method": method,
                "transcription_metadata": metadata,
                "processed_at": datetime.now().isoformat(),
                "processed_by": "rtx_5080_local"
            }
            
            # Insert/update source
            await conn.execute("""
                INSERT INTO sources (
                    source_id, source_type, title, url, metadata, 
                    created_at, updated_at
                ) VALUES ($1, 'youtube', $2, $3, $4, NOW(), NOW())
                ON CONFLICT (source_id) DO UPDATE SET
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
            """, video.video_id, video.title, 
                f"https://www.youtube.com/watch?v={video.video_id}",
                json.dumps(source_metadata))
            
            # Batch upload chunks
            if chunks:
                chunk_values = []
                for chunk in chunks:
                    chunk_values.append((
                        chunk.text,
                        chunk.start_time,
                        chunk.end_time,
                        chunk.timestamp_url,
                        video.video_id,
                        chunk.embedding.tolist() if hasattr(chunk, 'embedding') and chunk.embedding is not None else None
                    ))
                
                # Delete existing chunks for this video (in case of reprocessing)
                await conn.execute("DELETE FROM chunks WHERE source_id = $1", video.video_id)
                
                # Insert new chunks
                await conn.executemany("""
                    INSERT INTO chunks (
                        text, start_time, end_time, timestamp_url, 
                        source_id, embedding, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
                """, chunk_values)
                
                logger.debug(f"Uploaded {len(chunks)} chunks for {video.video_id}")

async def main():
    """Main entry point for production ingestion"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Production Ingestion - RTX 5080 to Cloud DB')
    parser.add_argument('--channel-url', default='https://www.youtube.com/@anthonychaffeemd',
                       help='YouTube channel URL')
    parser.add_argument('--limit', type=int, help='Limit number of videos to process')
    parser.add_argument('--batch-size', type=int, default=10, help='Videos per batch')
    parser.add_argument('--concurrency', type=int, default=3, help='Concurrent processing')
    
    args = parser.parse_args()
    
    # Create ingestion node
    ingestion_node = ProductionIngestionNode()
    ingestion_node.batch_size = args.batch_size
    ingestion_node.max_concurrent = args.concurrency
    
    # Check production database connection
    try:
        conn = await asyncpg.connect(ingestion_node.production_db_url)
        await conn.close()
        logger.info("✅ Production database connection verified")
    except Exception as e:
        logger.error(f"❌ Cannot connect to production database: {e}")
        return
    
    # Start processing
    await ingestion_node.process_channel_to_production(
        channel_url=args.channel_url,
        limit=args.limit
    )

if __name__ == "__main__":
    asyncio.run(main())
