#!/usr/bin/env python3
"""
YouTube ingestion with Enhanced ASR and speaker identification
Extends the existing ingestion pipeline with speaker recognition capabilities
"""

import os
import sys
import logging
import argparse
import warnings
import multiprocessing
import concurrent.futures
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Suppress noisy deprecation warnings
warnings.filterwarnings("ignore", category=UserWarning, message=".*torchaudio.*deprecated.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*TensorFloat-32.*")
warnings.filterwarnings("ignore", category=UserWarning, message=".*TorchCodec.*")

# Suppress torchaudio backend warnings
os.environ["TORCHAUDIO_USE_BACKEND_DISPATCHER"] = "0"
# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import existing ingestion components
from common.database import DatabaseManager
from common.segments_database import SegmentsDatabase
from common.embeddings import EmbeddingGenerator
from common.transcript_processor import TranscriptProcessor

# Import enhanced transcript fetching and video listing
from common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
from common.list_videos_yt_dlp import YtDlpVideoLister

logger = logging.getLogger(__name__)

class EnhancedYouTubeIngestion:
    """YouTube ingestion with Enhanced ASR capabilities"""
    
    def __init__(self, 
                 enable_speaker_id: bool = None,
                 voices_dir: str = None,
                 chaffee_min_sim: float = None,
                 source_type: str = None,
                 workers: int = None):
        
        # MANDATORY: Chaffee speaker identification is ALWAYS enabled (non-negotiable)
        self.enable_speaker_id = True  # FORCED - cannot be disabled
        self.voices_dir = voices_dir or os.getenv('VOICES_DIR', 'voices')
        self.chaffee_min_sim = chaffee_min_sim if chaffee_min_sim is not None else float(os.getenv('CHAFFEE_MIN_SIM', '0.62'))
        
        # MANDATORY: Verify Chaffee profile exists - CANNOT proceed without it
        chaffee_profile_path = os.path.join(self.voices_dir, 'chaffee.json')
        if not os.path.exists(chaffee_profile_path):
            raise FileNotFoundError(f"CRITICAL: Chaffee voice profile not found at {chaffee_profile_path}. "
                                  f"Speaker identification is MANDATORY to prevent misattribution. "
                                  f"Cannot proceed without Dr. Chaffee's voice profile!")
        self.source_type = source_type or os.getenv('SOURCE_TYPE', 'youtube')
        self.workers = workers or int(os.getenv('WHISPER_PARALLEL_MODELS', '4'))
        
        # Initialize components with .env values
        self.transcript_fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=self.enable_speaker_id,
            voices_dir=self.voices_dir,
            chaffee_min_sim=self.chaffee_min_sim,
            api_key=os.getenv('YOUTUBE_API_KEY'),
            ffmpeg_path=os.getenv('FFMPEG_PATH')
        )
        
        self.transcript_processor = TranscriptProcessor(chunk_duration_seconds=45)
        self.embedding_generator = EmbeddingGenerator()
        
        # Initialize enhanced segments database
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is required")
        self.segments_db = SegmentsDatabase(db_url)
        
        logger.info(f"Enhanced YouTube Ingestion initialized (speaker_id={enable_speaker_id})")
    
    def _check_existing_video(self, video_id: str) -> Tuple[Optional[int], int]:
        """Check if video already exists in database and return source_id and segment count"""
        try:
            return self.segments_db.check_video_exists(video_id)
        except Exception as e:
            logger.error(f"Failed to check existing video {video_id}: {e}")
            return None, 0
    
    def process_video(self, video_id: str, force_enhanced_asr: bool = False, skip_existing: bool = True) -> Dict[str, Any]:
        """
        Process a single YouTube video with Enhanced ASR and caching/resume support
        
        Args:
            video_id: YouTube video ID
            force_enhanced_asr: Skip YouTube transcripts and use Enhanced ASR
            skip_existing: Skip videos already processed in database
            
        Returns:
            Processing results with metadata
        """
        results = {
            'video_id': video_id,
            'success': False,
            'method': None,
            'segments_count': 0,
            'chunks_count': 0,
            'speaker_metadata': {},
            'refinement_stats': {},
            'error': None,
            'skipped': False,
            'processing_time': 0
        }
        
        start_time = time.time()
        
        try:
            # Enhanced caching: Check if video already exists and is complete
            if skip_existing:
                existing_source_id, existing_chunks = self._check_existing_video(video_id)
                if existing_source_id and existing_chunks > 0:
                    logger.info(f"✅ Skipping {video_id}: already processed ({existing_chunks} chunks)")
                    results.update({
                        'success': True,
                        'skipped': True,
                        'chunks_count': existing_chunks,
                        'source_id': existing_source_id
                    })
                    return results
            
            logger.info(f"🚀 Processing video {video_id} with optimized Enhanced ASR")
            
            # Check Enhanced ASR status
            asr_status = self.transcript_fetcher.get_enhanced_asr_status()
            logger.info(f"Enhanced ASR status: enabled={asr_status['enabled']}, available={asr_status['available']}")
            
            if asr_status['enabled'] and asr_status['available']:
                logger.info(f"Available voice profiles: {asr_status['voice_profiles']}")
            
            # Fetch transcript with speaker identification
            segments, method, metadata = self.transcript_fetcher.fetch_transcript_with_speaker_id(
                video_id,
                force_enhanced_asr=force_enhanced_asr,
                cleanup_audio=True
            )
            
            if not segments:
                results['error'] = metadata.get('error', 'Transcript fetching failed')
                logger.error(f"Failed to fetch transcript for {video_id}: {results['error']}")
                return results
            
            results['method'] = method
            results['segments_count'] = len(segments)
            
            # Extract speaker metadata and refinement stats if available
            if metadata.get('enhanced_asr_used'):
                results['speaker_metadata'] = {
                    'chaffee_percentage': metadata.get('chaffee_percentage', 0.0),
                    'speaker_distribution': metadata.get('speaker_distribution', {}),
                    'unknown_segments': metadata.get('unknown_segments', 0),
                    'processing_method': metadata.get('processing_method', method)
                }
                
                # Extract refinement statistics
                refinement_stats = metadata.get('refinement_stats', {})
                if refinement_stats:
                    results['refinement_stats'] = {
                        'total_segments': refinement_stats.get('total_segments', 0),
                        'refined_segments': refinement_stats.get('refined_segments', 0),
                        'low_quality_segments': metadata.get('low_quality_segments', 0),
                        'refinement_percentage': (refinement_stats.get('refined_segments', 0) / 
                                                max(refinement_stats.get('total_segments', 1), 1)) * 100
                    }
                    logger.info(f"📊 Quality triage: {refinement_stats.get('refined_segments', 0)}/{refinement_stats.get('total_segments', 0)} segments refined")
                
                # Will log speaker results after source_id is available
            
            # Convert segments to transcript entries for chunking
            transcript_entries = []
            for segment in segments:
                entry = {
                    'start': segment.start,
                    'duration': segment.end - segment.start,
                    'text': segment.text
                }
                
                # Add speaker metadata if available
                if hasattr(segment, 'metadata') and segment.metadata:
                    entry['speaker_metadata'] = segment.metadata
                
                transcript_entries.append(entry)
            
            # Chunk transcript
            chunks = self.transcript_processor.chunk_transcript(transcript_entries)
            results['chunks_count'] = len(chunks)
            
            # Generate embeddings for chunks
            logger.info(f"Generating embeddings for {len(chunks)} chunks")
            for chunk in chunks:
                try:
                    embedding = self.embedding_generator.generate_single_embedding(chunk['text'])
                    # Ensure embedding is a Python list, not numpy array 
                    if hasattr(embedding, 'tolist'):
                        embedding = embedding.tolist()
                    elif hasattr(embedding, '__iter__'):
                        embedding = list(embedding)
                    chunk['embedding'] = embedding
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for chunk {chunk['chunk_index']}: {e}")
                    chunk['embedding'] = None
            
            # Get essential video info using yt-dlp
            try:
                import subprocess
                result = subprocess.run([
                    'yt-dlp', '--print', 
                    '%(title)s|||%(duration)s|||%(upload_date)s|||%(view_count)s',
                    video_id
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    parts = result.stdout.strip().split('|||')
                    real_title = parts[0] if len(parts) > 0 else f"YouTube Video {video_id}"
                    duration = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                    upload_date = parts[2] if len(parts) > 2 and parts[2] != 'NA' else None
                    view_count = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
                else:
                    real_title = f"YouTube Video {video_id}"
                    duration = 0
                    upload_date = None
                    view_count = 0
            except:
                real_title = f"YouTube Video {video_id}"
                duration = 0
                upload_date = None
                view_count = 0
            
            # Parse upload date
            published_at = None
            if upload_date:
                try:
                    from datetime import datetime
                    published_at = datetime.strptime(upload_date, '%Y%m%d')
                except:
                    pass

            # Prepare source metadata with processing timestamp
            from datetime import datetime
            source_metadata = {
                'video_id': video_id,
                'method': method,
                'segments_count': len(segments),
                'processing_timestamp': datetime.now().isoformat(),
                'duration_seconds': duration,
                'view_count': view_count,
            }
            
            # Add Enhanced ASR metadata
            if metadata.get('enhanced_asr_used'):
                source_metadata.update({
                    'enhanced_asr': True,
                    'speaker_identification': True,
                    'chaffee_percentage': metadata.get('chaffee_percentage', 0.0),
                    'speaker_distribution': metadata.get('speaker_distribution', {}),
                    'confidence_stats': metadata.get('confidence_stats', {}),
                    'similarity_stats': metadata.get('similarity_stats', {}),
                    'threshold_used': metadata.get('threshold_used', 0.50),
                    'segments_with_high_confidence': metadata.get('high_confidence_segments', 0),
                    'monologue_detected': method.endswith('_monologue'),
                    'total_speakers_detected': len(metadata.get('speaker_distribution', {}))
                })
            
            # Upsert to database
            logger.info(f"Upserting {len(chunks)} chunks to database")
            
            # Create source entry
            from backend.scripts.common.list_videos_yt_dlp import VideoInfo
            
            # Create a VideoInfo object with essential fields
            video_info = VideoInfo(
                video_id=video_id,
                title=real_title,
                duration_s=duration,
                published_at=published_at,
                view_count=view_count
            )
            
            # Use 'whisper' as provenance since Enhanced ASR is AI transcription
            provenance = 'whisper' if method in ['enhanced_asr', 'whisper'] else method
            
            source_id = self.segments_db.upsert_source(
                video_id=video_id,
                title=video_info.get('title', f'Video {video_id}'),
                source_type=self.source_type,
                metadata={
                    'provenance': provenance,
                    'duration': video_info.get('duration'),
                    'upload_date': video_info.get('upload_date'),
                    'view_count': video_info.get('view_count'),
                    'enhanced_asr_used': method in ['enhanced_asr', 'whisper']
                }
            )
            
            # Log speaker identification results with source_id for tracking
            if results.get('speaker_metadata'):
                speaker_meta = results['speaker_metadata']
                logger.info(f"🎯 Speaker identification results for {video_id} (source_id: {source_id}):")
                logger.info(f"   Chaffee: {speaker_meta['chaffee_percentage']:.1f}%")
                logger.info(f"   Unknown segments: {speaker_meta['unknown_segments']}")
                logger.info(f"   Total speakers: {len(speaker_meta.get('speaker_distribution', {}))}")
                logger.info(f"   Method: {speaker_meta.get('processing_method', 'unknown')}")
            
            # Prepare chunks for database upsert - INCLUDE ALL CHUNKS (embeddings generated later)
            db_chunks = []
            for chunk in chunks:
                # Ensure all values are native Python types, not numpy types
                t_start = float(chunk['start_time_seconds']) if chunk['start_time_seconds'] is not None else 0.0
                t_end = float(chunk['end_time_seconds']) if chunk['end_time_seconds'] is not None else 0.0
                
                # Convert embedding to list if needed (may be None, that's OK)
                embedding = chunk.get('embedding')
                if embedding is not None:
                    if hasattr(embedding, 'tolist'):
                        embedding = embedding.tolist()
                    elif hasattr(embedding, '__iter__') and not isinstance(embedding, list):
                        embedding = list(embedding)
                
                db_chunk = ChunkData(
                    chunk_hash=f"{video_id}:{chunk['chunk_index']}",
                    source_id=source_id,
                    text=chunk['text'],
                    t_start_s=t_start,
                    t_end_s=t_end,
                    embedding=embedding  # Can be None - embeddings generated in segments_db
                )
                db_chunks.append(db_chunk)
            
            # Insert segments with enhanced speaker attribution
            if db_chunks:
                # Convert chunks to segments format with Enhanced ASR metadata
                segments = []
                for i, chunk_data in enumerate(db_chunks):
                    # Get original chunk for Enhanced ASR metadata
                    orig_chunk = chunks[i] if i < len(chunks) else {}
                    
                    segment = {
                        'start': chunk_data.t_start_s,
                        'end': chunk_data.t_end_s,
                        'text': chunk_data.text,
                        'speaker_label': orig_chunk.get('speaker_label', 'GUEST'),
                        'speaker_confidence': orig_chunk.get('speaker_confidence', None),
                        'avg_logprob': orig_chunk.get('avg_logprob', None),
                        'compression_ratio': orig_chunk.get('compression_ratio', None),
                        'no_speech_prob': orig_chunk.get('no_speech_prob', None),
                        're_asr': orig_chunk.get('re_asr', False),
                        'embedding': chunk_data.embedding  # May be None - generated in segments_db
                    }
                    segments.append(segment)
                
                # Batch insert segments
                segments_count = self.segments_db.batch_insert_segments(
                    segments=segments,
                    video_id=video_id,
                    chaffee_only_storage=False,     # Store all speakers
                    embed_chaffee_only=False        # Embed all speakers
                )
                logger.info(f"✅ Inserted {segments_count} segments into database for {video_id}")
            else:
                logger.warning(f"⚠️  No chunks to insert for {video_id} - original chunks: {len(chunks)}")
            
            results['success'] = True
            logger.info(f"Successfully processed video {video_id}: {results['chunks_count']} chunks upserted")
            
            return results
            
        except Exception as e:
            results['error'] = str(e)
            logger.error(f"Failed to process video {video_id}: {e}")
            return results
        
        finally:
            results['processing_time'] = time.time() - start_time
    
    def process_video_batch(self, video_ids: list, force_enhanced_asr: bool = False, skip_existing: bool = True) -> Dict[str, Any]:
        """Process multiple videos in parallel with enhanced caching and resume support"""
        batch_results = {
            'total_videos': len(video_ids),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'video_results': {},
            'summary': {},
            'error_summary': {}
        }
        
        # Determine optimal number of parallel processes
        max_workers = self.workers or int(os.getenv('WHISPER_PARALLEL_MODELS', '4'))
        # Limit to CPU count - 1 to avoid system overload
        max_workers = min(max_workers, multiprocessing.cpu_count() - 1)
        max_workers = max(1, max_workers)  # Ensure at least 1 worker
        
        logger.info(f"Processing batch of {len(video_ids)} videos with {max_workers} parallel threads")
        error_counts = {}
        processed_count = 0
        
        # Define worker function for ProcessPoolExecutor
        def process_video_worker(args):
            idx, vid = args
            try:
                logger.info(f"[{idx}/{len(video_ids)}] Processing video {vid}")
                result = self.process_video(vid, force_enhanced_asr=force_enhanced_asr, skip_existing=skip_existing)
                success_msg = f"✅ [{idx}/{len(video_ids)}] SUCCESS: {vid} ({result.get('chunks_count', 0)} chunks)"
                return vid, result, True, None, success_msg
            except Exception as e:
                error_msg = str(e)
                fail_msg = f"💥 [{idx}/{len(video_ids)}] ERROR: {vid} - {error_msg}"
                return vid, {
                    'video_id': vid,
                    'success': False,
                    'error': f'Worker error: {error_msg}',
                    'chunks_count': 0
                }, False, error_msg, fail_msg
        
        # Process videos in parallel with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs with their indices
            future_to_idx = {executor.submit(process_video_worker, (i, vid)): i 
                            for i, vid in enumerate(video_ids, 1)}
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_idx):
                vid, result, success, error_msg, log_msg = future.result()
                batch_results['video_results'][vid] = result
                
                # Log the result
                logger.info(log_msg)
                
                # Update counters
                if success:
                    if result.get('skipped'):
                        batch_results['skipped'] += 1
                    else:
                        batch_results['successful'] += 1
                else:
                    batch_results['failed'] += 1
                    error_type = result.get('error', 'Unknown error')
                    error_counts[error_type] = error_counts.get(error_type, 0) + 1
                
                # Progress update
                processed_count += 1
                if processed_count % 10 == 0:
                    logger.info(f"🔄 Progress: {processed_count}/{len(video_ids)} processed, "
                              f"{batch_results['successful']} successful, {batch_results['failed']} failed, {batch_results['skipped']} skipped")
        
        # Store error summary
        batch_results['error_summary'] = error_counts
        
        # Generate batch summary
        total_chunks = sum(r['chunks_count'] for r in batch_results['video_results'].values() if r['success'])
        enhanced_asr_count = sum(1 for r in batch_results['video_results'].values() 
                                if r['success'] and 'enhanced_asr_used' in r.get('speaker_metadata', {}))
        
        batch_results['summary'] = {
            'total_chunks_processed': total_chunks,
            'enhanced_asr_videos': enhanced_asr_count,
            'average_chunks_per_video': total_chunks / max(batch_results['successful'], 1)
        }
        
        logger.info(f"Batch processing complete: {batch_results['successful']}/{batch_results['total_videos']} successful")
        return batch_results
    
    def setup_chaffee_profile(self, audio_sources: list, overwrite: bool = False) -> bool:
        """Setup Chaffee voice profile for speaker identification"""
        try:
            logger.info("Setting up Chaffee voice profile")
            
            success = False
            for source in audio_sources:
                if source.startswith('http'):
                    # YouTube URL - extract video ID
                    if 'v=' in source:
                        video_id = source.split('v=')[1].split('&')[0]
                        success = self.transcript_fetcher.enroll_speaker_from_video(
                            video_id, 
                            'Chaffee', 
                            overwrite=overwrite
                        )
                    else:
                        logger.warning(f"Could not extract video ID from URL: {source}")
                else:
                    # Assume it's a local file - use voice enrollment directly
                    from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
                    enrollment = VoiceEnrollment(voices_dir=self.voices_dir)
                    profile = enrollment.enroll_speaker(
                        name='Chaffee',
                        audio_sources=[source],
                        overwrite=overwrite
                    )
                    success = profile is not None
                
                if success:
                    logger.info(f"Successfully enrolled Chaffee from: {source}")
                    break
                else:
                    logger.warning(f"Failed to enroll Chaffee from: {source}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to setup Chaffee profile: {e}")
            return False

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="YouTube ingestion with Enhanced ASR and speaker identification"
    )
    
    # Video selection - either specific IDs, channel URL, or video list file
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--video-ids', nargs='+', help='Specific YouTube video IDs to process')
    group.add_argument('--channel-url', default=os.getenv('YOUTUBE_CHANNEL_URL'), 
                       help='YouTube channel URL to fetch videos from (default from .env)')
    group.add_argument('--video-list-file', help='JSON file with pre-fetched video list')
    
    # Channel fetching options
    parser.add_argument('--limit', type=int, default=50, help='Maximum videos to fetch from channel')
    parser.add_argument('--workers', type=int, help='Number of parallel workers (overrides env)')
    parser.add_argument('--force-enhanced-asr', action='store_true', 
                       help='Force Enhanced ASR (skip YouTube transcripts)')
    
    # Enhanced ASR options - use environment defaults
    parser.add_argument('--enable-speaker-id', action='store_true', default=True,
                       help='Speaker identification (MANDATORY - always enabled for accuracy)')
    parser.add_argument('--voices-dir', default=os.getenv('VOICES_DIR', 'voices'),
                       help='Voice profiles directory')
    parser.add_argument('--chaffee-min-sim', type=float, 
                       default=float(os.getenv('CHAFFEE_MIN_SIM', '0.62')),
                       help='Minimum similarity threshold for Chaffee')
    parser.add_argument('--source-type', default='youtube',
                       help='Source type for database')
    
    # Models & compute options
    parser.add_argument('--model-primary', default=os.getenv('WHISPER_MODEL_PRIMARY', 'distil-large-v3'),
                       help='Primary transcription model (default: distil-large-v3)')
    parser.add_argument('--model-refine', default=os.getenv('WHISPER_MODEL_REFINE', 'large-v3'),
                       help='Refinement model for low-quality segments (default: large-v3)')
    parser.add_argument('--compute-type', default=os.getenv('WHISPER_COMPUTE', 'float16'),
                       choices=['float16', 'int8_float16', 'int8'],
                       help='Compute type for models')
    parser.add_argument('--language', default='en', help='Language for transcription')
    
    # VAD/chunk/decoding options
    parser.add_argument('--vad-filter', action='store_true', default=True,
                       help='Enable Voice Activity Detection')
    parser.add_argument('--vad-threshold', type=float, default=0.5,
                       help='VAD threshold')
    parser.add_argument('--chunk-size', type=int, default=20,
                       help='Chunk size for processing')
    parser.add_argument('--beam-size', type=int, default=1,
                       help='Beam size for bulk transcription')
    parser.add_argument('--temperature', type=float, default=0.0,
                       help='Temperature for sampling')
    parser.add_argument('--temperature-increment-on-fallback', type=float, default=0.2,
                       help='Temperature increment on fallback')
    parser.add_argument('--initial-prompt', type=str, default='',
                       help='Initial prompt for Whisper')
    
    # Diarization & speaker profile options
    parser.add_argument('--diarization', action='store_true', default=True,
                       help='Enable speaker diarization')
    parser.add_argument('--ch-profile-path', type=str,
                       default=os.getenv('CH_PROFILE_PATH', 'data/chaffee_profile.json'),
                       help='Path to Chaffee speaker profile')
    parser.add_argument('--ch-hi', type=float, default=float(os.getenv('CH_HI', '0.75')),
                       help='Chaffee high threshold for entry')
    parser.add_argument('--ch-lo', type=float, default=float(os.getenv('CH_LO', '0.68')),
                       help='Chaffee low threshold for exit')
    parser.add_argument('--min-runs', type=int, default=int(os.getenv('MIN_RUNS', '2')),
                       help='Minimum consecutive segments for state change')
    parser.add_argument('--overlap-split-ms', type=int, default=int(os.getenv('OVERLAP_SPLIT_MS', '300')),
                       help='Split overlapping segments (milliseconds)')
    
    # Refinement policy options
    parser.add_argument('--reprobe-segments', action='store_true', default=True,
                       help='Enable segment refinement')
    parser.add_argument('--threshold-logprob-ch', type=float, 
                       default=float(os.getenv('THRESHOLD_LOGPROB_CH', '-0.55')),
                       help='Log probability threshold for Chaffee segments')
    parser.add_argument('--threshold-logprob-guest', type=float,
                       default=float(os.getenv('THRESHOLD_LOGPROB_GUEST', '-0.8')),
                       help='Log probability threshold for guest segments')
    parser.add_argument('--threshold-compression-ch', type=float,
                       default=float(os.getenv('THRESHOLD_COMPRESSION_CH', '2.4')),
                       help='Compression ratio threshold for Chaffee segments')
    parser.add_argument('--threshold-compression-guest', type=float,
                       default=float(os.getenv('THRESHOLD_COMPRESSION_GUEST', '2.6')),
                       help='Compression ratio threshold for guest segments')
    
    # Concurrency & I/O options
    parser.add_argument('--jobs', type=int, default=4,
                       help='Bulk processing queue size')
    parser.add_argument('--refine-jobs', type=int, default=1,
                       help='Refinement processing jobs')
    parser.add_argument('--output-dir', type=str, default='data/asr',
                       help='Output directory for files')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                       help='Skip videos already processed in database')
    parser.add_argument('--dry-run', action='store_true',
                       help='Dry run mode (no database writes)')
    
    # Database & embeddings options
    parser.add_argument('--db-url', default=os.getenv('DATABASE_URL'),
                       help='PostgreSQL connection string')
    parser.add_argument('--schema', default='public',
                       help='Database schema name')
    parser.add_argument('--embed-model', default=os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-large'),
                       help='Embedding model name')
    parser.add_argument('--embed-batch', type=int, default=256,
                       help='Embedding batch size')
    parser.add_argument('--embedding-provider', default=os.getenv('EMBEDDING_PROVIDER', 'local'),
                       choices=['openai', 'local'],
                       help='Embedding provider (local for sentence-transformers, openai for text-embedding-3-large)')
    parser.add_argument('--chaffee-only-storage', action='store_true',
                       help='Store only Chaffee segments in database (saves space)')
    parser.add_argument('--embed-chaffee-only', action='store_true', default=False,
                       help='Generate embeddings only for Chaffee segments (default: False - embed all)')
    
    # Chaffee profile setup
    parser.add_argument('--setup-chaffee', nargs='+', metavar='AUDIO_SOURCE',
                       help='Setup Chaffee profile from audio files or YouTube URLs')
    parser.add_argument('--overwrite-profile', action='store_true',
                       help='Overwrite existing Chaffee profile')
    
    # General options
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--output', help='Save results to JSON file')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Display enhanced configuration
    print(f"[CONFIG] Enhanced ASR Configuration with Chaffee-aware Diarization:")
    print(f"   Primary Model: {args.model_primary} ({args.compute_type})")
    print(f"   Refinement Model: {args.model_refine} (quality improvement)")
    print(f"   Language: {args.language}")
    print(f"   Beam Size: {args.beam_size} (bulk), 5 (refine)")
    print(f"   Temperature: {args.temperature} (+{args.temperature_increment_on_fallback} fallback)")
    print(f"   VAD Filter: {args.vad_filter}")
    print(f"   Chunk Size: {args.chunk_size}")
    print(f"   Parallel Jobs: {args.jobs} bulk, {args.refine_jobs} refine")
    print(f"   Embedding Provider: {args.embedding_provider} ({'local sentence-transformers' if args.embedding_provider == 'local' else args.embed_model})")
    print(f"   Output Directory: {args.output_dir}")
    print(f"   Skip Existing: {args.skip_existing}")
    
    # Speaker profile configuration
    print(f"\n[SPEAKER PROFILE] Chaffee-aware Configuration:")
    print(f"   Diarization: {args.diarization}")
    print(f"   Chaffee Profile: {args.ch_profile_path}")
    print(f"   Hysteresis Thresholds: HI={args.ch_hi}, LO={args.ch_lo}")
    print(f"   Min Runs: {args.min_runs} consecutive segments")
    print(f"   Overlap Split: {args.overlap_split_ms}ms")
    
    # Quality triage configuration  
    print(f"\n[QUALITY TRIAGE] Refinement Policy:")
    print(f"   Reprobe Segments: {args.reprobe_segments}")
    print(f"   CH Thresholds: logprob={args.threshold_logprob_ch}, compression={args.threshold_compression_ch}")
    print(f"   GUEST Thresholds: logprob={args.threshold_logprob_guest}, compression={args.threshold_compression_guest}")
    
    # Performance estimates for distil-large-v3
    if args.model_primary == 'distil-large-v3':
        print(f"\n[PERFORMANCE] distil-large-v3 Pipeline Estimates (RTX 5080):")
        print(f"   Primary Speed: ~5x faster than large-v3, superior to medium.en")
        print(f"   Quality: Large-v3 level accuracy with distillation efficiency")
        print(f"   Selective Refinement: {args.threshold_logprob_ch}/{args.threshold_compression_ch} thresholds")
        print(f"   Expected Refinement: 5-15% of segments for optimal quality")
        print(f"   Overall Speed: ~4x faster than pure large-v3")
        print(f"   Est. Videos/Hour: 60-80 (1-hour videos)")
        print(f"   8-Hour Target: 480-640 videos")
        
        if args.compute_type == 'float16':
            vram_per_job = 5.5
            recommended_jobs = 3
        elif args.compute_type == 'int8_float16':
            vram_per_job = 4.0
            recommended_jobs = 5
        else:
            vram_per_job = 3.0
            recommended_jobs = 6
            
        total_vram = args.jobs * vram_per_job
        print(f"   VRAM Usage: ~{total_vram:.1f}GB ({args.jobs} jobs × {vram_per_job}GB each)")
        if args.jobs > recommended_jobs:
            print(f"   WARNING: Consider reducing --jobs to {recommended_jobs} for {args.compute_type}")
    else:
        print(f"\n[PERFORMANCE] Using {args.model_primary} as primary model")
        print(f"   Note: distil-large-v3 is recommended for optimal quality+speed")
    
    # Initialize ingestion system with .env defaults
    ingestion = EnhancedYouTubeIngestion(
        enable_speaker_id=args.enable_speaker_id,
        voices_dir=args.voices_dir, 
        chaffee_min_sim=args.chaffee_min_sim,
        source_type=args.source_type,
        workers=args.workers
    )
    
    # Setup Chaffee profile if requested
    if args.setup_chaffee:
        logger.info("Setting up Chaffee voice profile...")
        success = ingestion.setup_chaffee_profile(
            audio_sources=args.setup_chaffee,
            overwrite=args.overwrite_profile
        )
        
        if success:
            print("✅ Chaffee voice profile setup successful")
        else:
            print("Chaffee voice profile setup failed")
            return 1
    
    # Check Enhanced ASR status
    asr_status = ingestion.transcript_fetcher.get_enhanced_asr_status()
    print(f"[ASR] Enhanced ASR Status:")
    print(f"   Enabled: {asr_status['enabled']}")
    print(f"   Available: {asr_status['available']}")
    print(f"   Voice Profiles: {asr_status['voice_profiles']}")
    
    if not asr_status['available'] and args.enable_speaker_id:
        print("Enhanced ASR not available - install dependencies:")
        print("   pip install whisperx pyannote.audio speechbrain")
    
    # Get video IDs (either from args or channel)
    if args.channel_url:
        print(f"[FETCH] Fetching videos from channel: {args.channel_url}")
        video_lister = YtDlpVideoLister()
        videos_data = video_lister.list_channel_videos(args.channel_url)
        
        # Extract video IDs and limit if specified
        video_ids = [video.video_id for video in videos_data[:args.limit]]
        print(f"[FETCH] Found {len(videos_data)} videos, processing {len(video_ids)}")
    else:
        video_ids = args.video_ids
        print(f"[VIDEO] Processing {len(video_ids)} specified videos...")
    
    # Process videos
    batch_results = ingestion.process_video_batch(
        video_ids=video_ids,
        force_enhanced_asr=args.force_enhanced_asr,
        skip_existing=args.skip_existing
    )
    
    # Print results
    print(f"\n[RESULTS] Processing Results:")
    total_videos = batch_results['total_videos'] 
    if total_videos > 0:
        print(f"   Successful: {batch_results['successful']}/{total_videos} ({batch_results['successful']/total_videos*100:.1f}%)")
        print(f"   Skipped: {batch_results['skipped']}/{total_videos} ({batch_results['skipped']/total_videos*100:.1f}%)")
        print(f"   Failed: {batch_results['failed']}/{total_videos} ({batch_results['failed']/total_videos*100:.1f}%)")
    else:
        print(f"   No videos found to process!")
        print(f"   Check channel URL or video list path")
    print(f"   Total chunks: {batch_results['summary']['total_chunks_processed']}")
    print(f"   Enhanced ASR videos: {batch_results['summary']['enhanced_asr_videos']}")
    
    # Show refinement statistics if available
    total_refinements = sum(r.get('refinement_stats', {}).get('refined_segments', 0) 
                           for r in batch_results['video_results'].values() if r['success'])
    total_segments = sum(r.get('refinement_stats', {}).get('total_segments', 0) 
                        for r in batch_results['video_results'].values() if r['success'])
    if total_segments > 0:
        refinement_pct = (total_refinements / total_segments) * 100
        print(f"   Quality Triage: {total_refinements}/{total_segments} segments refined ({refinement_pct:.1f}%)")
    
    # Show error summary
    if batch_results.get('error_summary'):
        print(f"\n[ERROR SUMMARY] Top failure reasons:")
        for error_type, count in sorted(batch_results['error_summary'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {error_type}: {count} videos")
    
    # Show successful videos only (limit output)
    successful_videos = [(vid, result) for vid, result in batch_results['video_results'].items() if result['success']]
    if successful_videos:
        print(f"\n[SUCCESS DETAILS] First 10 successful videos:")
        for i, (video_id, result) in enumerate(successful_videos[:10]):
            method = result.get('method', 'unknown')
            chunks = result.get('chunks_count', 0)
            print(f"   ✅ {video_id}: {method} ({chunks} chunks)")
            
            # Show speaker info if available
            if result.get('speaker_metadata'):
                speaker_meta = result['speaker_metadata']
                chaffee_pct = speaker_meta.get('chaffee_percentage', 0)
                if chaffee_pct > 0:
                    print(f"      🎯 Chaffee: {chaffee_pct:.1f}%")
    
    # Show sample failures (first 5 only)
    failed_videos = [(vid, result) for vid, result in batch_results['video_results'].items() if not result['success']]
    if failed_videos:
        print(f"\n[FAILURE SAMPLES] First 5 failed videos:")
        for i, (video_id, result) in enumerate(failed_videos[:5]):
            error = result.get('error', 'Unknown')[:100]  # Truncate long errors
            print(f"   ❌ {video_id}: {error}")
    
    # Save results if requested
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(batch_results, f, indent=2, default=str)
        print(f"\n[SAVED] Results saved to: {args.output}")
    
    # Return appropriate exit code
    return 0 if batch_results['failed'] == 0 else 1

if __name__ == '__main__':
    exit(main())
