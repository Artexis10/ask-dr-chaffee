#!/usr/bin/env python3
"""
FIXED Dedicated Whisper Worker Process for True Parallel Processing
- Properly skips members-only videos
- Fixed YouTube Transcript API usage
- Each process loads its own Whisper model and processes videos independently
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

def check_video_access(video_id, skip_members_only=True, cookies_file=None):
    """
    Check video accessibility with configurable handling
    Returns: (accessible, reason, action)
    """
    try:
        import subprocess
        
        # Build command with optional authentication
        cmd = [
            'yt-dlp',
            f'https://www.youtube.com/watch?v={video_id}',
            '--dump-json',
            '--no-warnings'
        ]
        
        # Add authentication if provided
        username = os.getenv('YOUTUBE_USERNAME')
        password = os.getenv('YOUTUBE_PASSWORD')
        
        if cookies_file and Path(cookies_file).exists():
            cmd.extend(['--cookies', cookies_file])
        elif username and password:
            cmd.extend(['--username', username, '--password', password])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return True, "accessible", "process"
        
        error_output = result.stderr
        
        if "Join this channel to get access to members-only" in error_output:
            if skip_members_only:
                return False, "members-only", "skip"
            else:
                return False, "members-only", "requires-auth"
        
        if "Private video" in error_output:
            return False, "private", "skip"
        
        if "Video unavailable" in error_output:
            return False, "unavailable", "skip"
            
        return False, f"unknown-error", "skip"
        
    except Exception as e:
        return False, f"check-failed: {str(e)}", "skip"

def get_youtube_transcript_fixed(video_id):
    """Fixed YouTube Transcript API implementation"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from scripts.common.transcript_common import TranscriptSegment
        
        # Get available transcripts for the video
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to get English transcript
        try:
            transcript = transcript_list.find_transcript(['en'])
            transcript_data = transcript.fetch()
        except:
            # If no English, get the first available
            transcripts = list(transcript_list)
            if not transcripts:
                return None, None
            transcript_data = transcripts[0].fetch()
        
        # Convert to our format
        segments = []
        for entry in transcript_data:
            segment = TranscriptSegment(
                start=entry['start'],
                end=entry['start'] + entry['duration'],
                text=entry['text'].strip()
            )
            if len(segment.text) > 3:  # Filter out very short segments
                segments.append(segment)
        
        metadata = {
            "method": "youtube_transcript_api",
            "language": "en",
            "segment_count": len(segments)
        }
        
        return segments, metadata
        
    except Exception as e:
        return None, {"error": str(e)}

