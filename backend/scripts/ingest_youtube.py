#!/usr/bin/env python3
"""
YouTube transcript ingestion script for Ask Dr. Chaffee.

This script:
1. Fetches videos from Dr. Anthony Chaffee's YouTube channel
2. Downloads transcripts using youtube-transcript-api or faster-whisper fallback
3. Chunks transcripts into 45-60 second segments
4. Generates embeddings using sentence-transformers
5. Stores in Postgres database with pgvector
"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import json

# Third-party imports
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.database import DatabaseManager
from scripts.common.embeddings import EmbeddingGenerator
from scripts.common.transcript_processor import TranscriptProcessor

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_ingestion.log')
    ]
)
logger = logging.getLogger(__name__)

class YouTubeIngester:
    def __init__(self):
        self.db = DatabaseManager()
        self.embedder = EmbeddingGenerator()
        self.processor = TranscriptProcessor(
            chunk_duration_seconds=int(os.getenv('CHUNK_DURATION_SECONDS', 45))
        )
        self.channel_url = "https://www.youtube.com/@anthonychaffeemd"
        
        # yt-dlp options
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Don't download, just get metadata
        }
    
    def get_channel_videos(self, max_videos: int = 50) -> List[Dict[str, Any]]:
        """Fetch video metadata from the YouTube channel"""
        logger.info(f"Fetching videos from {self.channel_url}")
        
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            try:
                # Extract channel info and video list
                channel_info = ydl.extract_info(
                    self.channel_url,
                    download=False
                )
                
                videos = []
                entries = channel_info.get('entries', [])[:max_videos]
                
                for entry in entries:
                    video_id = entry.get('id')
                    if not video_id:
                        continue
                    
                    # Get detailed video info
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    video_info = ydl.extract_info(video_url, download=False)
                    
                    videos.append({
                        'id': video_id,
                        'title': video_info.get('title', ''),
                        'description': video_info.get('description', ''),
                        'duration': video_info.get('duration'),
                        'upload_date': video_info.get('upload_date'),
                        'url': video_url,
                        'view_count': video_info.get('view_count'),
                        'like_count': video_info.get('like_count'),
                    })
                
                logger.info(f"Found {len(videos)} videos")
                return videos
                
            except Exception as e:
                logger.error(f"Error fetching channel videos: {e}")
                return []
    
    def get_transcript(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get transcript for a video, trying multiple methods"""
        
        # Method 1: Try YouTube's auto-generated transcript
        try:
            logger.info(f"Attempting to fetch YouTube transcript for {video_id}")
            api = YouTubeTranscriptApi()
            transcript_data = api.fetch(video_id, languages=['en'])
            # transcript_data is a FetchedTranscript object, iterate over it
            transcript_list = []
            for entry in transcript_data:
                transcript_list.append({
                    'start': entry['start'],
                    'duration': entry['duration'], 
                    'text': entry['text']
                })
            logger.info(f"Successfully fetched YouTube transcript ({len(transcript_list)} entries)")
            return transcript_list
            
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            logger.warning(f"No YouTube transcript available for {video_id}: {e}")
            
        # Method 2: Fallback to faster-whisper (requires audio download)
        try:
            logger.info(f"Attempting Whisper transcription for {video_id}")
            transcript = self._transcribe_with_whisper(video_id)
            if transcript:
                logger.info(f"Successfully transcribed with Whisper ({len(transcript)} entries)")
                return transcript
                
        except Exception as e:
            logger.error(f"Whisper transcription failed for {video_id}: {e}")
        
        logger.error(f"All transcript methods failed for {video_id}")
        return None
    
    def _transcribe_with_whisper(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """Transcribe video using faster-whisper (fallback method)"""
        try:
            from faster_whisper import WhisperModel
            import tempfile
            
            # Download audio
            audio_path = self._download_audio(video_id)
            if not audio_path:
                return None
            
            # Initialize Whisper model
            model = WhisperModel("base", device="cpu", compute_type="int8")
            
            # Transcribe
            segments, info = model.transcribe(audio_path, beam_size=5)
            
            transcript = []
            for segment in segments:
                transcript.append({
                    'start': segment.start,
                    'duration': segment.end - segment.start,
                    'text': segment.text.strip()
                })
            
            # Clean up audio file
            os.unlink(audio_path)
            
            return transcript
            
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return None
    
    def _download_audio(self, video_id: str) -> Optional[str]:
        """Download audio for transcription"""
        try:
            import tempfile
            
            temp_dir = tempfile.mkdtemp()
            audio_path = os.path.join(temp_dir, f"{video_id}.mp3")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': audio_path,
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                ydl.download([video_url])
            
            return audio_path if os.path.exists(audio_path) else None
            
        except Exception as e:
            logger.error(f"Audio download error: {e}")
            return None
    
    def process_video(self, video_info: Dict[str, Any]) -> bool:
        """Process a single video: get transcript, chunk, embed, and store"""
        video_id = video_info['id']
        
        # Check if already processed
        if self.db.source_exists('youtube', video_id):
            logger.info(f"Video {video_id} already processed, skipping")
            return True
        
        logger.info(f"Processing video: {video_info['title']}")
        
        # Get transcript
        transcript = self.get_transcript(video_id)
        if not transcript:
            logger.error(f"Could not get transcript for {video_id}")
            return False
        
        # Parse upload date
        upload_date = None
        if video_info.get('upload_date'):
            try:
                upload_date = datetime.strptime(
                    video_info['upload_date'], 
                    '%Y%m%d'
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        
        # Store source in database
        source_db_id = self.db.insert_source(
            source_type='youtube',
            source_id=video_id,
            title=video_info['title'],
            description=video_info.get('description'),
            duration_seconds=video_info.get('duration'),
            published_at=upload_date,
            url=video_info['url'],
            metadata={
                'view_count': video_info.get('view_count'),
                'like_count': video_info.get('like_count'),
            }
        )
        
        # Chunk transcript
        chunks = self.processor.chunk_transcript(transcript)
        
        # Store chunks
        self.db.insert_chunks(source_db_id, chunks)
        
        logger.info(f"Successfully processed video {video_id}")
        return True
    
    def generate_embeddings(self):
        """Generate embeddings for all chunks without embeddings"""
        logger.info("Generating embeddings for chunks...")
        
        chunks_to_embed = self.db.get_sources_without_embeddings()
        if not chunks_to_embed:
            logger.info("No chunks need embeddings")
            return
        
        logger.info(f"Generating embeddings for {len(chunks_to_embed)} chunks")
        
        # Process in batches
        batch_size = 100
        for i in range(0, len(chunks_to_embed), batch_size):
            batch = chunks_to_embed[i:i + batch_size]
            texts = [chunk['text'] for chunk in batch]
            
            # Generate embeddings
            embeddings = self.embedder.generate_embeddings(texts)
            
            # Update database
            for chunk, embedding in zip(batch, embeddings):
                self.db.update_chunk_embedding(chunk['id'], embedding)
            
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(chunks_to_embed) + batch_size - 1)//batch_size}")
    
    def run(self, max_videos: int = 50):
        """Run the full ingestion pipeline"""
        logger.info("Starting YouTube ingestion pipeline")
        
        try:
            # Get videos from channel
            videos = self.get_channel_videos(max_videos)
            if not videos:
                logger.error("No videos found")
                return
            
            # Process each video
            processed_count = 0
            for video in videos:
                if self.process_video(video):
                    processed_count += 1
            
            logger.info(f"Processed {processed_count}/{len(videos)} videos")
            
            # Generate embeddings
            self.generate_embeddings()
            
            logger.info("YouTube ingestion pipeline completed successfully")
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ingest YouTube transcripts for Ask Dr. Chaffee')
    parser.add_argument('--max-videos', type=int, default=50, 
                       help='Maximum number of videos to process')
    parser.add_argument('--video-id', type=str, 
                       help='Process specific video ID only')
    
    args = parser.parse_args()
    
    ingester = YouTubeIngester()
    
    if args.video_id:
        # Process single video
        video_info = {
            'id': args.video_id,
            'title': f'Video {args.video_id}',
            'url': f'https://www.youtube.com/watch?v={args.video_id}'
        }
        success = ingester.process_video(video_info)
        if success:
            ingester.generate_embeddings()
        sys.exit(0 if success else 1)
    else:
        # Process channel
        ingester.run(args.max_videos)

if __name__ == '__main__':
    main()
