#!/usr/bin/env python3
"""
Enhanced YouTube transcript ingestion pipeline with speaker identification:
1. youtube-transcript-api (cheap, fast)
2. yt-dlp subtitles (with proxy support)  
3. Enhanced ASR with speaker identification (if enabled)

All results are normalized, chunked, embedded, and stored with speaker metadata.
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import your existing ingestion components
from backend.scripts.common.database import get_db_connection
from backend.scripts.common.transcript_processor import TranscriptProcessor
from backend.scripts.common.embeddings import EmbeddingGenerator

# Import Enhanced ASR components
from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher

logger = logging.getLogger(__name__)

class EnhancedYouTubeIngestion:
    """Enhanced YouTube ingestion with optional speaker identification"""
    
    def __init__(self, enable_speaker_id=False, voices_dir="voices"):
        self.enable_speaker_id = enable_speaker_id
        self.voices_dir = voices_dir
        
        # Initialize components
        self.transcript_fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=enable_speaker_id,
            voices_dir=voices_dir,
            api_key=os.getenv('YOUTUBE_API_KEY')
        )
        
        self.transcript_processor = TranscriptProcessor()
        self.embedding_generator = EmbeddingGenerator()
        
        # Database connection
        self.db = get_db_connection()
        
        logger.info(f"Enhanced ingestion initialized (speaker_id={enable_speaker_id})")
    
    def process_video(self, video_id: str) -> dict:
        """Process a single video with optional speaker identification"""
        try:
            logger.info(f"Processing video: {video_id}")
            
            # Step 1: Get transcript with optional speaker identification
            segments = self.transcript_fetcher.get_transcript(video_id)
            
            if not segments:
                logger.error(f"Failed to get transcript for {video_id}")
                return {"video_id": video_id, "success": False, "error": "No transcript"}
            
            # Step 2: Process and chunk segments
            chunks = self.transcript_processor.process_segments(segments, video_id)
            
            # Step 3: Generate embeddings
            embedded_chunks = []
            for chunk in chunks:
                embedding = self.embedding_generator.generate_embedding(chunk['text'])
                chunk['embedding'] = embedding
                embedded_chunks.append(chunk)
            
            # Step 4: Store in database with speaker metadata
            self._store_segments_with_speakers(video_id, segments)
            self._store_chunks_with_embeddings(embedded_chunks)
            
            # Step 5: Update video metadata
            self._update_video_metadata(video_id, segments)
            
            logger.info(f"✅ Successfully processed {video_id}")
            return {
                "video_id": video_id, 
                "success": True, 
                "segments": len(segments),
                "chunks": len(embedded_chunks),
                "speaker_id_enabled": self.enable_speaker_id
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to process {video_id}: {e}")
            return {"video_id": video_id, "success": False, "error": str(e)}
    
    def _store_segments_with_speakers(self, video_id: str, segments):
        """Store transcript segments with speaker information"""
        # Check if speaker columns exist, create if needed
        self._ensure_speaker_columns()
        
        # Store segments
        for segment in segments:
            speaker = getattr(segment, 'speaker', None)
            speaker_confidence = getattr(segment, 'speaker_confidence', None)
            
            self.db.execute("""
                INSERT OR REPLACE INTO transcript_segments 
                (video_id, start_time, end_time, text, speaker, speaker_confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                video_id, 
                segment.start, 
                segment.end, 
                segment.text,
                speaker,
                speaker_confidence
            ))
        
        self.db.commit()
    
    def _store_chunks_with_embeddings(self, chunks):
        """Store processed chunks with embeddings"""
        for chunk in chunks:
            # Convert embedding to blob for storage
            embedding_blob = chunk['embedding'].tobytes() if chunk['embedding'] is not None else None
            
            self.db.execute("""
                INSERT OR REPLACE INTO transcript_chunks
                (video_id, chunk_index, start_time, end_time, text, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                chunk['video_id'],
                chunk['chunk_index'],
                chunk['start_time'],
                chunk['end_time'],
                chunk['text'],
                embedding_blob
            ))
        
        self.db.commit()
    
    def _update_video_metadata(self, video_id: str, segments):
        """Update video metadata with processing information"""
        speaker_stats = {}
        if self.enable_speaker_id:
            # Calculate speaker distribution
            for segment in segments:
                speaker = getattr(segment, 'speaker', 'Unknown')
                if speaker not in speaker_stats:
                    speaker_stats[speaker] = {'count': 0, 'duration': 0}
                speaker_stats[speaker]['count'] += 1
                speaker_stats[speaker]['duration'] += (segment.end - segment.start)
        
        self.db.execute("""
            UPDATE videos SET 
                has_enhanced_transcript = ?,
                speaker_stats = ?,
                processed_at = datetime('now')
            WHERE id = ?
        """, (
            1 if self.enable_speaker_id else 0,
            json.dumps(speaker_stats) if speaker_stats else None,
            video_id
        ))
        
        self.db.commit()
    
    def _ensure_speaker_columns(self):
        """Ensure database has speaker-related columns"""
        try:
            # Add speaker columns to transcript_segments if they don't exist
            self.db.execute("ALTER TABLE transcript_segments ADD COLUMN speaker TEXT")
        except:
            pass  # Column already exists
        
        try:
            self.db.execute("ALTER TABLE transcript_segments ADD COLUMN speaker_confidence REAL")
        except:
            pass  # Column already exists
        
        try:
            # Add enhanced transcript flag to videos table
            self.db.execute("ALTER TABLE videos ADD COLUMN has_enhanced_transcript INTEGER DEFAULT 0")
        except:
            pass  # Column already exists
        
        try:
            self.db.execute("ALTER TABLE videos ADD COLUMN speaker_stats TEXT")
        except:
            pass  # Column already exists


def main():
    parser = argparse.ArgumentParser(description='Enhanced YouTube ingestion with speaker identification')
    
    # Video processing
    parser.add_argument('video_ids', nargs='+', help='YouTube video IDs to process')
    
    # Enhanced ASR options
    parser.add_argument('--enable-speaker-id', action='store_true', default=False,
                       help='Enable speaker identification (requires Dr. Chaffee voice profile)')
    parser.add_argument('--voices-dir', default='voices', help='Voice profiles directory')
    
    # General options
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--batch-size', type=int, default=5, help='Batch processing size')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Initialize enhanced ingestion
    ingestion = EnhancedYouTubeIngestion(
        enable_speaker_id=args.enable_speaker_id,
        voices_dir=args.voices_dir
    )
    
    # Process videos
    results = []
    for video_id in args.video_ids:
        result = ingestion.process_video(video_id)
        results.append(result)
        
        # Print progress
        if result['success']:
            speaker_info = f" (speaker ID: {result['speaker_id_enabled']})" if args.enable_speaker_id else ""
            print(f"✅ {video_id}: {result['segments']} segments, {result['chunks']} chunks{speaker_info}")
        else:
            print(f"❌ {video_id}: {result['error']}")
    
    # Summary
    successful = sum(1 for r in results if r['success'])
    total = len(results)
    print(f"\n📊 Summary: {successful}/{total} videos processed successfully")
    
    if args.enable_speaker_id:
        print("🎤 Speaker identification was enabled")


if __name__ == '__main__':
    main()
