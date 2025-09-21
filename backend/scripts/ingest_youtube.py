#!/usr/bin/env python3
"""
Complete YouTube transcript ingestion pipeline with preferred order:
1. youtube-transcript-api (cheap, fast)
2. yt-dlp subtitles (with proxy support)  
3. Mark for Whisper processing (optional GPU run)

All results are normalized, chunked, embedded, and stored with provenance tags.
"""

import os
import sys
import argparse
import logging
import json
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import time
import tempfile
import subprocess

# Third-party imports
import tqdm
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from scripts.common.list_videos_api import YouTubeAPILister
from scripts.common.transcripts import TranscriptFetcher, TranscriptSegment, create_transcript_fetcher
from scripts.common.database_upsert import DatabaseUpserter, ChunkData
from scripts.common.embeddings import EmbeddingGenerator
from scripts.common.transcript_processor import TranscriptProcessor

# Import Whisper support
try:
    import faster_whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_ingestion.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class IngestConfig:
    """Configuration for the ingestion pipeline"""
    # Data source
    source: str = 'yt-dlp'  # 'yt-dlp' or 'api'
    from_json: Optional[Path] = None
    channel_url: str = None
    
    # Processing limits
    concurrency: int = 4
    limit: Optional[int] = None
    skip_shorts: bool = False
    max_duration: Optional[int] = None
    newest_first: bool = False
    
    # Execution modes
    dry_run: bool = False
    
    # Database
    db_url: str = None
    
    # API keys
    youtube_api_key: Optional[str] = None
    
    def __post_init__(self):
        if self.channel_url is None:
            self.channel_url = os.getenv('YOUTUBE_CHANNEL_URL', 'https://www.youtube.com/@anthonychaffeemd')
        
        if self.db_url is None:
            self.db_url = os.getenv('DATABASE_URL')
            if not self.db_url:
                raise ValueError("DATABASE_URL environment variable required")
        
        if self.source == 'api':
            if self.youtube_api_key is None:
                self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')
            if not self.youtube_api_key:
                raise ValueError("YOUTUBE_API_KEY required for API source")

@dataclass
class BatchStats:
    """Statistics for a processing batch"""
    total: int = 0
    processed: int = 0
    skipped: int = 0
    errors: int = 0
    done: int = 0
    
    def log_batch_summary(self, batch_num: int):
        """Log summary for this batch"""
        logger.info(f"=== BATCH {batch_num} SUMMARY ===")
        logger.info(f"Processed: {self.processed}, Done: {self.done}, Errors: {self.errors}, Skipped: {self.skipped}")
        
        if self.total > 0:
            success_rate = (self.done / self.total) * 100
            logger.info(f"Batch success rate: {success_rate:.1f}%")

