#!/usr/bin/env python3
"""
YouTube video listing using official YouTube Data API v3
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Iterator
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
import isodate

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

from .list_videos_yt_dlp import VideoInfo

logger = logging.getLogger(__name__)

class YouTubeAPILister:
    """List videos from YouTube channel using official Data API v3"""
    
    def __init__(self, api_key: str):
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API client not available. Install with: "
                "pip install google-api-python-client"
            )
        
        self.api_key = api_key
        self.youtube = build('youtube', 'v3', developerKey=api_key)
    
    def _resolve_channel_id(self, channel_url: str) -> str:
        """Resolve channel URL to channel ID"""
        # Extract channel identifier from URL
        parsed = urlparse(channel_url)
        path = parsed.path.strip('/')
        
        # Handle different URL formats
        if path.startswith('channel/'):
            # Direct channel ID: youtube.com/channel/UCxxxxx
            return path.split('/')[-1]
        elif path.startswith('c/'):
            # Custom URL: youtube.com/c/customname
            custom_name = path.split('/')[-1]
            return self._get_channel_id_by_custom_url(custom_name)
        elif path.startswith('@'):
            # Handle URL: youtube.com/@username
            username = path[1:]  # Remove @
            return self._get_channel_id_by_handle(username)
        elif '/@' in channel_url:
            # Handle URL: youtube.com/@username
            username = channel_url.split('/@')[-1]
            return self._get_channel_id_by_handle(username)
        else:
            # Legacy username: youtube.com/user/username
            username = path.split('/')[-1]
            return self._get_channel_id_by_username(username)
    
    def _get_channel_id_by_handle(self, handle: str) -> str:
        """Get channel ID from @handle"""
        try:
            # Search for channel by handle
            request = self.youtube.search().list(
                part='snippet',
                q=f'@{handle}',
                type='channel',
                maxResults=1
            )
            response = request.execute()
            
            if response['items']:
                return response['items'][0]['snippet']['channelId']
            else:
                raise ValueError(f"Channel not found for handle: @{handle}")
        except HttpError as e:
            logger.error(f"API error resolving handle @{handle}: {e}")
            raise
    
    def _get_channel_id_by_username(self, username: str) -> str:
        """Get channel ID from legacy username"""
        try:
            request = self.youtube.channels().list(
                part='id',
                forUsername=username
            )
            response = request.execute()
            
            if response['items']:
                return response['items'][0]['id']
            else:
                raise ValueError(f"Channel not found for username: {username}")
        except HttpError as e:
            logger.error(f"API error resolving username {username}: {e}")
            raise
    
    def _get_channel_id_by_custom_url(self, custom_name: str) -> str:
        """Get channel ID from custom URL name"""
        try:
            # Search for channel by custom name
            request = self.youtube.search().list(
                part='snippet',
                q=custom_name,
                type='channel',
                maxResults=5
            )
            response = request.execute()
            
            # Look for exact match
            for item in response['items']:
                if item['snippet']['customUrl'].lower() == custom_name.lower():
                    return item['snippet']['channelId']
            
            # If no exact match, take first result
            if response['items']:
                logger.warning(f"No exact match for {custom_name}, using first result")
                return response['items'][0]['snippet']['channelId']
            else:
                raise ValueError(f"Channel not found for custom URL: {custom_name}")
        except HttpError as e:
            logger.error(f"API error resolving custom URL {custom_name}: {e}")
            raise
    
    def _get_uploads_playlist_id(self, channel_id: str) -> str:
        """Get the uploads playlist ID for a channel"""
        try:
            request = self.youtube.channels().list(
                part='contentDetails',
                id=channel_id
            )
            response = request.execute()
            
            if not response['items']:
                raise ValueError(f"Channel not found: {channel_id}")
            
            uploads_playlist = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            return uploads_playlist
        except HttpError as e:
            logger.error(f"API error getting uploads playlist: {e}")
            raise
    
    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse ISO 8601 duration string to seconds"""
        try:
            duration = isodate.parse_duration(duration_str)
            return int(duration.total_seconds())
        except Exception as e:
            logger.warning(f"Failed to parse duration {duration_str}: {e}")
            return None
    
    def _fetch_video_details(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch detailed information for a batch of video IDs"""
        if not video_ids:
            return {}
        
        try:
            # YouTube API allows up to 50 video IDs per request
            request = self.youtube.videos().list(
                part='snippet,contentDetails,statistics',
                id=','.join(video_ids[:50])  # Limit to 50
            )
            response = request.execute()
            
            details = {}
            for item in response['items']:
                video_id = item['id']
                snippet = item['snippet']
                content_details = item['contentDetails']
                statistics = item.get('statistics', {})
                
                details[video_id] = {
                    'title': snippet['title'],
                    'published_at': datetime.fromisoformat(
                        snippet['publishedAt'].replace('Z', '+00:00')
                    ),
                    'duration_s': self._parse_duration(content_details['duration']),
                    'view_count': int(statistics.get('viewCount', 0)),
                    'like_count': int(statistics.get('likeCount', 0)),
                    'description': snippet.get('description', ''),
                    'tags': snippet.get('tags', []),
                    'category_id': snippet.get('categoryId')
                }
            
            return details
        except HttpError as e:
            logger.error(f"API error fetching video details: {e}")
            return {}
    
    def _list_playlist_videos(self, playlist_id: str, max_results: Optional[int] = None) -> Iterator[str]:
        """Generate video IDs from a playlist"""
        next_page_token = None
        total_fetched = 0
        
        while True:
            try:
                request = self.youtube.playlistItems().list(
                    part='contentDetails',
                    playlistId=playlist_id,
                    maxResults=min(50, max_results - total_fetched if max_results else 50),
                    pageToken=next_page_token
                )
                response = request.execute()
                
                # Extract video IDs
                for item in response['items']:
                    video_id = item['contentDetails']['videoId']
                    yield video_id
                    total_fetched += 1
                    
                    if max_results and total_fetched >= max_results:
                        return
                
                # Check for more pages
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
                    
            except HttpError as e:
                logger.error(f"API error listing playlist videos: {e}")
                break
    
    def list_channel_videos(
        self, 
        channel_url: str, 
        max_results: Optional[int] = None,
        newest_first: bool = True
    ) -> List[VideoInfo]:
        """List all videos from a YouTube channel"""
        logger.info(f"Listing videos from channel: {channel_url}")
        
        # Resolve channel ID
        channel_id = self._resolve_channel_id(channel_url)
        logger.info(f"Resolved channel ID: {channel_id}")
        
        # Get uploads playlist
        uploads_playlist_id = self._get_uploads_playlist_id(channel_id)
        logger.info(f"Uploads playlist ID: {uploads_playlist_id}")
        
        # Collect video IDs
        video_ids = list(self._list_playlist_videos(uploads_playlist_id, max_results))
        logger.info(f"Found {len(video_ids)} video IDs")
        
        # Fetch video details in batches
        videos = []
        batch_size = 50
        
        for i in range(0, len(video_ids), batch_size):
            batch_ids = video_ids[i:i + batch_size]
            details = self._fetch_video_details(batch_ids)
            
            for video_id in batch_ids:
                if video_id in details:
                    detail = details[video_id]
                    video = VideoInfo(
                        video_id=video_id,
                        title=detail['title'],
                        published_at=detail['published_at'],
                        duration_s=detail['duration_s'],
                        view_count=detail['view_count'],
                        description=detail['description']
                    )
                    videos.append(video)
                else:
                    logger.warning(f"No details found for video {video_id}")
        
        # Sort by publication date if requested
        if newest_first:
            videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)
        
        logger.info(f"Successfully processed {len(videos)} videos")
        return videos

def main():
    """CLI for testing API video listing"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='List YouTube videos using API')
    parser.add_argument('channel_url', help='YouTube channel URL')
    parser.add_argument('--api-key', help='YouTube API key (or use YOUTUBE_API_KEY env)')
    parser.add_argument('--limit', type=int, help='Maximum number of videos')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    api_key = args.api_key or os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        raise ValueError("YouTube API key required (--api-key or YOUTUBE_API_KEY env)")
    
    lister = YouTubeAPILister(api_key)
    videos = lister.list_channel_videos(args.channel_url, max_results=args.limit)
    
    print(f"\nFound {len(videos)} videos:")
    for video in videos[:10]:  # Show first 10
        print(f"  {video.video_id}: {video.title}")
        if video.published_at:
            print(f"    Published: {video.published_at.strftime('%Y-%m-%d')}")
        if video.duration_s:
            print(f"    Duration: {video.duration_s}s")
        if video.view_count:
            print(f"    Views: {video.view_count:,}")
    
    if len(videos) > 10:
        print(f"  ... and {len(videos) - 10} more")

if __name__ == '__main__':
    main()
