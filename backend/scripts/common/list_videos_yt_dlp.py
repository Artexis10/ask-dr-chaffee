#!/usr/bin/env python3
"""
YouTube video listing using yt-dlp (no API key required)
"""

import json
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
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
        
        return cls(
            video_id=data['id'],
            title=data.get('title', f"Video {data['id']}"),
            published_at=published_at,
            duration_s=duration_s,
            view_count=data.get('view_count'),
            description=data.get('description', '').strip() or None
        )

class YtDlpVideoLister:
    """List videos from YouTube channel using yt-dlp"""
    
    def __init__(self, yt_dlp_path: str = "yt-dlp"):
        self.yt_dlp_path = yt_dlp_path
    
    def list_from_json(self, json_path: Path) -> List[VideoInfo]:
        """Load video list from pre-dumped yt-dlp JSON file (JSON Lines format)"""
        logger.info(f"Loading videos from JSON: {json_path}")
        
        videos = []
        with open(json_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    entry = json.loads(line)
                    if not entry or not entry.get('id'):
                        continue
                    
                    video = VideoInfo.from_yt_dlp(entry)
                    videos.append(video)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON on line {line_num}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Failed to parse video entry on line {line_num}: {e}")
                    continue
        
        logger.info(f"Loaded {len(videos)} videos from JSON")
        return videos
    
    def dump_channel_json(self, channel_url: str, output_path: Path) -> Path:
        """Dump channel videos to JSON using yt-dlp flat playlist mode"""
        logger.info(f"Dumping channel videos to JSON: {channel_url}")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # yt-dlp command for flat playlist extraction
        cmd = [
            self.yt_dlp_path,
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--ignore-errors",
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
            logger.error(f"yt-dlp failed: {e.stderr}")
            raise
        except Exception as e:
            logger.error(f"Failed to dump channel JSON: {e}")
            raise
    
    def list_channel_videos(self, channel_url: str, use_cache: bool = True) -> List[VideoInfo]:
        """List all videos from a YouTube channel"""
        # Create cache file path
        cache_dir = Path("backend/data")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate cache filename from channel URL
        channel_id = channel_url.split('/')[-1].replace('@', '').replace('c/', '')
        cache_file = cache_dir / f"videos_{channel_id}.json"
        
        # Use cache if available and requested
        if use_cache and cache_file.exists():
            logger.info(f"Using cached video list: {cache_file}")
            return self.list_from_json(cache_file)
        
        # Dump fresh data
        self.dump_channel_json(channel_url, cache_file)
        return self.list_from_json(cache_file)
    
    def get_video_metadata(self, video_id: str) -> Optional[VideoInfo]:
        """Get detailed metadata for a single video"""
        logger.debug(f"Fetching metadata for video: {video_id}")
        
        cmd = [
            self.yt_dlp_path,
            "--dump-json",
            "--no-warnings",
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
