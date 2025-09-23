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

# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import existing ingestion components
from backend.scripts.common.database import get_db_connection
from backend.scripts.common.database_upsert import DatabaseUpserter
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
                 source_type: str = "youtube_enhanced"):
        
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
        self.db_upserter = DatabaseUpserter()
        
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
                    embedding = self.embedding_generator.generate_embedding(chunk['text'])
                    chunk['embedding'] = embedding
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for chunk {chunk['chunk_index']}: {e}")
                    chunk['embedding'] = None
            
            # Prepare source metadata
            source_metadata = {
                'video_id': video_id,
                'method': method,
                'segments_count': len(segments),
                'processing_timestamp': metadata.get('timestamp'),
            }
            
            # Add Enhanced ASR metadata
            if metadata.get('enhanced_asr_used'):
                source_metadata.update({
                    'enhanced_asr': True,
                    'speaker_identification': True,
                    'chaffee_percentage': metadata.get('chaffee_percentage', 0.0),
                    'speaker_distribution': metadata.get('speaker_distribution', {}),
                    'confidence_stats': metadata.get('confidence_stats', {}),
                    'monologue_detected': method.endswith('_monologue')
                })
            
            # Upsert to database
            logger.info(f"Upserting {len(chunks)} chunks to database")
            
            # Create source entry
            source_data = {
                'title': f"YouTube Video {video_id}",  # Could be enhanced with actual title
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'content_type': 'video',
                'metadata': source_metadata
            }
            
            source_id = self.db_upserter.upsert_source(source_data, source_type=self.source_type)
            
            # Upsert chunks
            for chunk in chunks:
                if chunk['embedding'] is not None:
                    chunk_data = {
                        'source_id': source_id,
                        'chunk_index': chunk['chunk_index'],
                        'start_time_seconds': chunk['start_time_seconds'],
                        'end_time_seconds': chunk['end_time_seconds'],
                        'text': chunk['text'],
                        'word_count': chunk['word_count'],
                        'embedding': chunk['embedding']
                    }
                    
                    # Add speaker metadata to chunk if available
                    chunk_metadata = {}
                    if 'speaker_metadata' in chunk:
                        chunk_metadata['speaker'] = chunk['speaker_metadata']
                    
                    if metadata.get('enhanced_asr_used'):
                        chunk_metadata['enhanced_asr'] = True
                    
                    if chunk_metadata:
                        chunk_data['metadata'] = chunk_metadata
                    
                    self.db_upserter.upsert_chunk(chunk_data)
            
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
    parser.add_argument('--source-type', default='youtube_enhanced',
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
            print("❌ Chaffee voice profile setup failed")
            return 1
    
    # Check Enhanced ASR status
    asr_status = ingestion.transcript_fetcher.get_enhanced_asr_status()
    print(f"🎤 Enhanced ASR Status:")
    print(f"   Enabled: {asr_status['enabled']}")
    print(f"   Available: {asr_status['available']}")
    print(f"   Voice Profiles: {asr_status['voice_profiles']}")
    
    if not asr_status['available'] and args.enable_speaker_id:
        print("⚠️  Enhanced ASR not available - install dependencies:")
        print("   pip install whisperx pyannote.audio speechbrain")
    
    # Process videos
    print(f"\n🎬 Processing {len(args.video_ids)} videos...")
    
    batch_results = ingestion.process_video_batch(
        video_ids=args.video_ids,
        force_enhanced_asr=args.force_enhanced_asr
    )
    
    # Print results
    print(f"\n📊 Processing Results:")
    print(f"   Successful: {batch_results['successful']}/{batch_results['total_videos']}")
    print(f"   Failed: {batch_results['failed']}/{batch_results['total_videos']}")
    print(f"   Total chunks: {batch_results['summary']['total_chunks_processed']}")
    print(f"   Enhanced ASR videos: {batch_results['summary']['enhanced_asr_videos']}")
    
    # Show individual results
    for video_id, result in batch_results['video_results'].items():
        status = "✅" if result['success'] else "❌"
        method = result.get('method', 'unknown')
        chunks = result.get('chunks_count', 0)
        
        print(f"   {status} {video_id}: {method} ({chunks} chunks)")
        
        # Show speaker info if available
        if result.get('speaker_metadata'):
            speaker_meta = result['speaker_metadata']
            chaffee_pct = speaker_meta.get('chaffee_percentage', 0)
            unknown_segs = speaker_meta.get('unknown_segments', 0)
            
            if chaffee_pct > 0:
                print(f"      🎯 Chaffee: {chaffee_pct:.1f}%, Unknown segments: {unknown_segs}")
        
        if result.get('error'):
            print(f"      ❌ Error: {result['error']}")
    
    # Save results if requested
    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(batch_results, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {args.output}")
    
    # Return appropriate exit code
    return 0 if batch_results['failed'] == 0 else 1

if __name__ == '__main__':
    exit(main())