class RobustYouTubeIngester:
    """Production-ready YouTube ingestion pipeline with resumability"""
    
    def __init__(self, config: IngestConfig):
        self.config = config
        
        # Initialize components
        self.db = DatabaseUpserter(config.db_url)
        self.transcript_fetcher = create_transcript_fetcher()
        self.embedder = EmbeddingGenerator()
        self.processor = TranscriptProcessor(
            chunk_duration_seconds=int(os.getenv('CHUNK_DURATION_SECONDS', 45))
        )
        
        # Whisper configuration for --whisper mode
        self.whisper_model = None
        self.ytdlp_bin = os.getenv('YTDLP_BIN', 'yt-dlp')
        self.ytdlp_proxy = os.getenv('YTDLP_PROXY', '').strip()
        
        # Initialize video lister based on source
        if config.source == 'yt-dlp':
            self.video_lister = YtDlpVideoLister()
        elif config.source == 'api':
            self.video_lister = YouTubeAPILister(config.youtube_api_key)
        else:
            raise ValueError(f"Unknown source: {config.source}")
    
    def list_videos(self) -> List[VideoInfo]:
        """List videos using configured source"""
        logger.info(f"Listing videos using {self.config.source} source")
        
        if self.config.from_json:
            # Load from JSON file (yt-dlp only)
            if self.config.source != 'yt-dlp':
                raise ValueError("--from-json only supported with yt-dlp source")
            videos = self.video_lister.list_from_json(self.config.from_json)
        else:
            # List from channel
            if self.config.source == 'yt-dlp':
                videos = self.video_lister.list_channel_videos(self.config.channel_url)
            else:  # api
                videos = self.video_lister.list_channel_videos(
                    self.config.channel_url,
                    max_results=self.config.limit
                )
        
        # Apply filters
        if self.config.skip_shorts:
            videos = [v for v in videos if not v.duration_s or v.duration_s >= 120]
            logger.info(f"Filtered out shorts, {len(videos)} videos remaining")
        
        if self.config.max_duration:
            videos = [v for v in videos if not v.duration_s or v.duration_s <= self.config.max_duration]
            logger.info(f"Filtered by max duration, {len(videos)} videos remaining")
        
        # Apply sorting
        if self.config.newest_first:
            videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)
        else:
            videos.sort(key=lambda v: v.published_at or datetime.min)
        
        # Apply limit
        if self.config.limit:
            videos = videos[:self.config.limit]
        
        logger.info(f"Found {len(videos)} videos to process")
        return videos
    
    def get_pending_videos(self, batch_size: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get videos that need processing (resumable queue)"""
        # Get videos in pending or error state (with retry limits)
        pending_videos = self.db.get_videos_by_status('pending', limit=batch_size)
        error_videos = []
        
        # Add error videos that haven't exceeded retry limit
        all_error_videos = self.db.get_videos_by_status('error', limit=batch_size * 2 if batch_size else None)
        for video in all_error_videos:
            if video.get('retries', 0) < 3:
                error_videos.append(video)
        
        combined = pending_videos + error_videos
        
        if batch_size:
            combined = combined[:batch_size]
        
        logger.info(f"Found {len(pending_videos)} pending + {len(error_videos)} retryable error videos")
        return combined
    
    def should_skip_video(self, video_info: VideoInfo) -> Tuple[bool, str]:
        """Check if video should be skipped based on current state"""
        state = self.db.get_ingest_state(video_info.video_id)
        
        if state:
            if state['status'] in ('done', 'upserted'):
                return True, f"already completed (status: {state['status']})"
            elif state['status'] == 'error' and state.get('retries', 0) >= 3:
                return True, f"max retries exceeded ({state.get('retries', 0)})"
        
        return False, ""
    
    def process_single_video(self, video_info: VideoInfo) -> bool:
        """Process a single video through the complete transcript pipeline"""
        video_id = video_info.video_id
        
        try:
            # Check if should skip
            should_skip, reason = self.should_skip_video(video_info)
            if should_skip:
                logger.debug(f"Skipping {video_id}: {reason}")
                return True
            
            logger.info(f"Processing {video_id}: {video_info.title}")
            
            # Initialize/update ingest state
            self.db.upsert_ingest_state(video_id, video_info, status='pending')
            
            # Step 1: Fetch transcript using new pipeline
            segments, provenance = self.transcript_fetcher.fetch_transcript(video_id)
            
            if not segments:
                # No transcript found - mark for Whisper
                self.db.update_ingest_status(
                    video_id, 'needs_whisper',
                    error='no_captions'
                )
                logger.info(f"📝 {video_id} marked for Whisper processing")
                return True
            
            # Step 2: Determine access level and metadata
            access_level = 'public'  # Default for public YouTube videos
            extra_metadata = {
                'has_captions': True,
                'is_clip': video_info.duration_s and video_info.duration_s < 300  # <5min = clip
            }
            
            # Step 3: Chunk transcript (45-60s sentence-aware)
            chunks = self.processor.process_segments(segments)
            chunk_data = []
            for i, chunk in enumerate(chunks):
                chunk_obj = ChunkData(
                    chunk_hash=f"{video_id}_{i}",
                    source_id=video_id,  # Will be updated after source insert
                    text=chunk.text,
                    t_start_s=chunk.start,
                    t_end_s=chunk.end
                )
                chunk_data.append(chunk_obj)
            
            self.db.update_ingest_status(video_id, 'chunked', chunk_count=len(chunk_data))
            
            # Step 4: Generate embeddings
            texts = [chunk.text for chunk in chunk_data]
            embeddings = self.embedder.generate_embeddings(texts)
            
            # Attach embeddings to chunks
            for chunk, embedding in zip(chunk_data, embeddings):
                chunk.embedding = embedding
            
            self.db.update_ingest_status(video_id, 'embedded', embedding_count=len(embeddings))
            
            # Step 5: Upsert to database with provenance tracking
            source_id = self.db.upsert_source(
                video_info,
                source_type='youtube',
                provenance=provenance,
                access_level=access_level,
                extra_metadata=extra_metadata
            )
            
            # Update chunks with correct source_id
            for chunk in chunk_data:
                chunk.source_id = source_id
            
            chunk_count = self.db.upsert_chunks(chunk_data)
            
            self.db.update_ingest_status(video_id, 'done')
            
            logger.info(f"✅ {video_id} completed: {len(chunk_data)} chunks, provenance={provenance}")
            return True
            
        except Exception as e:
            error_msg = str(e)[:500]  # Truncate long errors
            logger.error(f"❌ Error processing {video_id}: {error_msg}")
            
            try:
                self.db.update_ingest_status(
                    video_id, 'error',
                    error=error_msg,
                    increment_retries=True
                )
            except Exception as db_error:
                logger.error(f"Failed to update error status: {db_error}")
            
            return False
    
    def process_whisper_videos(self, limit: Optional[int] = None) -> None:
        """Process videos marked for Whisper transcription"""
        if not WHISPER_AVAILABLE:
            logger.error("Whisper not available. Install with: pip install faster-whisper")
            return
        
        # Get videos that need Whisper processing
        needs_whisper = self.db.get_videos_by_status('needs_whisper', limit=limit)
        
        if not needs_whisper:
            logger.info("No videos need Whisper processing")
            return
        
        logger.info(f"Processing {len(needs_whisper)} videos with Whisper")
        
        # Initialize Whisper model
        if not self.whisper_model:
            model_name = os.getenv('WHISPER_MODEL', 'small.en')
            logger.info(f"Loading Whisper model: {model_name}")
            self.whisper_model = faster_whisper.WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8"
            )
        
        for video_data in tqdm.tqdm(needs_whisper, desc="Whisper processing"):
            video_id = video_data['video_id']
            self._process_single_whisper(video_id, video_data)
    
    def _process_single_whisper(self, video_id: str, video_data: Dict[str, Any]) -> bool:
        """Process a single video with Whisper transcription"""
        try:
            logger.info(f"🎤 Whisper processing {video_id}: {video_data.get('title', 'Unknown')}")
            
            # Check duration limits for cost control
            duration_s = video_data.get('duration_s', 0)
            max_duration = int(os.getenv('MAX_AUDIO_DURATION', 3600))
            
            if duration_s > max_duration:
                logger.warning(f"Skipping {video_id}: duration {duration_s}s exceeds limit {max_duration}s")
                self.db.update_ingest_status(
                    video_id, 'error',
                    error=f'duration_exceeds_limit_{max_duration}s',
                    increment_retries=True
                )
                return False
            
            # Download audio with yt-dlp
            audio_path = self._download_audio(video_id)
            if not audio_path:
                self.db.update_ingest_status(
                    video_id, 'error',
                    error='audio_download_failed',
                    increment_retries=True
                )
                return False
            
            try:
                # Preprocess audio to 16kHz mono
                processed_audio = self._preprocess_audio(audio_path)
                
                # Transcribe with Whisper
                segments = self._transcribe_with_whisper(processed_audio)
                
                if not segments:
                    self.db.update_ingest_status(
                        video_id, 'error',
                        error='whisper_transcription_failed',
                        increment_retries=True
                    )
                    return False
                
                # Continue with normal pipeline (chunk, embed, upsert)
                video_info = VideoInfo(
                    video_id=video_id,
                    title=video_data.get('title', ''),
                    duration_s=video_data.get('duration_s'),
                    published_at=video_data.get('published_at'),
                    view_count=video_data.get('view_count', 0),
                    description=video_data.get('description', '')
                )
                
                return self._complete_whisper_pipeline(video_info, segments)
                
            finally:
                # Clean up audio files
                for file_path in [audio_path, processed_audio]:
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except OSError:
                            pass
        
        except Exception as e:
            error_msg = str(e)[:500]
            logger.error(f"❌ Whisper error for {video_id}: {error_msg}")
            
            try:
                self.db.update_ingest_status(
                    video_id, 'error',
                    error=error_msg,
                    increment_retries=True
                )
            except Exception as db_error:
                logger.error(f"Failed to update error status: {db_error}")
            
            return False
    
    def _download_audio(self, video_id: str) -> Optional[str]:
        """Download audio using yt-dlp"""
        output_dir = Path(tempfile.gettempdir()) / 'whisper_audio'
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{video_id}.%(ext)s"
        
        cmd = [
            self.ytdlp_bin,
            f"https://www.youtube.com/watch?v={video_id}",
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', '0',
            '-o', str(output_path)
        ]
        
        if self.ytdlp_proxy:
            cmd.extend(['--proxy', self.ytdlp_proxy])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.error(f"yt-dlp audio download failed for {video_id}: {result.stderr}")
                return None
            
            # Find the downloaded file
            for ext in ['mp3', 'webm', 'm4a', 'ogg']:
                candidate = str(output_path).replace('%(ext)s', ext)
                if os.path.exists(candidate):
                    return candidate
            
            return None
            
        except subprocess.TimeoutExpired:
            logger.error(f"Audio download timeout for {video_id}")
            return None
        except Exception as e:
            logger.error(f"Audio download error for {video_id}: {e}")
            return None
    
    def _preprocess_audio(self, audio_path: str) -> str:
        """Preprocess audio to 16kHz mono WAV"""
        output_path = audio_path.rsplit('.', 1)[0] + '_processed.wav'
        
        cmd = [
            'ffmpeg', '-i', audio_path,
            '-ac', '1', '-ar', '16000', '-sample_fmt', 's16',
            '-vn', '-y', output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logger.error(f"ffmpeg preprocessing failed: {result.stderr}")
                return audio_path  # Return original if preprocessing fails
            
            return output_path
            
        except Exception as e:
            logger.warning(f"Audio preprocessing failed, using original: {e}")
            return audio_path
    
    def _transcribe_with_whisper(self, audio_path: str) -> Optional[List[TranscriptSegment]]:
        """Transcribe audio with Whisper"""
        try:
            segments, info = self.whisper_model.transcribe(
                audio_path,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 700}
            )
            
            transcript_segments = []
            for segment in segments:
                # Convert Whisper segment to our format
                seg = TranscriptSegment(
                    start=segment.start,
                    end=segment.end,
                    text=segment.text.strip()
                )
                if seg.text and len(seg.text) > 2:
                    transcript_segments.append(seg)
            
            return transcript_segments
            
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return None
    
    def _complete_whisper_pipeline(self, video_info: VideoInfo, segments: List[TranscriptSegment]) -> bool:
        """Complete the pipeline for Whisper-transcribed content"""
        try:
            video_id = video_info.video_id
            
            # Chunk transcript
            chunks = self.processor.process_segments(segments)
            chunk_data = []
            for i, chunk in enumerate(chunks):
                chunk_obj = ChunkData(
                    chunk_hash=f"{video_id}_{i}",
                    source_id=video_id,
                    text=chunk.text,
                    t_start_s=chunk.start,
                    t_end_s=chunk.end
                )
                chunk_data.append(chunk_obj)
            
            # Generate embeddings
            texts = [chunk.text for chunk in chunk_data]
            embeddings = self.embedder.generate_embeddings(texts)
            
            # Attach embeddings
            for chunk, embedding in zip(chunk_data, embeddings):
                chunk.embedding = embedding
            
            # Upsert with Whisper provenance
            extra_metadata = {'has_captions': False, 'whisper_transcribed': True}
            source_id = self.db.upsert_source(
                video_info,
                source_type='youtube',
                provenance='whisper',
                access_level='public',
                extra_metadata=extra_metadata
            )
            
            # Update chunks with source_id
            for chunk in chunk_data:
                chunk.source_id = source_id
            
            self.db.upsert_chunks(chunk_data)
            self.db.update_ingest_status(video_id, 'done')
            
            logger.info(f"✅ Whisper completed {video_id}: {len(chunk_data)} chunks")
            return True
            
        except Exception as e:
            logger.error(f"Whisper pipeline completion failed: {e}")
            return False


def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(description="Robust YouTube transcript ingestion pipeline")
    parser.add_argument('channel_identifier', help='Channel handle (@username) or channel_id')
    parser.add_argument('--limit', type=int, default=50, help='Maximum videos to process')
    parser.add_argument('--max-duration', type=int, default=7200, help='Maximum video duration (seconds)')
    parser.add_argument('--source', choices=['api', 'yt-dlp'], default='api', help='Video listing source')
    parser.add_argument('--since-published', help='Only process videos published after this date (YYYY-MM-DD)')
    parser.add_argument('--whisper', action='store_true', help='Process videos marked for Whisper transcription')
    parser.add_argument('--whisper-limit', type=int, default=10, help='Max videos to process in Whisper mode')
    parser.add_argument('--batch-size', type=int, default=5, help='Batch size for concurrent processing')
    parser.add_argument('--max-workers', type=int, default=3, help='Max concurrent workers')
    
    args = parser.parse_args()
    
    # Load configuration
    config = IngestConfig(
        channel_identifier=args.channel_identifier,
        max_videos=args.limit,
        max_duration=args.max_duration,
        source=args.source,
        since_published=args.since_published,
        youtube_api_key=os.getenv('YOUTUBE_API_KEY'),
        db_url=os.getenv('DATABASE_URL')
    )
    
    # Initialize ingester
    ingester = RobustYouTubeIngester(config)
    
    if args.whisper:
        # Whisper processing mode
        logger.info(f"🎤 Starting Whisper processing (limit: {args.whisper_limit})")
        ingester.process_whisper_videos(limit=args.whisper_limit)
    else:
        # Normal ingestion mode
        logger.info(f"🚀 Starting YouTube ingestion for {config.channel_identifier}")
        logger.info(f"Source: {config.source}, Limit: {config.max_videos}, Max duration: {config.max_duration}s")
        
        success = ingester.ingest_videos(
            batch_size=args.batch_size,
            max_workers=args.max_workers
        )
        
        if success:
            logger.info("✅ Ingestion completed successfully")
        else:
            logger.error("❌ Ingestion completed with errors")
            sys.exit(1)


if __name__ == "__main__":
    main()
