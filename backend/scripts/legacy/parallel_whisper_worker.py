#!/usr/bin/env python3
"""
Dedicated Whisper Worker Process for True Parallel Processing
Each process loads its own Whisper model and processes videos independently
"""

import os
import sys
import logging
import time
from pathlib import Path

# Add parent directories to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

def setup_worker_logging(worker_id):
    """Setup logging for worker process"""
    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s - WORKER-{worker_id} - %(levelname)s - %(message)s'
    )
    return logging.getLogger(f"worker_{worker_id}")

def initialize_whisper_model(worker_id, model_size="base"):
    """Initialize dedicated Whisper model for this worker"""
    logger = logging.getLogger(f"worker_{worker_id}")
    try:
        import faster_whisper
        logger.info(f"🔥 Loading dedicated Whisper model ({model_size})")
        
        model = faster_whisper.WhisperModel(
            model_size,
            device="cuda",
            compute_type="float16"
        )
        
        logger.info(f"✅ Whisper model loaded successfully")
        return model
    except Exception as e:
        logger.error(f"❌ Failed to load Whisper model: {e}")
        return None

def process_video_with_dedicated_whisper(worker_id, video_id, video_title):
    """Process a single video with dedicated Whisper model"""
    logger = setup_worker_logging(worker_id)
    
    try:
        # Initialize components
        from scripts.common.database_upsert import DatabaseUpserter
        from scripts.common.transcript_fetch import TranscriptFetcher
        from scripts.common.embeddings import EmbeddingGenerator
        
        db_url = os.getenv('DATABASE_URL')
        db = DatabaseUpserter(db_url)
        transcript_fetcher = TranscriptFetcher()
        embedder = EmbeddingGenerator()
        
        logger.info(f"🎯 Processing {video_id} - {video_title}")
        start_time = time.time()
        
        # Check if already completed
        try:
            import psycopg2
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM ingest_state WHERE video_id = %s", (video_id,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result and result[0] == 'done':
                logger.info(f"⏭️ Already completed, skipping")
                return {"worker_id": worker_id, "video_id": video_id, "success": True, "skipped": True}
        except:
            pass
        
        # Initialize Whisper model
        whisper_model = initialize_whisper_model(worker_id)
        if not whisper_model:
            return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": "Failed to load Whisper"}
        
        # Override the transcript fetcher's Whisper method with our dedicated model
        def dedicated_whisper_transcribe(audio_path, model_name=None):
            try:
                logger.info(f"🎯 Transcribing with dedicated model")
                
                segments_iter, info = whisper_model.transcribe(
                    str(audio_path),
                    language="en",
                    beam_size=1,
                    word_timestamps=False,
                    vad_filter=False,
                    temperature=0.0,
                    no_speech_threshold=0.6
                )
                
                # Convert to transcript segments
                from scripts.common.transcript_common import TranscriptSegment
                segments = []
                
                for segment in segments_iter:
                    if len(segment.text.strip()) > 3:
                        ts = TranscriptSegment(
                            start=segment.start,
                            end=segment.end,
                            text=segment.text.strip()
                        )
                        segments.append(ts)
                
                metadata = {
                    "model": "base",
                    "worker_id": worker_id,
                    "dedicated_model": True,
                    "detected_language": info.language,
                    "duration": info.duration
                }
                
                logger.info(f"✅ Transcribed {len(segments)} segments")
                return segments, metadata
                
            except Exception as e:
                logger.error(f"❌ Transcription failed: {e}")
                return None, {"error": str(e)}
        
        # Monkey patch the transcriber to use our dedicated model
        transcript_fetcher.transcribe_with_whisper_parallel = lambda audio_path, model_name=None: dedicated_whisper_transcribe(audio_path, model_name)
        
        # Use existing infrastructure for the full pipeline
        segments, method, metadata = transcript_fetcher.fetch_transcript(video_id)
        
        if not segments:
            logger.error(f"❌ No transcript segments generated")
            return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": "No segments"}
        
        # Continue with existing pipeline - chunking, embedding, database
        from scripts.common.database_upsert import ChunkData
        
        # Create video info for database operations
        from scripts.common.list_videos_yt_dlp import VideoInfo
        video_info = VideoInfo(
            video_id=video_id,
            title=video_title,
            published_at=None,
            duration_s=None
        )
        
        # Update status
        db.upsert_ingest_state(video_id, video_info, status='pending')
        db.update_ingest_status(
            video_id, 'transcribed',
            has_yt_transcript=(method == 'youtube'),
            has_whisper=(method != 'youtube')
        )
        
        # Chunk transcript
        chunks = []
        for segment in segments:
            chunk = ChunkData.from_transcript_segment(segment, video_id)
            chunks.append(chunk)
        
        db.update_ingest_status(video_id, 'chunked', chunk_count=len(chunks))
        
        # Generate embeddings
        texts = [chunk.text for chunk in chunks]
        embeddings = embedder.generate_embeddings(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        db.update_ingest_status(video_id, 'embedded', embedding_count=len(embeddings))
        
        # Upsert to database
        source_id = db.upsert_source(video_info, source_type='youtube')
        
        for chunk in chunks:
            chunk.source_id = source_id
        
        db.upsert_chunks(chunks)
        db.update_ingest_status(video_id, 'upserted')
        db.update_ingest_status(video_id, 'done')
        
        processing_time = time.time() - start_time
        logger.info(f"✅ COMPLETED in {processing_time:.1f}s - {len(chunks)} chunks")
        
        return {
            "worker_id": worker_id,
            "video_id": video_id,
            "success": True,
            "processing_time": processing_time,
            "chunks": len(chunks),
            "method": method
        }
        
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": str(e)}

if __name__ == "__main__":
    # This allows the worker to be called as a subprocess
    import sys
    if len(sys.argv) >= 4:
        worker_id = int(sys.argv[1])
        video_id = sys.argv[2]
        video_title = sys.argv[3]
        
        result = process_video_with_dedicated_whisper(worker_id, video_id, video_title)
        print(f"RESULT: {result}")
