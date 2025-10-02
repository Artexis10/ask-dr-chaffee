#!/usr/bin/env python3
"""
YouTube video listing using yt-dlp (no API key required)
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class VideoInfo:
    """Normalized video information"""
    video_id: str
    title: str
    published_at: Optional[datetime] = None
    duration_s: Optional[int] = None
    view_count: Optional[int] = None
    description: Optional[str] = None
    channel_name: Optional[str] = None
    channel_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    tags: Optional[List[str]] = None
    url: Optional[str] = None
    availability: Optional[str] = None  # e.g., 'public', 'subscriber_only', 'unlisted'
    
    @classmethod
    def from_yt_dlp(cls, data: Dict[str, Any]) -> 'VideoInfo':
        """Create VideoInfo from yt-dlp JSON output"""
        # Parse upload date
        published_at = None
        if data.get('upload_date'):
            try:
                published_at = datetime.strptime(data['upload_date'], '%Y%m%d')
            except (ValueError, TypeError):
                logger.warning(f"Could not parse upload_date: {data.get('upload_date')}")
        
        # Parse duration
        duration_s = data.get('duration')
        if isinstance(duration_s, str):
            try:
                duration_s = int(float(duration_s))
            except (ValueError, TypeError):
                duration_s = None
        
        # Get thumbnail (prefer maxresdefault, fallback to others)
        thumbnail_url = None
        if data.get('thumbnail'):
            thumbnail_url = data['thumbnail']
        elif data.get('thumbnails') and len(data['thumbnails']) > 0:
            thumbnail_url = data['thumbnails'][-1].get('url')  # Last is usually highest quality
        
        # Safely handle description (can be None)
        description = data.get('description')
        if description:
            description = description.strip() or None
        
        return cls(
            video_id=data['id'],
            title=data.get('title', f"Video {data['id']}"),
            published_at=published_at,
            duration_s=duration_s,
            view_count=data.get('view_count'),
            description=description,
            channel_name=data.get('channel') or data.get('uploader'),
            channel_url=data.get('channel_url') or data.get('uploader_url'),
            thumbnail_url=thumbnail_url,
            like_count=data.get('like_count'),
            comment_count=data.get('comment_count'),
            tags=data.get('tags'),
            url=data.get('webpage_url') or data.get('original_url') or f"https://www.youtube.com/watch?v={data['id']}",
            availability=data.get('availability')  # Capture availability status
        )

class YtDlpVideoLister:
    """List videos from YouTube channel using yt-dlp"""
    
    def __init__(self, yt_dlp_path: str = "yt-dlp"):
        self.yt_dlp_path = yt_dlp_path
    
    def list_from_json(self, json_path: Path) -> List[VideoInfo]:
        """Load video list from pre-dumped yt-dlp JSON file (JSON Lines format)"""
        logger.info(f"Loading videos from JSON: {json_path}")
        
        videos = []
        
        # Try different encodings
        encodings_to_try = ['utf-8', 'latin1', 'cp1252', None]  # None will use locale.getpreferredencoding()
        
        for encoding in encodings_to_try:
            try:
                with open(json_path, 'r', encoding=encoding) as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            entry = json.loads(line)
                            if not entry or not entry.get('id'):
                                continue
                            
                            # Validate required fields before creating VideoInfo
                            if entry.get('title') is None:
                                logger.warning(f"Skipping video on line {line_num}: missing title")
                                continue
                                
                            try:
                                video = VideoInfo.from_yt_dlp(entry)
                                videos.append(video)
                            except (AttributeError, TypeError) as e:
                                logger.warning(f"Skipping video on line {line_num}: {e}")
                                continue
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON on line {line_num}: {e}")
                            continue
                        except Exception as e:
                            logger.warning(f"Failed to parse video entry on line {line_num}: {e}")
                            continue
                
                # If we got here without exception, we found the right encoding
                logger.info(f"Successfully read file with encoding: {encoding or 'system default'}")
                break
                
            except UnicodeDecodeError:
                logger.warning(f"Failed to decode file with encoding {encoding}, trying next encoding")
                continue
            except Exception as e:
                logger.error(f"Error reading file: {e}")
                raise
        
        logger.info(f"Loaded {len(videos)} videos from JSON")
        return videos
    
    def dump_channel_json(self, channel_url: str, output_path: Path) -> Path:
        """Dump channel videos to JSON using yt-dlp flat playlist mode"""
        logger.info(f"Dumping channel videos to JSON: {channel_url}")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # yt-dlp command for flat playlist extraction with latest anti-blocking fixes
        cmd = [
            self.yt_dlp_path,
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--ignore-errors",
            # Latest nightly anti-blocking fixes (2025.09.26):
            '--extractor-args', 'youtube:player_client=web_safari',  # Use web_safari client (latest fix)
            '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '--referer', 'https://www.youtube.com/',
            '-4',  # Force IPv4 (fixes many 403s)
            '--sleep-requests', '2',  # Sleep between requests
            f"{channel_url}/videos"
        ]
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # Run yt-dlp and capture JSON output
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
            
            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8') if result.stderr else "Unknown error"
                raise subprocess.CalledProcessError(result.returncode, cmd, error_msg)
            
            logger.info(f"Successfully dumped channel to {output_path}")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp timeout after 5 minutes")
            raise
        except subprocess.CalledProcessError as e:
            raise
        except Exception as e:
            logger.error(f"Failed to dump channel JSON: {e}")
            raise
    
    def list_channel_videos(self, channel_url: str, use_cache: bool = False, skip_members_only: bool = True) -> List[VideoInfo]:
        """List all videos from a YouTube channel
        
        Args:
            channel_url: YouTube channel URL
            use_cache: If True, use cached data (WARNING: may be stale - availability can change!)
            skip_members_only: Filter out subscriber-only/members-only content
        """
        # Create cache file path
        cache_dir = Path("backend/data")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate cache filename from channel URL
        channel_name = channel_url.split('@')[-1] if '@' in channel_url else 'unknown'
        cache_file = cache_dir / f"videos_{channel_name}.json"
        
        # Check cache age if using cache
        use_existing_cache = False
        if use_cache and cache_file.exists():
            cache_age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
            if cache_age_hours < 24:  # Cache valid for 24 hours
                logger.info(f"Using cached video list ({cache_age_hours:.1f}h old): {cache_file}")
                use_existing_cache = True
            else:
                logger.warning(f"Cache is {cache_age_hours:.1f}h old (stale) - refreshing")
        
        if use_existing_cache:
            videos = self.list_from_json(cache_file)
        else:
            # Dump fresh data
            logger.info(f"Fetching fresh video list from YouTube")
            self.dump_channel_json(channel_url, cache_file)
            videos = self.list_from_json(cache_file)
        
        # Apply members-only filter if requested
        if skip_members_only:
            original_count = len(videos)
            videos = [v for v in videos if not self._is_members_only_video(v)]
            filtered_count = original_count - len(videos)
            if filtered_count > 0:
                logger.info(f"Filtered out {filtered_count} members-only videos, {len(videos)} remaining")
        
        return videos
    
    def _is_members_only_video(self, video: VideoInfo) -> bool:
        """Check if video is members-only/subscriber-only content
        
        Checks both the availability metadata field (most reliable) and title indicators.
        """
        # First check availability field from yt-dlp metadata (most reliable)
        if video.availability:
            restricted_types = ['subscriber_only', 'premium_only', 'needs_auth', 'unlisted']
            if video.availability in restricted_types:
                logger.debug(f"Detected restricted video (availability={video.availability}): {video.video_id}")
                return True
        
        # Fallback: check title for members-only indicators
        title = video.title.lower()
        members_indicators = [
            'members only',
            'members exclusive',
            'exclusive to members', 
            'member exclusive',
            'patreon exclusive',
            'subscriber exclusive',
            'premium content',
            'early access'
        ]
        
        for indicator in members_indicators:
            if indicator in title:
                logger.debug(f"Detected members-only video (title): {video.video_id} - {video.title[:50]}...")
                return True
        
        return False
    
    def get_video_metadata(self, video_id: str) -> Optional[VideoInfo]:
        """Get detailed metadata for a single video"""
        logger.debug(f"Fetching metadata for video: {video_id}")
        
        cmd = [
            self.yt_dlp_path,
            "--dump-json",
            "--no-warnings",
            # Latest nightly anti-blocking fixes (2025.09.26):
            '--extractor-args', 'youtube:player_client=web_safari',  # Use web_safari client (latest fix)
            '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '--referer', 'https://www.youtube.com/',
            '-4',  # Force IPv4 (fixes many 403s)
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to get metadata for {video_id}: {result.stderr}")
                return None
            
            data = json.loads(result.stdout)
            return VideoInfo.from_yt_dlp(data)
            
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            logger.warning(f"Error getting metadata for {video_id}: {e}")
            return None

def main():
    """CLI for testing video listing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='List YouTube videos using yt-dlp')
    parser.add_argument('channel_url', help='YouTube channel URL')
    parser.add_argument('--output', '-o', help='Output JSON file path')
    parser.add_argument('--no-cache', action='store_true', help='Force refresh cache')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    lister = YtDlpVideoLister()
    
    if args.output:
        # Dump to specific file
        output_path = Path(args.output)
        lister.dump_channel_json(args.channel_url, output_path)
        videos = lister.list_from_json(output_path)
    else:
        # List videos
        videos = lister.list_channel_videos(args.channel_url, use_cache=not args.no_cache)
    
    print(f"\nFound {len(videos)} videos:")
    for video in videos[:10]:  # Show first 10
        print(f"  {video.video_id}: {video.title}")
        if video.published_at:
            print(f"    Published: {video.published_at.strftime('%Y-%m-%d')}")
        if video.duration_s:
            print(f"    Duration: {video.duration_s}s")
    
    if len(videos) > 10:
        print(f"  ... and {len(videos) - 10} more")

if __name__ == '__main__':
    main()
