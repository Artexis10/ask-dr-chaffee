#!/usr/bin/env python3
"""
Extract video IDs from Dr. Anthony Chaffee's YouTube channel
Channel: @anthonychaffeemd
"""

import requests
import re
import json
from urllib.parse import urljoin, urlparse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_channel_videos(channel_handle: str, max_videos: int = 10, seed_mode: bool = False) -> list:
    """
    Extract video IDs from a YouTube channel using web scraping
    """
    # Convert @handle to channel URL
    if channel_handle.startswith('@'):
        channel_url = f"https://www.youtube.com/{channel_handle}/videos"
    else:
        channel_url = f"https://www.youtube.com/c/{channel_handle}/videos"
    
    logger.info(f"Fetching videos from: {channel_url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(channel_url, headers=headers)
        response.raise_for_status()
        
        # Extract video IDs from the page content
        # YouTube embeds video data in JavaScript variables
        content = response.text
        
        # Look for video IDs in various patterns
        video_id_patterns = [
            r'"videoId":"([a-zA-Z0-9_-]{11})"',
            r'/watch\?v=([a-zA-Z0-9_-]{11})',
            r'"videoId":\s*"([a-zA-Z0-9_-]{11})"'
        ]
        
        video_ids = set()
        
        for pattern in video_id_patterns:
            matches = re.findall(pattern, content)
            video_ids.update(matches)
            
        video_list = list(video_ids)[:max_videos]
        
        # Apply seed mode limit if enabled
        if seed_mode and len(video_list) > 10:
            video_list = video_list[:10]
            logger.info(f"Seed mode: Limited to first 10 videos")
        
        logger.info(f"Found {len(video_list)} video IDs")
        return video_list
        
    except Exception as e:
        logger.error(f"Error fetching channel videos: {e}")
        
        # Fallback: Manually curated list of Dr. Chaffee's videos (you can update this)
        logger.info("Using fallback video list")
        return [
            # Add known video IDs here as fallback
            # Example: "dQw4w9WgXcQ"  # Remove this test video
        ]

def main():
    channel_handle = "@anthonychaffeemd"
    videos = get_channel_videos(channel_handle, max_videos=5)
    
    print(f"\n=== Dr. Anthony Chaffee YouTube Videos ===")
    print(f"Channel: {channel_handle}")
    print(f"Found {len(videos)} videos:\n")
    
    for i, video_id in enumerate(videos, 1):
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"{i}. Video ID: {video_id}")
        print(f"   URL: {video_url}")
        print(f"   Ingest: python scripts/ingest_youtube.py --video-id {video_id}")
        print()

if __name__ == '__main__':
    main()
