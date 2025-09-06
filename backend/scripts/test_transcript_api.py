#!/usr/bin/env python3
"""
Test script for YouTube Data API transcript fetching
"""

import os
import sys
import logging
import argparse
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.transcript_common import TranscriptSegment
from scripts.common.transcript_api import YouTubeTranscriptAPI, GOOGLE_API_AVAILABLE

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Test YouTube Data API transcript fetching"""
    parser = argparse.ArgumentParser(description='Test YouTube Data API transcript fetching')
    parser.add_argument('video_id', help='YouTube video ID')
    parser.add_argument('--api-key', help='YouTube API key (or use YOUTUBE_API_KEY env)')
    parser.add_argument('--language', default='en', help='Language code (default: en)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get API key from args or environment
    api_key = args.api_key or os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        raise ValueError("YouTube API key required (--api-key or YOUTUBE_API_KEY env)")
    
    # Check if Google API client is available
    if not GOOGLE_API_AVAILABLE:
        logger.error("Google API client not available. Install with: pip install google-api-python-client")
        return 1
    
    logger.info(f"Testing YouTube Data API transcript fetching for video {args.video_id}")
    
    try:
        # Initialize API client
        api = YouTubeTranscriptAPI(api_key)
        
        # List available captions
        captions = api.list_captions(args.video_id)
        logger.info(f"Found {len(captions)} caption tracks")
        
        for i, caption in enumerate(captions):
            track_language = caption['snippet']['language']
            is_auto = caption['snippet'].get('trackKind') == 'ASR'
            logger.info(f"  {i+1}. Language: {track_language}, Auto-generated: {is_auto}")
        
        # Get transcript segments
        segments = api.get_transcript_segments(args.video_id, args.language)
        
        if segments:
            logger.info(f"\nTranscript found with {len(segments)} segments:")
            for i, segment in enumerate(segments[:5]):  # Show first 5
                logger.info(f"  {segment.start:.1f}s - {segment.end:.1f}s: {segment.text}")
            
            if len(segments) > 5:
                logger.info(f"  ... and {len(segments) - 5} more segments")
            
            return 0
        else:
            logger.error("No transcript found")
            return 1
            
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        return 1

if __name__ == '__main__':
    sys.exit(main())
