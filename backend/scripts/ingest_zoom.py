#!/usr/bin/env python3
"""
Zoom transcript ingestion script for Ask Dr. Chaffee.

This script:
1. Connects to Zoom API to fetch cloud recordings
2. Downloads VTT transcript files
3. Processes VTT format into chunks
4. Generates embeddings and stores in database
"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import requests
import json
import base64

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.database import DatabaseManager
from scripts.common.embeddings import EmbeddingGenerator
from scripts.common.transcript_processor import TranscriptProcessor

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('zoom_ingestion.log')
    ]
)
logger = logging.getLogger(__name__)

class ZoomIngester:
    def __init__(self):
        self.db = DatabaseManager()
        self.embedder = EmbeddingGenerator()
        self.processor = TranscriptProcessor(
            chunk_duration_seconds=int(os.getenv('CHUNK_DURATION_SECONDS', 45))
        )
        
        # Zoom API credentials
        self.account_id = os.getenv('ZOOM_ACCOUNT_ID')
        self.client_id = os.getenv('ZOOM_CLIENT_ID')
        self.client_secret = os.getenv('ZOOM_CLIENT_SECRET')
        
        if not all([self.account_id, self.client_id, self.client_secret]):
            raise ValueError("Zoom API credentials (ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET) are required")
        
        self.access_token = None
    
    def get_access_token(self) -> str:
        """Get OAuth access token for Zoom API"""
        if self.access_token:
            return self.access_token
        
        logger.info("Getting Zoom OAuth access token")
        
        # Prepare credentials for basic auth
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'account_credentials',
            'account_id': self.account_id
        }
        
        response = requests.post(
            'https://zoom.us/oauth/token',
            headers=headers,
            data=data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get access token: {response.text}")
        
        token_data = response.json()
        self.access_token = token_data['access_token']
        
        logger.info("Successfully obtained Zoom access token")
        return self.access_token
    
    def get_cloud_recordings(self, user_id: str = 'me', from_date: str = None, to_date: str = None) -> List[Dict[str, Any]]:
        """Get cloud recordings from Zoom"""
        token = self.get_access_token()
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        params = {
            'page_size': 300,  # Max allowed
            'mc': 'false'  # Don't include meeting chat
        }
        
        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date
        
        recordings = []
        next_page_token = None
        
        while True:
            if next_page_token:
                params['next_page_token'] = next_page_token
            
            response = requests.get(
                f'https://api.zoom.us/v2/users/{user_id}/recordings',
                headers=headers,
                params=params
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get recordings: {response.text}")
                break
            
            data = response.json()
            meetings = data.get('meetings', [])
            recordings.extend(meetings)
            
            next_page_token = data.get('next_page_token')
            if not next_page_token:
                break
        
        logger.info(f"Found {len(recordings)} cloud recordings")
        return recordings
    
    def download_vtt_transcript(self, recording_file: Dict[str, Any]) -> Optional[str]:
        """Download VTT transcript file"""
        download_url = recording_file.get('download_url')
        if not download_url:
            return None
        
        token = self.get_access_token()
        
        headers = {
            'Authorization': f'Bearer {token}'
        }
        
        try:
            response = requests.get(download_url, headers=headers)
            if response.status_code == 200:
                return response.text
            else:
                logger.warning(f"Failed to download transcript: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error downloading transcript: {e}")
            return None
    
    def process_zoom_meeting(self, meeting: Dict[str, Any]) -> bool:
        """Process a single Zoom meeting with transcripts"""
        meeting_id = meeting.get('uuid', meeting.get('id', ''))
        meeting_topic = meeting.get('topic', 'Untitled Meeting')
        
        # Check if already processed
        if self.db.source_exists('zoom', meeting_id):
            logger.info(f"Meeting {meeting_id} already processed, skipping")
            return True
        
        logger.info(f"Processing meeting: {meeting_topic}")
        
        # Find VTT transcript files
        recording_files = meeting.get('recording_files', [])
        transcript_files = [
            f for f in recording_files 
            if f.get('file_type') == 'TRANSCRIPT' and f.get('file_extension') == 'VTT'
        ]
        
        if not transcript_files:
            logger.warning(f"No VTT transcript found for meeting {meeting_id}")
            return False
        
        # Process first VTT file (usually there's only one)
        transcript_file = transcript_files[0]
        
        # Download transcript content
        vtt_content = self.download_vtt_transcript(transcript_file)
        if not vtt_content:
            logger.error(f"Could not download transcript for meeting {meeting_id}")
            return False
        
        # Process VTT content into transcript entries
        transcript_entries = self.processor.chunk_vtt_transcript(vtt_content)
        if not transcript_entries:
            logger.error(f"Could not process VTT transcript for meeting {meeting_id}")
            return False
        
        # Parse meeting date
        start_time = None
        if meeting.get('start_time'):
            try:
                start_time = datetime.fromisoformat(
                    meeting['start_time'].replace('Z', '+00:00')
                )
            except ValueError:
                pass
        
        # Calculate duration from transcript
        duration_seconds = None
        if transcript_entries:
            last_entry = transcript_entries[-1]
            duration_seconds = int(last_entry['start'] + last_entry['duration'])
        
        # Store source in database
        source_db_id = self.db.insert_source(
            source_type='zoom',
            source_id=meeting_id,
            title=meeting_topic,
            description=f"Zoom recording from {meeting.get('start_time', 'unknown date')}",
            duration_seconds=duration_seconds,
            published_at=start_time,
            url=meeting.get('share_url'),
            metadata={
                'host_email': meeting.get('host_email'),
                'participant_count': meeting.get('participant_count'),
                'recording_count': len(recording_files),
                'file_size': transcript_file.get('file_size'),
            }
        )
        
        # Chunk transcript
        chunks = self.processor.chunk_transcript(transcript_entries)
        
        # Store chunks
        self.db.insert_chunks(source_db_id, chunks)
        
        logger.info(f"Successfully processed meeting {meeting_id}")
        return True
    
    def process_local_vtt_file(self, file_path: str, meeting_title: str = None) -> bool:
        """Process a local VTT file (for manual uploads)"""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        
        logger.info(f"Processing local VTT file: {file_path}")
        
        # Generate a unique ID for this file
        file_id = f"local_{os.path.basename(file_path)}_{int(datetime.now().timestamp())}"
        
        # Check if already processed
        if self.db.source_exists('zoom', file_id):
            logger.info(f"File {file_path} already processed, skipping")
            return True
        
        # Read VTT content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                vtt_content = f.read()
        except Exception as e:
            logger.error(f"Error reading VTT file: {e}")
            return False
        
        # Process VTT content
        transcript_entries = self.processor.chunk_vtt_transcript(vtt_content)
        if not transcript_entries:
            logger.error(f"Could not process VTT transcript from {file_path}")
            return False
        
        # Calculate duration
        duration_seconds = None
        if transcript_entries:
            last_entry = transcript_entries[-1]
            duration_seconds = int(last_entry['start'] + last_entry['duration'])
        
        # Use provided title or generate from filename
        title = meeting_title or f"Local Recording: {os.path.splitext(os.path.basename(file_path))[0]}"
        
        # Store source
        source_db_id = self.db.insert_source(
            source_type='zoom',
            source_id=file_id,
            title=title,
            description=f"Local VTT file: {file_path}",
            duration_seconds=duration_seconds,
            published_at=datetime.now(timezone.utc),
            url=None,
            metadata={
                'source_file': file_path,
                'file_size': os.path.getsize(file_path),
            }
        )
        
        # Chunk and store
        chunks = self.processor.chunk_transcript(transcript_entries)
        self.db.insert_chunks(source_db_id, chunks)
        
        logger.info(f"Successfully processed local VTT file: {file_path}")
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
    
    def run(self, from_date: str = None, to_date: str = None):
        """Run the full Zoom ingestion pipeline"""
        logger.info("Starting Zoom ingestion pipeline")
        
        try:
            # Get cloud recordings
            recordings = self.get_cloud_recordings(from_date=from_date, to_date=to_date)
            if not recordings:
                logger.warning("No cloud recordings found")
                return
            
            # Process each recording
            processed_count = 0
            for meeting in recordings:
                if self.process_zoom_meeting(meeting):
                    processed_count += 1
            
            logger.info(f"Processed {processed_count}/{len(recordings)} meetings")
            
            # Generate embeddings
            self.generate_embeddings()
            
            logger.info("Zoom ingestion pipeline completed successfully")
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ingest Zoom transcripts for Ask Dr. Chaffee')
    parser.add_argument('--from-date', type=str, 
                       help='Start date for recordings (YYYY-MM-DD)')
    parser.add_argument('--to-date', type=str,
                       help='End date for recordings (YYYY-MM-DD)')
    parser.add_argument('--local-file', type=str,
                       help='Process local VTT file instead of API')
    parser.add_argument('--title', type=str,
                       help='Title for local file processing')
    
    args = parser.parse_args()
    
    ingester = ZoomIngester()
    
    if args.local_file:
        # Process local file
        success = ingester.process_local_vtt_file(args.local_file, args.title)
        if success:
            ingester.generate_embeddings()
        sys.exit(0 if success else 1)
    else:
        # Process cloud recordings
        ingester.run(args.from_date, args.to_date)

if __name__ == '__main__':
    main()
