#!/usr/bin/env python3
"""
YouTube transcript fetching using official YouTube Data API v3
"""

import os
import logging
import json
import base64
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

from .transcript_fetch import TranscriptSegment

logger = logging.getLogger(__name__)

class YouTubeTranscriptAPI:
    """Fetch transcripts using YouTube Data API v3"""
    
    def __init__(self, api_key: str):
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API client not available. Install with: "
                "pip install google-api-python-client"
            )
        
        self.api_key = api_key
        self.youtube = build('youtube', 'v3', developerKey=api_key)
    
    def list_captions(self, video_id: str) -> List[Dict[str, Any]]:
        """List available captions for a video"""
        try:
            request = self.youtube.captions().list(
                part="snippet",
                videoId=video_id
            )
            response = request.execute()
            
            return response.get('items', [])
        except HttpError as e:
            if e.resp.status == 403:
                logger.warning(f"No permission to access captions for {video_id}")
                return []
            logger.error(f"API error listing captions for {video_id}: {e}")
            return []
    
    def download_caption(self, caption_id: str) -> Optional[str]:
        """Download a specific caption track"""
        try:
            request = self.youtube.captions().download(
                id=caption_id,
                tfmt="srt"  # Use SRT format for easy parsing
            )
            
            # Execute request and get binary response
            response = request.execute()
            
            # Response is base64-encoded
            if isinstance(response, bytes):
                return response.decode('utf-8')
            return response
        except HttpError as e:
            logger.error(f"API error downloading caption {caption_id}: {e}")
            return None
    
    def get_transcript_segments(self, video_id: str, language_code: str = "en") -> List[TranscriptSegment]:
        """Get transcript segments for a video in the specified language"""
        # List available captions
        captions = self.list_captions(video_id)
        if not captions:
            logger.warning(f"No captions found for video {video_id}")
            return []
        
        # Find caption in requested language
        caption_id = None
        for caption in captions:
            track_language = caption['snippet']['language']
            is_auto = caption['snippet'].get('trackKind') == 'ASR'
            
            # Prefer manual captions in the requested language
            if track_language == language_code and not is_auto:
                caption_id = caption['id']
                break
            
            # Fall back to auto-generated captions
            if track_language == language_code and is_auto and caption_id is None:
                caption_id = caption['id']
        
        if caption_id is None:
            logger.warning(f"No {language_code} captions found for video {video_id}")
            return []
        
        # Download and parse caption
        caption_content = self.download_caption(caption_id)
        if not caption_content:
            return []
        
        # Parse SRT format
        return self._parse_srt(caption_content)
    
    def _parse_srt(self, srt_content: str) -> List[TranscriptSegment]:
        """Parse SRT format into transcript segments"""
        segments = []
        lines = srt_content.strip().split('\n')
        
        i = 0
        while i < len(lines):
            # Skip index line
            if not lines[i].strip().isdigit():
                i += 1
                continue
            
            i += 1  # Move to timestamp line
            if i >= len(lines):
                break
                
            # Parse timestamp line
            timestamp_line = lines[i].strip()
            try:
                time_parts = timestamp_line.split(' --> ')
                start_time = self._parse_timestamp(time_parts[0])
                end_time = self._parse_timestamp(time_parts[1])
            except (IndexError, ValueError):
                logger.warning(f"Failed to parse timestamp: {timestamp_line}")
                i += 1
                continue
            
            i += 1  # Move to text line(s)
            
            # Collect text lines until empty line or end
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            
            # Create segment
            if text_lines:
                text = ' '.join(text_lines)
                segment = TranscriptSegment(
                    start=start_time,
                    end=end_time,
                    text=text
                )
                segments.append(segment)
            
            # Skip empty line
            i += 1
        
        return segments
    
    def _parse_timestamp(self, timestamp: str) -> float:
        """Parse SRT timestamp (00:00:00,000) to seconds"""
        # Replace comma with period for milliseconds
        timestamp = timestamp.replace(',', '.')
        
        # Split into hours, minutes, seconds
        parts = timestamp.split(':')
        if len(parts) != 3:
            raise ValueError(f"Invalid timestamp format: {timestamp}")
        
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        
        return hours * 3600 + minutes * 60 + seconds

def main():
    """CLI for testing API transcript fetching"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch YouTube transcript using API')
    parser.add_argument('video_id', help='YouTube video ID')
    parser.add_argument('--api-key', help='YouTube API key (or use YOUTUBE_API_KEY env)')
    parser.add_argument('--language', default='en', help='Language code (default: en)')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    api_key = args.api_key or os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        raise ValueError("YouTube API key required (--api-key or YOUTUBE_API_KEY env)")
    
    api = YouTubeTranscriptAPI(api_key)
    segments = api.get_transcript_segments(args.video_id, args.language)
    
    if segments:
        print(f"\nTranscript found with {len(segments)} segments:")
        for i, segment in enumerate(segments[:5]):  # Show first 5
            print(f"  {segment.start:.1f}s - {segment.end:.1f}s: {segment.text}")
        
        if len(segments) > 5:
            print(f"  ... and {len(segments) - 5} more segments")
    else:
        print("No transcript found")

if __name__ == '__main__':
    main()
