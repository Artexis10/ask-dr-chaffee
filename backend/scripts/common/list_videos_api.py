#!/usr/bin/env python3
"""
YouTube video listing using official YouTube Data API v3
"""

import re
import logging
import time
import random
import os
from datetime import datetime, timezone
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

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

from .list_videos_yt_dlp import VideoInfo

logger = logging.getLogger(__name__)

class YouTubeAPILister:
    """List videos from YouTube channel using official Data API v3"""
    
    def __init__(self, api_key: str, db_url: str = None):
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API client not available. Install with: "
                "pip install google-api-python-client"
            )
        
        self.api_key = api_key
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.db_url = db_url or os.getenv('DATABASE_URL')
        self._channel_cache = {}  # In-memory cache for channel IDs
    
    def _get_db_connection(self):
        """Get database connection for caching"""
        if not POSTGRES_AVAILABLE or not self.db_url:
            return None
        try:
            return psycopg2.connect(self.db_url)
        except Exception as e:
            logger.warning(f"Failed to connect to database for caching: {e}")
            return None
    
    def _get_cache_value(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached value from database"""
        conn = self._get_db_connection()
        if not conn:
            return None
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT etag, updated_at FROM api_cache WHERE key = %s",
                    (key,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.warning(f"Failed to get cache value for {key}: {e}")
            return None
        finally:
            conn.close()
    
    def _set_cache_value(self, key: str, etag: str = None):
        """Set cached value in database"""
        conn = self._get_db_connection()
        if not conn:
            return
        
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO api_cache (key, etag, updated_at) 
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key) DO UPDATE SET 
                        etag = EXCLUDED.etag,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (key, etag)
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to set cache value for {key}: {e}")
        finally:
            conn.close()
    
    def _exponential_backoff(self, attempt: int, max_delay: int = 60):
        """Implement exponential backoff with jitter"""
        delay = min(max_delay, (2 ** attempt) + random.uniform(0, 1))
        logger.info(f"Backing off for {delay:.2f} seconds (attempt {attempt})")
        time.sleep(delay)
    
    def _make_api_request(self, request_func, max_retries: int = 3):
        """Make API request with exponential backoff on rate limits"""
        for attempt in range(max_retries):
            try:
                return request_func()
            except HttpError as e:
                if e.resp.status in [429, 500, 502, 503, 504]:  # Rate limit or server errors
                    if attempt < max_retries - 1:
                        self._exponential_backoff(attempt)
                        continue
                raise
    
    def _resolve_channel_id(self, channel_url: str) -> str:
        """Resolve channel URL to channel ID with caching"""
        # Check in-memory cache first
        if channel_url in self._channel_cache:
            return self._channel_cache[channel_url]
        
        # Check database cache
        cache_key = f"channel_id_{channel_url}"
        cached = self._get_cache_value(cache_key)
        if cached and cached.get('etag'):  # Use etag field to store channel_id
            self._channel_cache[channel_url] = cached['etag']
            return cached['etag']
        
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
            channel_id = self._get_channel_id_by_handle(username)
        elif '/@' in channel_url:
            # Handle URL: youtube.com/@username
            username = channel_url.split('/@')[-1]
            channel_id = self._get_channel_id_by_handle(username)
        else:
            # Legacy username: youtube.com/user/username
            username = path.split('/')[-1]
            channel_id = self._get_channel_id_by_username(username)
        
        # Cache the resolved channel ID
        self._channel_cache[channel_url] = channel_id
        self._set_cache_value(cache_key, channel_id)
        return channel_id
    
    def _get_channel_id_by_handle(self, handle: str) -> str:
        """Get channel ID from @handle"""
        def make_request():
            request = self.youtube.search().list(
                part='snippet',
                q=f'@{handle}',
                type='channel',
                maxResults=1
            )
            return request.execute()
        
        try:
            response = self._make_api_request(make_request)
            
            if response['items']:
                return response['items'][0]['snippet']['channelId']
            else:
                raise ValueError(f"Channel not found for handle: @{handle}")
        except HttpError as e:
            logger.error(f"API error resolving handle @{handle}: {e}")
            raise
    
    def _get_channel_id_by_username(self, username: str) -> str:
        """Get channel ID from legacy username"""
        def make_request():
            request = self.youtube.channels().list(
                part='id',
                forUsername=username
            )
            return request.execute()
        
        try:
            response = self._make_api_request(make_request)
            
            if response['items']:
                return response['items'][0]['id']
            else:
                raise ValueError(f"Channel not found for username: {username}")
        except HttpError as e:
            logger.error(f"API error resolving username {username}: {e}")
            raise
    
    def _get_channel_id_by_custom_url(self, custom_name: str) -> str:
        """Get channel ID from custom URL name"""
        def make_request():
            request = self.youtube.search().list(
                part='snippet',
                q=custom_name,
                type='channel',
                maxResults=5
            )
            return request.execute()
        
        try:
            response = self._make_api_request(make_request)
            
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
        """Get the uploads playlist ID for a channel with caching"""
        cache_key = f"uploads_playlist_{channel_id}"
        cached = self._get_cache_value(cache_key)
        if cached and cached.get('etag'):
            return cached['etag']
        
        def make_request():
            request = self.youtube.channels().list(
                part='contentDetails',
                id=channel_id
            )
            return request.execute()
        
        try:
            response = self._make_api_request(make_request)
            
            if not response['items']:
                raise ValueError(f"Channel not found: {channel_id}")
            
            uploads_playlist = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Cache the uploads playlist ID
            self._set_cache_value(cache_key, uploads_playlist)
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
                part='snippet,contentDetails,statistics,liveStreamingDetails',
                id=','.join(video_ids[:50])  # Limit to 50
            )
            response = request.execute()
            
            details = {}
            for item in response['items']:
                video_id = item['id']
                snippet = item['snippet']
                content_details = item['contentDetails']
                statistics = item.get('statistics', {})
                live_streaming_details = item.get('liveStreamingDetails', {})
                
                # Detect live stream status
                is_live = False
                is_upcoming = False
                if live_streaming_details:
                    is_live = 'actualStartTime' in live_streaming_details and 'actualEndTime' not in live_streaming_details
                    is_upcoming = 'scheduledStartTime' in live_streaming_details and 'actualStartTime' not in live_streaming_details
                
                # Detect members-only content
                is_members_only = False
                if 'membershipRequired' in content_details:
                    is_members_only = content_details['membershipRequired']
                # Also check title and description for common indicators
                title_lower = snippet['title'].lower()
                desc_lower = snippet.get('description', '').lower()
                if '[members only]' in title_lower or '(members only)' in title_lower or \
                   '[members only]' in desc_lower or '(members only)' in desc_lower or \
                   'exclusive to members' in desc_lower or 'member exclusive' in title_lower:
                    is_members_only = True
                
                details[video_id] = {
                    'title': snippet['title'],
                    'published_at': datetime.fromisoformat(
                        snippet['publishedAt'].replace('Z', '+00:00')
                    ),
                    'duration_s': self._parse_duration(content_details.get('duration', 'PT0S')),
                    'view_count': int(statistics.get('viewCount', 0)),
                    'like_count': int(statistics.get('likeCount', 0)),
                    'description': snippet.get('description', ''),
                    'tags': snippet.get('tags', []),
                    'category_id': snippet.get('categoryId'),
                    'is_live': is_live,
                    'is_upcoming': is_upcoming,
                    'is_members_only': is_members_only
                }
            
            return details
        except HttpError as e:
            logger.error(f"API error fetching video details: {e}")
            return {}
    
    def _list_playlist_videos(self, playlist_id: str, max_results: Optional[int] = None, since_published: Optional[datetime] = None) -> Iterator[str]:
        """Generate video IDs from a playlist with optional date filtering"""
        next_page_token = None
        total_fetched = 0
        
        while True:
            def make_request():
                request = self.youtube.playlistItems().list(
                    part='contentDetails',
                    playlistId=playlist_id,
                    maxResults=min(50, max_results - total_fetched if max_results else 50),
                    pageToken=next_page_token
                )
                return request.execute()
            
            try:
                response = self._make_api_request(make_request)
                
                # Extract video IDs
                for item in response['items']:
                    video_id = item['contentDetails']['videoId']
                    
                    # If we have a since_published filter, we need to check the video's publish date
                    # This requires a separate API call, so we'll do it in batches later
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
        newest_first: bool = True,
        since_published: Optional[datetime] = None,
        skip_live: bool = True,
        skip_upcoming: bool = True,
        skip_members_only: bool = True
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
        video_ids = list(self._list_playlist_videos(uploads_playlist_id, max_results, since_published))
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
                    
                    # Apply since_published filter if specified
                    if since_published and detail['published_at'] < since_published:
                        continue
                    
                    # Apply content type filters
                    if skip_live and detail.get('is_live', False):
                        logger.info(f"Skipping live stream: {video_id} - {detail['title']}")
                        continue
                        
                    if skip_upcoming and detail.get('is_upcoming', False):
                        logger.info(f"Skipping upcoming stream: {video_id} - {detail['title']}")
                        continue
                        
                    if skip_members_only and detail.get('is_members_only', False):
                        logger.info(f"Skipping members-only content: {video_id} - {detail['title']}")
                        continue
                    
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