def process_video_with_dedicated_whisper(worker_id, video_id, video_title, skip_members_only=True, cookies_file=None):
    """Process a single video with dedicated Whisper model - ENHANCED VERSION"""
    logger = setup_worker_logging(worker_id)
    
    try:
        # Step 1: Check video accessibility with configurable handling
        logger.info(f"🔍 Checking accessibility for {video_id}")
        accessible, reason, action = check_video_access(video_id, skip_members_only, cookies_file)
        
        if not accessible:
            if action == "skip":
                logger.info(f"⏭️ Skipping {video_id} - {reason}")
                return {"worker_id": worker_id, "video_id": video_id, "success": True, "skipped": True, "reason": reason}
            elif action == "requires-auth":
                logger.warning(f"🔑 {video_id} requires authentication ({reason}) - set cookies_file to access")
                return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": f"Authentication required: {reason}"}
        
        # Initialize components
        from scripts.common.database_upsert import DatabaseUpserter
        from scripts.common.embeddings import EmbeddingGenerator
        
        db_url = os.getenv('DATABASE_URL')
        db = DatabaseUpserter(db_url)
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
                return {"worker_id": worker_id, "video_id": video_id, "success": True, "skipped": True, "reason": "already_done"}
        except:
            pass
        
        # Initialize Whisper model
        whisper_model = initialize_whisper_model(worker_id)
        if not whisper_model:
            return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": "Failed to load Whisper"}
        
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
        
        # Step 2: Try fixed YouTube transcript first
        logger.info(f"📋 Trying YouTube transcript for {video_id}")
        segments, metadata = get_youtube_transcript_fixed(video_id)
        method = "youtube"
        
        # Step 3: If no YouTube transcript, use Whisper
        if not segments:
            logger.info(f"📥 No YouTube transcript, using Whisper for {video_id}")
            
            try:
                # Download audio using yt-dlp directly
                import subprocess
                import tempfile
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    audio_file = Path(temp_dir) / f"{video_id}.wav"
                    
                    # Download with yt-dlp
                    cmd = [
                        'yt-dlp',
                        f'https://www.youtube.com/watch?v={video_id}',
                        '-x',
                        '--audio-format', 'wav',
                        '--audio-quality', '0',
                        '-o', str(audio_file.with_suffix('.%(ext)s')),
                        '--no-playlist',
                        '--no-warnings'
                    ]
                    
                    # Add authentication for member content
                    username = os.getenv('YOUTUBE_USERNAME')
                    password = os.getenv('YOUTUBE_PASSWORD')
                    
                    if cookies_file and Path(cookies_file).exists():
                        cmd.extend(['--cookies', cookies_file])
                        logger.info(f"🔑 Using cookies authentication for download")
                    elif username and password:
                        cmd.extend(['--username', username, '--password', password])
                        logger.info(f"🔑 Using username/password authentication for download")
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                    
                    if result.returncode != 0:
                        error_msg = result.stderr
                        if "Join this channel to get access to members-only" in error_msg:
                            if skip_members_only:
                                logger.info(f"⏭️ Skipping {video_id} - members-only content detected during download")
                                return {"worker_id": worker_id, "video_id": video_id, "success": True, "skipped": True, "reason": "members-only"}
                            else:
                                logger.error(f"🔑 {video_id} needs authentication - provide cookies_file")
                                return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": "Authentication required"}
                        else:
                            raise Exception(f"yt-dlp failed: {error_msg}")
                    
                    if not audio_file.exists():
                        raise Exception("Audio file not created")
                    
                    # Transcribe with dedicated Whisper model
                    logger.info(f"🎯 Transcribing with dedicated Whisper model")
                    
                    segments_iter, info = whisper_model.transcribe(
                        str(audio_file),
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
                    
                    method = "whisper_dedicated"
                    metadata = {
                        "model": "base",
                        "worker_id": worker_id,
                        "dedicated_model": True,
                        "detected_language": info.language,
                        "language_probability": info.language_probability,
                        "duration": info.duration
                    }
                    
                    logger.info(f"✅ Transcribed {video_id} - {len(segments)} segments")
                    
            except Exception as e:
                logger.error(f"❌ Transcription failed for {video_id}: {e}")
                db.update_ingest_status(
                    video_id, 'error',
                    error=str(e),
                    increment_retries=True
                )
                return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": str(e)}
        
        if not segments:
            error = "No transcript segments generated"
            logger.error(f"❌ {error} for {video_id}")
            db.update_ingest_status(video_id, 'error', error=error, increment_retries=True)
            return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": error}
        
        # Update transcript status
        db.update_ingest_status(
            video_id, 'transcribed',
            has_yt_transcript=(method == 'youtube'),
            has_whisper=(method != 'youtube')
        )
        
        # Chunk transcript
        from scripts.common.database_upsert import ChunkData
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
        logger.info(f"✅ COMPLETED {video_id} in {processing_time:.1f}s - {len(chunks)} chunks, method: {method}")
        
        return {
            "worker_id": worker_id,
            "video_id": video_id,
            "success": True,
            "processing_time": processing_time,
            "chunks": len(chunks),
            "method": method
        }
        
    except Exception as e:
        logger.error(f"❌ FAILED {video_id}: {e}")
        return {"worker_id": worker_id, "video_id": video_id, "success": False, "error": str(e)}

if __name__ == "__main__":
    # This allows the worker to be called as a subprocess
    import sys
    if len(sys.argv) >= 4:
        worker_id = int(sys.argv[1])
        video_id = sys.argv[2]
        video_title = sys.argv[3]
        
        # Parse optional flags from environment or additional args
        skip_members_only = os.getenv('SKIP_MEMBERS_ONLY', 'true').lower() == 'true'
        cookies_file = os.getenv('YOUTUBE_COOKIES_FILE', None)
        
        # Or from command line args
        if len(sys.argv) > 4:
            skip_members_only = sys.argv[4].lower() == 'true'
        if len(sys.argv) > 5:
            cookies_file = sys.argv[5] if sys.argv[5] != 'none' else None
        
        result = process_video_with_dedicated_whisper(
            worker_id, video_id, video_title, skip_members_only, cookies_file
        )
        print(f"RESULT: {result}")
