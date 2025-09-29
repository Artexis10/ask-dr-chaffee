#!/usr/bin/env python3
"""
Enhance existing videos in the database with speaker identification
This script processes videos that already have transcripts but lack speaker information
"""

import os
import sys
import argparse
import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scripts.common.database import get_db_connection
from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment

logger = logging.getLogger(__name__)

class ExistingVideoEnhancer:
    """Enhance existing videos with speaker identification"""
    
    def __init__(self, voices_dir="voices", dry_run=False):
        self.voices_dir = voices_dir
        self.dry_run = dry_run
        
        # Initialize components
        self.transcript_fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=True,
            voices_dir=voices_dir,
            api_key=os.getenv('YOUTUBE_API_KEY')
        )
        
        self.voice_enrollment = VoiceEnrollment(voices_dir=voices_dir)
        
        # Database connection
        self.db = get_db_connection()
        
        # Ensure speaker columns exist
        self._ensure_speaker_columns()
        
        logger.info(f"Existing video enhancer initialized (dry_run={dry_run})")
    
    def get_videos_needing_enhancement(self) -> List[Dict[str, Any]]:
        """Get list of videos that need speaker identification enhancement"""
        try:
            # Get videos that have transcripts but no speaker information
            cursor = self.db.execute("""
                SELECT DISTINCT v.id, v.title, v.duration_s, 
                       COUNT(ts.id) as segment_count,
                       SUM(CASE WHEN ts.speaker IS NOT NULL THEN 1 ELSE 0 END) as speaker_segments
                FROM videos v
                JOIN transcript_segments ts ON v.id = ts.video_id
                WHERE v.has_enhanced_transcript != 1 OR v.has_enhanced_transcript IS NULL
                GROUP BY v.id, v.title, v.duration_s
                HAVING speaker_segments = 0  -- No segments have speaker information
                ORDER BY v.duration_s DESC  -- Process longer videos first
            """)
            
            videos = []
            for row in cursor.fetchall():
                videos.append({
                    'id': row[0],
                    'title': row[1],
                    'duration_s': row[2],
                    'segment_count': row[3],
                    'speaker_segments': row[4]
                })
            
            return videos
            
        except Exception as e:
            logger.error(f"Failed to get videos needing enhancement: {e}")
            return []
    
    def check_voice_profiles_available(self) -> Dict[str, bool]:
        """Check what voice profiles are available"""
        profiles = self.voice_enrollment.list_profiles()
        return {
            'chaffee': 'Chaffee' in profiles,
            'available_profiles': profiles,
            'total_profiles': len(profiles)
        }
    
    def enhance_video(self, video_id: str) -> Dict[str, Any]:
        """Enhance a single video with speaker identification"""
        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would enhance video: {video_id}")
                return {"video_id": video_id, "success": True, "dry_run": True}
            
            logger.info(f"Enhancing video with speaker ID: {video_id}")
            
            # Step 1: Re-process with Enhanced ASR and speaker identification
            segments = self.transcript_fetcher.get_transcript(video_id)
            
            if not segments:
                return {"video_id": video_id, "success": False, "error": "Failed to get enhanced transcript"}
            
            # Step 2: Update existing segments with speaker information
            speaker_stats = {}
            updated_segments = 0
            
            for segment in segments:
                speaker = getattr(segment, 'speaker', None)
                speaker_confidence = getattr(segment, 'speaker_confidence', None)
                
                if speaker:
                    # Update the segment in database
                    self.db.execute("""
                        UPDATE transcript_segments 
                        SET speaker = ?, speaker_confidence = ?
                        WHERE video_id = ? AND start_time = ? AND end_time = ?
                    """, (
                        speaker, 
                        speaker_confidence,
                        video_id,
                        segment.start,
                        segment.end
                    ))
                    updated_segments += 1
                    
                    # Track speaker statistics
                    if speaker not in speaker_stats:
                        speaker_stats[speaker] = {'count': 0, 'duration': 0}
                    speaker_stats[speaker]['count'] += 1
                    speaker_stats[speaker]['duration'] += (segment.end - segment.start)
            
            # Step 3: Update video metadata
            self.db.execute("""
                UPDATE videos SET 
                    has_enhanced_transcript = 1,
                    speaker_stats = ?,
                    enhanced_at = datetime('now')
                WHERE id = ?
            """, (
                json.dumps(speaker_stats),
                video_id
            ))
            
            self.db.commit()
            
            logger.info(f"✅ Enhanced {video_id}: {updated_segments} segments updated")
            return {
                "video_id": video_id, 
                "success": True, 
                "updated_segments": updated_segments,
                "speaker_stats": speaker_stats
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to enhance {video_id}: {e}")
            return {"video_id": video_id, "success": False, "error": str(e)}
    
    def enhance_batch(self, video_ids: List[str], max_workers: int = 1) -> List[Dict[str, Any]]:
        """Enhance multiple videos"""
        results = []
        
        for i, video_id in enumerate(video_ids, 1):
            logger.info(f"Processing {i}/{len(video_ids)}: {video_id}")
            result = self.enhance_video(video_id)
            results.append(result)
            
            # Progress update
            if result['success'] and not self.dry_run:
                stats = result.get('speaker_stats', {})
                speakers = list(stats.keys())
                speaker_info = f" (speakers: {', '.join(speakers)})" if speakers else ""
                print(f"✅ {video_id}: {result['updated_segments']} segments{speaker_info}")
            elif result['success'] and self.dry_run:
                print(f"[DRY RUN] {video_id}: Would be enhanced")
            else:
                print(f"❌ {video_id}: {result['error']}")
        
        return results
    
    def _ensure_speaker_columns(self):
        """Ensure database has speaker-related columns"""
        try:
            self.db.execute("ALTER TABLE transcript_segments ADD COLUMN speaker TEXT")
        except:
            pass
        
        try:
            self.db.execute("ALTER TABLE transcript_segments ADD COLUMN speaker_confidence REAL")
        except:
            pass
        
        try:
            self.db.execute("ALTER TABLE videos ADD COLUMN has_enhanced_transcript INTEGER DEFAULT 0")
        except:
            pass
        
        try:
            self.db.execute("ALTER TABLE videos ADD COLUMN speaker_stats TEXT")
        except:
            pass
        
        try:
            self.db.execute("ALTER TABLE videos ADD COLUMN enhanced_at TEXT")
        except:
            pass


def main():
    parser = argparse.ArgumentParser(description='Enhance existing videos with speaker identification')
    
    # Video selection
    parser.add_argument('video_ids', nargs='*', help='Specific video IDs to enhance (optional)')
    parser.add_argument('--all', action='store_true', help='Process all videos needing enhancement')
    parser.add_argument('--limit', type=int, help='Limit number of videos to process')
    
    # Processing options
    parser.add_argument('--dry-run', action='store_true', help='Show what would be enhanced without doing it')
    parser.add_argument('--voices-dir', default='voices', help='Voice profiles directory')
    
    # General options
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--check-profiles', action='store_true', help='Check available voice profiles and exit')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Initialize enhancer
    enhancer = ExistingVideoEnhancer(
        voices_dir=args.voices_dir,
        dry_run=args.dry_run
    )
    
    # Check voice profiles
    if args.check_profiles:
        profiles = enhancer.check_voice_profiles_available()
        print(f"🎤 Available voice profiles: {profiles['available_profiles']}")
        print(f"📊 Total profiles: {profiles['total_profiles']}")
        print(f"✅ Chaffee profile available: {profiles['chaffee']}")
        
        if not profiles['chaffee']:
            print("\n⚠️  Dr. Chaffee's voice profile not found!")
            print("   Run: python scripts/asr_cli.py enroll --name Chaffee --url YOUTUBE_URL")
        
        return
    
    # Determine which videos to process
    if args.video_ids:
        video_ids = args.video_ids
        print(f"🎯 Processing specified videos: {len(video_ids)}")
    elif args.all:
        videos = enhancer.get_videos_needing_enhancement()
        video_ids = [v['id'] for v in videos]
        if args.limit:
            video_ids = video_ids[:args.limit]
        
        print(f"🔄 Found {len(video_ids)} videos needing enhancement")
        for video in videos[:10]:  # Show first 10
            print(f"   • {video['id']}: {video.get('title', 'Unknown')} ({video.get('segment_count', 0)} segments)")
        if len(videos) > 10:
            print(f"   ... and {len(videos) - 10} more")
    else:
        parser.print_help()
        return
    
    if not video_ids:
        print("No videos to process")
        return
    
    # Check if voice profiles are available
    profiles = enhancer.check_voice_profiles_available()
    if not profiles['chaffee']:
        print("⚠️  Warning: Dr. Chaffee's voice profile not found!")
        print("   Speaker identification may not work properly.")
        print("   Run: python scripts/asr_cli.py enroll --name Chaffee --url YOUTUBE_URL")
        
        response = input("\nContinue anyway? (y/N): ")
        if response.lower() != 'y':
            return
    
    # Process videos
    print(f"\n🚀 {'[DRY RUN] ' if args.dry_run else ''}Starting enhancement of {len(video_ids)} videos...")
    
    results = enhancer.enhance_batch(video_ids)
    
    # Summary
    successful = sum(1 for r in results if r['success'])
    total = len(results)
    
    print(f"\n📊 Summary: {successful}/{total} videos processed successfully")
    
    if not args.dry_run and successful > 0:
        total_segments = sum(r.get('updated_segments', 0) for r in results if r['success'])
        print(f"🎤 Total segments enhanced with speaker information: {total_segments}")
        
        # Show speaker distribution across all processed videos
        all_speakers = set()
        for result in results:
            if result['success'] and 'speaker_stats' in result:
                all_speakers.update(result['speaker_stats'].keys())
        
        if all_speakers:
            print(f"👥 Speakers identified: {', '.join(sorted(all_speakers))}")


if __name__ == '__main__':
    main()
