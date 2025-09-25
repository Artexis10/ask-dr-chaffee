#!/usr/bin/env python3
"""
YouTube ingestion with Enhanced ASR and speaker identification
Extends the existing ingestion pipeline with speaker recognition capabilities
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import existing ingestion components
from backend.scripts.common.database import DatabaseManager
from backend.scripts.common.database_upsert import DatabaseUpserter, ChunkData
from backend.scripts.common.embeddings import EmbeddingGenerator
from backend.scripts.common.transcript_processor import TranscriptProcessor

# Import enhanced transcript fetching
from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher

logger = logging.getLogger(__name__)

class EnhancedYouTubeIngestion:
    """YouTube ingestion with Enhanced ASR capabilities"""
    
    def __init__(self, 
                 enable_speaker_id: bool = True,
                 voices_dir: str = "voices",
                 chaffee_min_sim: float = 0.82,
                 source_type: str = "youtube"):
        
        self.enable_speaker_id = enable_speaker_id
        self.voices_dir = voices_dir
        self.chaffee_min_sim = chaffee_min_sim
        self.source_type = source_type
        
        # Initialize components
        self.transcript_fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=enable_speaker_id,
            voices_dir=voices_dir,
            chaffee_min_sim=chaffee_min_sim,
            api_key=os.getenv('YOUTUBE_API_KEY'),
            ffmpeg_path=os.getenv('FFMPEG_PATH')
        )
        
        self.transcript_processor = TranscriptProcessor(chunk_duration_seconds=45)
        self.embedding_generator = EmbeddingGenerator()
        
        # Initialize database components
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is required")
        self.db_upserter = DatabaseUpserter(db_url)
        
        logger.info(f"Enhanced YouTube Ingestion initialized (speaker_id={enable_speaker_id})")
    
    def process_video(self, video_id: str, force_enhanced_asr: bool = False) -> Dict[str, Any]:
        """
        Process a single YouTube video with Enhanced ASR
        
        Args:
            video_id: YouTube video ID
            force_enhanced_asr: Skip YouTube transcripts and use Enhanced ASR
            
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
            'error': None
        }
        
        try:
            logger.info(f"Processing video {video_id} with Enhanced ASR")
            
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
            
            # Extract speaker metadata if available
            if metadata.get('enhanced_asr_used'):
                results['speaker_metadata'] = {
                    'chaffee_percentage': metadata.get('chaffee_percentage', 0.0),
                    'speaker_distribution': metadata.get('speaker_distribution', {}),
                    'unknown_segments': metadata.get('unknown_segments', 0),
                    'processing_method': metadata.get('processing_method', method)
                }
                
                logger.info(f"Speaker identification results:")
                logger.info(f"  Chaffee: {results['speaker_metadata']['chaffee_percentage']:.1f}%")
                logger.info(f"  Unknown segments: {results['speaker_metadata']['unknown_segments']}")
            
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
            
            source_id = self.db_upserter.upsert_source(
                video_info=video_info,
                source_type=self.source_type,
                provenance=provenance,
                extra_metadata=source_metadata
            )
            
            # Prepare chunks for database upsert
            db_chunks = []
            for chunk in chunks:
                if chunk['embedding'] is not None:
                    # Ensure all values are native Python types, not numpy types
                    t_start = float(chunk['start_time_seconds']) if chunk['start_time_seconds'] is not None else 0.0
                    t_end = float(chunk['end_time_seconds']) if chunk['end_time_seconds'] is not None else 0.0
                    
                    # Convert embedding to list if needed
                    embedding = chunk['embedding']
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
                        embedding=embedding
                    )
                    db_chunks.append(db_chunk)
            
            # Upsert chunks
            if db_chunks:
                self.db_upserter.upsert_chunks(db_chunks)
            
            results['success'] = True
            logger.info(f"Successfully processed video {video_id}: {results['chunks_count']} chunks upserted")
            
            return results
            
        except Exception as e:
            results['error'] = str(e)
            logger.error(f"Failed to process video {video_id}: {e}")
            return results
    
    def process_video_batch(self, video_ids: list, force_enhanced_asr: bool = False) -> Dict[str, Any]:
        """Process multiple videos"""
        batch_results = {
            'total_videos': len(video_ids),
            'successful': 0,
            'failed': 0,
            'video_results': {},
            'summary': {}
        }
        
        logger.info(f"Processing batch of {len(video_ids)} videos")
        
        for video_id in video_ids:
            result = self.process_video(video_id, force_enhanced_asr=force_enhanced_asr)
            batch_results['video_results'][video_id] = result
            
            if result['success']:
                batch_results['successful'] += 1
            else:
                batch_results['failed'] += 1
        
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
                    from backend.scripts.common.voice_enrollment import VoiceEnrollment
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
    """CLI for Enhanced YouTube ingestion"""
    parser = argparse.ArgumentParser(
        description='YouTube ingestion with Enhanced ASR and speaker identification'
    )
    
    # Video processing
    parser.add_argument('video_ids', nargs='+', help='YouTube video IDs to process')
    parser.add_argument('--force-enhanced-asr', action='store_true', 
                       help='Force Enhanced ASR (skip YouTube transcripts)')
    
    # Enhanced ASR options
    parser.add_argument('--enable-speaker-id', action='store_true', default=True,
                       help='Enable speaker identification')
    parser.add_argument('--voices-dir', default='voices', help='Voice profiles directory')
    parser.add_argument('--chaffee-min-sim', type=float, default=0.82,
                       help='Minimum similarity threshold for Chaffee')
    parser.add_argument('--source-type', default='youtube',
                       help='Source type for database')
    
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
    
    # Initialize ingestion system
    ingestion = EnhancedYouTubeIngestion(
        enable_speaker_id=args.enable_speaker_id,
        voices_dir=args.voices_dir,
        chaffee_min_sim=args.chaffee_min_sim,
        source_type=args.source_type
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
    
    # Process videos
    print(f"\n[VIDEO] Processing {len(args.video_ids)} videos...")
    
    batch_results = ingestion.process_video_batch(
        video_ids=args.video_ids,
        force_enhanced_asr=args.force_enhanced_asr
    )
    
    # Print results
    print(f"\n[RESULTS] Processing Results:")
    print(f"   Successful: {batch_results['successful']}/{batch_results['total_videos']}")
    print(f"   Failed: {batch_results['failed']}/{batch_results['total_videos']}")
    print(f"   Total chunks: {batch_results['summary']['total_chunks_processed']}")
    print(f"   Enhanced ASR videos: {batch_results['summary']['enhanced_asr_videos']}")
    
    # Show individual results
    for video_id, result in batch_results['video_results'].items():
        status = "[SUCCESS]" if result['success'] else "[FAILED]"
        method = result.get('method', 'unknown')
        chunks = result.get('chunks_count', 0)
        
        print(f"   {status} {video_id}: {method} ({chunks} chunks)")
        
        # Show speaker info if available
        if result.get('speaker_metadata'):
            speaker_meta = result['speaker_metadata']
            chaffee_pct = speaker_meta.get('chaffee_percentage', 0)
            unknown_segs = speaker_meta.get('unknown_segments', 0)
            
            if chaffee_pct > 0:
                print(f"      [SPEAKER] Chaffee: {chaffee_pct:.1f}%, Unknown segments: {unknown_segs}")
        
        if result.get('error'):
            print(f"      [ERROR] Error: {result['error']}")
    
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
