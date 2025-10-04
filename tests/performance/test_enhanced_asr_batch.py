#!/usr/bin/env python3
"""
Test Enhanced ASR Batch with Medium Model
Simple test version to verify the pipeline works with 1-2 videos
"""

import os
import sys
import time
import logging
from pathlib import Path

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
from backend.scripts.common.database_upsert import DatabaseUpserter, ChunkData
from backend.scripts.common.embeddings import EmbeddingGenerator
from backend.scripts.common.transcript_processor import TranscriptProcessor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_enhanced_asr_video(video_id: str, worker_id: int = 0):
    """Test Enhanced ASR processing for a single video"""
    
    logger.info(f"Worker {worker_id}: Testing Enhanced ASR on {video_id}")
    start_time = time.time()
    
    try:
        # Initialize Enhanced ASR components
        logger.info(f"Worker {worker_id}: Initializing Enhanced ASR pipeline")
        
        transcript_fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=True,
            voices_dir="voices",
            chaffee_min_sim=0.62,  # Conservative threshold
            api_key=os.getenv('YOUTUBE_API_KEY'),
            ffmpeg_path=os.getenv('FFMPEG_PATH')
        )
        
        processor = TranscriptProcessor()
        embedding_generator = EmbeddingGenerator()
        upserter = DatabaseUpserter(db_url=os.getenv('DATABASE_URL'))
        
        logger.info(f"Worker {worker_id}: Enhanced ASR pipeline initialized")
        
        # Step 1: Enhanced ASR transcription with speaker identification
        logger.info(f"Worker {worker_id}: Starting Enhanced ASR transcription")
        
        segments, method, metadata = transcript_fetcher.fetch_transcript_with_speaker_id(
            video_id,
            force_enhanced_asr=True,  # Force Enhanced ASR for testing
            cleanup_audio=True
        )
        
        if not segments:
            logger.error(f"Worker {worker_id}: No segments generated for {video_id}")
            return {"success": False, "error": "No segments"}
        
        transcript_time = time.time() - start_time
        logger.info(f"Worker {worker_id}: Got {len(segments)} segments via {method} in {transcript_time:.1f}s")
        
        # Step 2: Process segments into chunks
        logger.info(f"Worker {worker_id}: Processing segments into chunks")
        chunks = processor.process_segments(segments, chunk_duration_seconds=45, overlap_seconds=10)
        
        # Step 3: Generate embeddings
        logger.info(f"Worker {worker_id}: Generating embeddings for {len(chunks)} chunks")
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = embedding_generator.generate_batch(chunk_texts)
        
        # Step 4: Create chunk data with metadata
        chunk_data_list = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_data = ChunkData(
                source_id=video_id,
                source_type="youtube",
                title=f"Test Video {video_id}",
                description="Test video for Enhanced ASR batch processing",
                chunk_index=i,
                start_time_seconds=chunk.start_time_seconds,
                end_time_seconds=chunk.end_time_seconds,
                text=chunk.text,
                embedding=embedding,
                word_count=len(chunk.text.split()),
                url=f"https://www.youtube.com/watch?v={video_id}",
                published_at=None,
                duration_seconds=None,
                metadata={
                    "transcript_method": method,
                    "enhanced_asr": True,
                    "speaker_identification": True,
                    "chaffee_threshold": 0.62,
                    "processing_time": time.time() - start_time,
                    "transcript_time": transcript_time,
                    "worker_id": worker_id,
                    "whisper_model": "medium",
                    "test_mode": True,
                    **metadata
                }
            )
            chunk_data_list.append(chunk_data)
        
        # Step 5: Upsert to database
        logger.info(f"Worker {worker_id}: Upserting {len(chunk_data_list)} chunks to database")
        upserter.upsert_chunks(chunk_data_list)
        
        total_time = time.time() - start_time
        
        # Extract speaker statistics
        speaker_stats = metadata.get('speaker_distribution', {})
        chaffee_percentage = speaker_stats.get('Chaffee', 0.0) * 100
        
        result = {
            "success": True,
            "video_id": video_id,
            "chunks": len(chunk_data_list),
            "processing_time": total_time,
            "method": method,
            "worker_id": worker_id,
            "chaffee_percentage": chaffee_percentage,
            "speaker_stats": speaker_stats,
            "enhanced_asr": True
        }
        
        logger.info(f"Worker {worker_id}: SUCCESS!")
        logger.info(f"  - Video: {video_id}")
        logger.info(f"  - Chunks: {len(chunk_data_list)}")
        logger.info(f"  - Processing time: {total_time:.1f}s")
        logger.info(f"  - Method: {method}")
        logger.info(f"  - Dr. Chaffee attribution: {chaffee_percentage:.1f}%")
        logger.info(f"  - Speaker stats: {speaker_stats}")
        
        return result
        
    except Exception as e:
        logger.error(f"Worker {worker_id}: ERROR processing {video_id}: {e}")
        import traceback
        logger.error(f"Worker {worker_id}: Traceback: {traceback.format_exc()}")
        return {"success": False, "video_id": video_id, "error": str(e)}

def main():
    logger.info("Enhanced ASR Batch Test Starting")
    logger.info("=" * 50)
    
    # Test videos (using ones we know exist)
    test_video_ids = ["QLenO7DM7Cw", "HwbPIsGL5CE"]  # First 2 from current batch
    
    logger.info(f"Testing Enhanced ASR on {len(test_video_ids)} videos:")
    for i, video_id in enumerate(test_video_ids):
        logger.info(f"  {i+1}. {video_id}")
    
    # Process each video
    results = []
    start_time = time.time()
    
    for i, video_id in enumerate(test_video_ids):
        logger.info(f"\nProcessing video {i+1}/{len(test_video_ids)}: {video_id}")
        result = test_enhanced_asr_video(video_id, worker_id=i)
        results.append(result)
    
    # Summary
    total_time = time.time() - start_time
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    
    logger.info(f"\nTest Complete!")
    logger.info(f"=" * 50)
    logger.info(f"Results: {len(successful)} successful, {len(failed)} failed")
    logger.info(f"Total time: {total_time:.1f}s")
    
    if successful:
        total_chunks = sum(r.get("chunks", 0) for r in successful)
        avg_chaffee = sum(r.get("chaffee_percentage", 0) for r in successful) / len(successful)
        logger.info(f"Total chunks: {total_chunks}")
        logger.info(f"Average Dr. Chaffee attribution: {avg_chaffee:.1f}%")
        logger.info(f"Throughput: {len(successful)/(total_time/60):.1f} videos/minute")
    
    if failed:
        logger.error(f"Failed videos:")
        for result in failed:
            logger.error(f"  - {result.get('video_id', 'Unknown')}: {result.get('error', 'Unknown error')}")
    
    logger.info(f"\nReady for overnight batch processing!")

if __name__ == "__main__":
    main()
