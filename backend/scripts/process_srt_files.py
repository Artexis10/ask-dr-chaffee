#!/usr/bin/env python3
"""
Process SRT caption files exported from YouTube Studio
"""

import os
import re
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.transcript_common import TranscriptSegment
from scripts.common.database_upsert import DatabaseUpserter
from scripts.common.embedding_generator import EmbeddingGenerator
from scripts.common.transcript_processor import TranscriptProcessor, ChunkData

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class SRTEntry:
    """Single SRT subtitle entry"""
    index: int
    start_time: float
    end_time: float
    text: str

class SRTProcessor:
    """Process SRT files exported from YouTube Studio"""
    
    def __init__(self, db_url: str = None):
        self.db = DatabaseUpserter(db_url) if db_url else None
        self.embedder = EmbeddingGenerator()
        self.processor = TranscriptProcessor(
            chunk_duration_seconds=int(os.getenv('CHUNK_DURATION_SECONDS', 45))
        )
    
    def parse_srt_file(self, srt_path: Path) -> List[TranscriptSegment]:
        """Parse SRT file into transcript segments"""
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split by double newlines to get subtitle blocks
            blocks = re.split(r'\n\s*\n', content.strip())
            segments = []
            
            for block in blocks:
                if not block.strip():
                    continue
                
                lines = block.strip().split('\n')
                if len(lines) < 3:
                    continue
                
                # Parse subtitle index
                try:
                    index = int(lines[0])
                except ValueError:
                    continue
                
                # Parse time range
                time_match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})', lines[1])
                if not time_match:
                    continue
                
                # Convert to seconds
                start_time = (
                    int(time_match.group(1)) * 3600 +  # hours
                    int(time_match.group(2)) * 60 +    # minutes
                    int(time_match.group(3)) +         # seconds
                    int(time_match.group(4)) / 1000    # milliseconds
                )
                
                end_time = (
                    int(time_match.group(5)) * 3600 +  # hours
                    int(time_match.group(6)) * 60 +    # minutes
                    int(time_match.group(7)) +         # seconds
                    int(time_match.group(8)) / 1000    # milliseconds
                )
                
                # Get text content (may span multiple lines)
                text = ' '.join(lines[2:])
                # Clean up HTML tags and formatting
                text = re.sub(r'<[^>]+>', '', text)
                text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                text = text.strip()
                
                if text:
                    segments.append(TranscriptSegment(
                        start=start_time,
                        end=end_time,
                        text=text
                    ))
            
            logger.info(f"Parsed {len(segments)} segments from {srt_path.name}")
            return segments
            
        except Exception as e:
            logger.error(f"Error parsing SRT file {srt_path}: {e}")
            return []
    
    def extract_video_id_from_filename(self, filename: str) -> Optional[str]:
        """Extract video ID from SRT filename"""
        # Common YouTube SRT filename patterns:
        # video_id.srt
        # video_title_video_id.srt  
        # video_id_en.srt
        
        name = Path(filename).stem
        
        # Try to find 11-character YouTube video ID pattern
        video_id_match = re.search(r'([a-zA-Z0-9_-]{11})', name)
        if video_id_match:
            return video_id_match.group(1)
        
        # Fallback: use filename as video ID and let user correct
        logger.warning(f"Could not extract video ID from filename: {filename}")
        return name
    
    def process_srt_file(self, srt_path: Path, video_id: str = None, video_title: str = None) -> bool:
        """Process single SRT file into database"""
        try:
            # Extract video ID if not provided
            if not video_id:
                video_id = self.extract_video_id_from_filename(srt_path.name)
                if not video_id:
                    logger.error(f"Could not determine video ID for {srt_path.name}")
                    return False
            
            logger.info(f"Processing {srt_path.name} as video ID: {video_id}")
            
            # Parse SRT file
            segments = self.parse_srt_file(srt_path)
            if not segments:
                logger.error(f"No segments found in {srt_path.name}")
                return False
            
            # Process transcript into chunks
            chunks = []
            for segment in segments:
                chunk = ChunkData.from_transcript_segment(segment, video_id)
                chunks.append(chunk)
            
            logger.info(f"Created {len(chunks)} chunks from transcript")
            
            if self.db:
                # Generate embeddings
                texts = [chunk.text for chunk in chunks]
                embeddings = self.embedder.generate_embeddings(texts)
                
                # Attach embeddings to chunks
                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding
                
                # Create video info for database
                from scripts.common.list_videos_api import VideoInfo
                video = VideoInfo(
                    video_id=video_id,
                    title=video_title or f"Video {video_id}",
                    description="Processed from SRT file",
                    published_at=datetime.now(),
                    duration_seconds=int(segments[-1].end) if segments else 0,
                    view_count=0,
                    like_count=0,
                    comment_count=0,
                    channel_title="Dr. Anthony Chaffee"
                )
                
                # Upsert to database
                source_id = self.db.upsert_source(video, source_type='youtube')
                
                # Update chunks with correct source_id
                for chunk in chunks:
                    chunk.source_id = source_id
                
                chunk_count = self.db.upsert_chunks(chunks)
                logger.info(f"✅ Inserted {chunk_count} chunks for video {video_id}")
            else:
                # Just show what would be processed
                logger.info(f"DRY RUN: Would insert {len(chunks)} chunks for video {video_id}")
                for i, chunk in enumerate(chunks[:3]):  # Show first 3
                    logger.info(f"  Chunk {i+1}: {chunk.text[:100]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing {srt_path.name}: {e}")
            return False
    
    def process_directory(self, directory: Path, dry_run: bool = False) -> None:
        """Process all SRT files in a directory"""
        srt_files = list(directory.glob("*.srt"))
        
        if not srt_files:
            logger.error(f"No SRT files found in {directory}")
            return
        
        logger.info(f"Found {len(srt_files)} SRT files to process")
        
        if dry_run:
            logger.info("DRY RUN mode - no database operations")
        
        processed = 0
        failed = 0
        
        for srt_file in srt_files:
            logger.info(f"Processing {srt_file.name}...")
            
            if not dry_run and self.process_srt_file(srt_file):
                processed += 1
            elif dry_run:
                # Just parse and show info
                segments = self.parse_srt_file(srt_file)
                video_id = self.extract_video_id_from_filename(srt_file.name)
                logger.info(f"  Video ID: {video_id}, Segments: {len(segments)}")
                processed += 1
            else:
                failed += 1
        
        logger.info(f"Processing complete: {processed} successful, {failed} failed")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Process SRT caption files from YouTube Studio',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all SRT files in a directory
  python process_srt_files.py /path/to/captions/

  # Dry run to see what would be processed
  python process_srt_files.py /path/to/captions/ --dry-run

  # Process single SRT file with specific video ID
  python process_srt_files.py video.srt --video-id "dQw4w9WgXcQ"
        """
    )
    
    parser.add_argument('path', help='Path to SRT file or directory containing SRT files')
    parser.add_argument('--video-id', help='Video ID (for single file processing)')
    parser.add_argument('--video-title', help='Video title (for single file processing)')
    parser.add_argument('--dry-run', action='store_true', help='Parse files but don\'t insert into database')
    parser.add_argument('--db-url', help='Database URL (default: from environment)')
    
    args = parser.parse_args()
    
    # Initialize processor
    db_url = args.db_url if not args.dry_run else None
    processor = SRTProcessor(db_url)
    
    path = Path(args.path)
    
    if path.is_file():
        # Process single file
        if not path.suffix.lower() == '.srt':
            logger.error("File must have .srt extension")
            return 1
        
        success = processor.process_srt_file(path, args.video_id, args.video_title)
        return 0 if success else 1
    
    elif path.is_dir():
        # Process directory
        processor.process_directory(path, args.dry_run)
        return 0
    
    else:
        logger.error(f"Path does not exist: {path}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
