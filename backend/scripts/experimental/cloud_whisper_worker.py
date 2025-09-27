#!/usr/bin/env python3
"""
Cloud Whisper Worker using OpenAI API
Designed for cost-effective daily cron processing in production
"""

import os
import sys
import logging
import time
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

# Add parent directories to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

def setup_logging():
    """Setup logging for cloud worker"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - CLOUD-WORKER - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

logger = setup_logging()

@dataclass
class CloudProcessingConfig:
    """Configuration for cloud-based processing"""
    openai_api_key: str
    max_file_size_mb: int = 25  # OpenAI API limit
    cost_per_minute: float = 0.006  # Current OpenAI pricing
    max_duration_minutes: int = 120  # Cost protection
    temp_cleanup: bool = True
    processing_method: str = "api_whisper"

def estimate_processing_cost(duration_seconds: float) -> float:
    """Estimate OpenAI API cost for processing"""
    minutes = duration_seconds / 60
    return minutes * 0.006  # $0.006 per minute

def download_audio_for_api(video_id: str, max_size_mb: int = 25) -> Optional[Path]:
    """Download and prepare audio file for OpenAI API"""
    logger.info(f"📥 Downloading audio for {video_id} (API processing)")
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            audio_file = temp_path / f"{video_id}.mp3"
            
            # Download with size and duration limits for cost control
            cmd = [
                'yt-dlp',
                f'https://www.youtube.com/watch?v={video_id}',
                '-x',
                '--audio-format', 'mp3',
                '--audio-quality', '5',  # Compressed for API upload
                '-o', str(audio_file.with_suffix('.%(ext)s')),
                '--no-playlist',
                '--no-warnings',
                '--match-filter', f'duration < 7200'  # Max 2 hours
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                error_msg = result.stderr
                if "Join this channel to get access to members-only" in error_msg:
                    logger.info(f"⏭️ Skipping {video_id} - members-only content")
                    return None
                else:
                    raise Exception(f"yt-dlp failed: {error_msg}")
            
            if not audio_file.exists():
                raise Exception("Audio file not created")
            
            # Check file size for API limits
            file_size_mb = audio_file.stat().st_size / (1024 * 1024)
            if file_size_mb > max_size_mb:
                logger.warning(f"⚠️ Audio file too large ({file_size_mb:.1f}MB > {max_size_mb}MB)")
                
                # Compress further for API
                compressed_file = temp_path / f"{video_id}_compressed.mp3"
                compress_cmd = [
                    'ffmpeg', '-i', str(audio_file),
                    '-ar', '16000',  # Lower sample rate
                    '-ab', '64k',    # Lower bitrate
                    '-ac', '1',      # Mono
                    str(compressed_file),
                    '-y'
                ]
                
                subprocess.run(compress_cmd, capture_output=True, check=True)
                audio_file = compressed_file
                
                new_size_mb = audio_file.stat().st_size / (1024 * 1024)
                logger.info(f"🗜️ Compressed audio: {file_size_mb:.1f}MB → {new_size_mb:.1f}MB")
                
                if new_size_mb > max_size_mb:
                    raise Exception(f"Audio still too large after compression: {new_size_mb:.1f}MB")
            
            # Move to persistent location for API upload
            persistent_path = Path(tempfile.gettempdir()) / f"{video_id}_api.mp3"
            import shutil
            shutil.move(str(audio_file), str(persistent_path))
            
            logger.info(f"✅ Audio ready for API: {persistent_path} ({file_size_mb:.1f}MB)")
            return persistent_path
            
    except Exception as e:
        logger.error(f"❌ Audio download failed for {video_id}: {e}")
        return None

def transcribe_with_openai_api(audio_file: Path, config: CloudProcessingConfig) -> Optional[Dict[str, Any]]:
    """Transcribe audio using OpenAI Whisper API"""
    try:
        import openai
        
        # Configure OpenAI client
        openai.api_key = config.openai_api_key
        
        logger.info(f"🎯 Transcribing with OpenAI Whisper API")
        start_time = time.time()
        
        with open(audio_file, 'rb') as audio:
            # Use OpenAI Whisper API
            response = openai.Audio.transcribe(
                model="whisper-1",
                file=audio,
                language="en",
                response_format="verbose_json",  # Get timestamps
                temperature=0.0
            )
        
        processing_time = time.time() - start_time
        
        # Parse response and convert to our format
        from scripts.common.transcript_common import TranscriptSegment
        
        segments = []
        if 'segments' in response:
            for segment_data in response['segments']:
                segment = TranscriptSegment(
                    start=segment_data['start'],
                    end=segment_data['end'], 
                    text=segment_data['text'].strip()
                )
                if len(segment.text) > 3:
                    segments.append(segment)
        else:
            # Fallback: create single segment from full text
            segment = TranscriptSegment(
                start=0.0,
                end=float(response.get('duration', 0)),
                text=response['text'].strip()
            )
            segments.append(segment)
        
        # Calculate actual cost
        duration_minutes = response.get('duration', 0) / 60
        actual_cost = duration_minutes * config.cost_per_minute
        
        metadata = {
            "model": "whisper-1-api",
            "processing_method": config.processing_method,
            "duration_minutes": duration_minutes,
            "processing_time_seconds": processing_time,
            "estimated_cost_usd": actual_cost,
            "segments_count": len(segments),
            "language": response.get('language', 'en')
        }
        
        logger.info(f"✅ API transcription complete: {len(segments)} segments, "
                   f"{duration_minutes:.1f}min, ${actual_cost:.4f}")
        
        return segments, metadata
        
    except Exception as e:
        logger.error(f"❌ OpenAI API transcription failed: {e}")
        return None, {"error": str(e)}

def process_video_with_api_whisper(video_id: str, video_title: str, config: CloudProcessingConfig) -> Dict[str, Any]:
    """Process a single video using OpenAI Whisper API"""
    logger.info(f"🎯 Processing {video_id} - {video_title} (Cloud API)")
    
    try:
        # Initialize components
        from scripts.common.database_upsert import DatabaseUpserter
        from scripts.common.embeddings import EmbeddingGenerator
        
        db_url = os.getenv('DATABASE_URL')
        db = DatabaseUpserter(db_url)
        embedder = EmbeddingGenerator()
        
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
                return {"video_id": video_id, "success": True, "skipped": True, "reason": "already_done"}
        except:
            pass
        
        # Create video info
        from scripts.common.list_videos_yt_dlp import VideoInfo
        video_info = VideoInfo(
            video_id=video_id,
            title=video_title,
            published_at=None,
            duration_s=None
        )
        
        # Update status
        db.upsert_ingest_state(video_id, video_info, status='pending')
        
        # Try YouTube transcript first (still free and fast)
        logger.info(f"📋 Checking for existing YouTube transcript")
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            from scripts.common.transcript_common import TranscriptSegment
            
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # MEDICAL-GRADE QUALITY: Only use manual transcripts, completely skip auto-generated
            # Auto-generated are too inaccurate for health/medical content
            manual_transcripts = [t for t in transcript_list if not t.is_generated]
            
            if manual_transcripts:
                transcript = manual_transcripts[0]  # Use first manual transcript
                logger.info(f"✅ Found manual transcript (human-created, medical-grade quality)")
                transcript_data = transcript.fetch()
                
                segments = []
                for entry in transcript_data:
                    segment = TranscriptSegment(
                        start=entry['start'],
                        end=entry['start'] + entry['duration'],
                        text=entry['text'].strip()
                    )
                    if len(segment.text) > 3:
                        segments.append(segment)
                
                method = "youtube-manual"
                metadata = {"method": method, "cost_usd": 0.0}
                logger.info(f"✅ Using YouTube manual transcript ({len(segments)} segments)")
            else:
                logger.info(f"❌ No manual transcripts available (only auto-generated found)")
                raise Exception("No manual transcripts available - skipping auto-generated for medical accuracy")
                
        except Exception as e:
            logger.info(f"📥 No manual transcript available, using Whisper API: {e}")
            
            # Download audio for API processing
            audio_file = download_audio_for_api(video_id, config.max_file_size_mb)
            if not audio_file:
                return {"video_id": video_id, "success": False, "error": "Audio download failed"}
            
            try:
                # Transcribe with OpenAI API
                segments, metadata = transcribe_with_openai_api(audio_file, config)
                
                if not segments:
                    return {"video_id": video_id, "success": False, "error": "API transcription failed"}
                
                method = "api-whisper"
                
            finally:
                # Cleanup temporary file
                if config.temp_cleanup and audio_file.exists():
                    audio_file.unlink()
                    logger.info(f"🗑️ Cleaned up temporary audio file")
        
        if not segments:
            error = "No transcript segments generated"
            logger.error(f"❌ {error}")
            db.update_ingest_status(video_id, 'error', error=error, increment_retries=True)
            return {"video_id": video_id, "success": False, "error": error}
        
        # Update transcript status
        db.update_ingest_status(
            video_id, 'transcribed',
            has_yt_transcript=(method.startswith('youtube')),
            has_whisper=(method.startswith('api')),
            processing_method=config.processing_method
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
        
        cost = metadata.get('estimated_cost_usd', 0.0)
        logger.info(f"✅ COMPLETED {video_id} - {len(chunks)} chunks, method: {method}, cost: ${cost:.4f}")
        
        return {
            "video_id": video_id,
            "success": True,
            "chunks": len(chunks),
            "method": method,
            "cost_usd": cost
        }
        
    except Exception as e:
        logger.error(f"❌ FAILED {video_id}: {e}")
        return {"video_id": video_id, "success": False, "error": str(e)}

if __name__ == "__main__":
    # Test single video processing
    import sys
    if len(sys.argv) >= 3:
        video_id = sys.argv[1]
        video_title = sys.argv[2]
        
        config = CloudProcessingConfig(
            openai_api_key=os.getenv('OPENAI_API_KEY')
        )
        
        if not config.openai_api_key:
            print("ERROR: OPENAI_API_KEY environment variable required")
            sys.exit(1)
        
        result = process_video_with_api_whisper(video_id, video_title, config)
        print(f"RESULT: {result}")
    else:
        print("Usage: python cloud_whisper_worker.py VIDEO_ID VIDEO_TITLE")
