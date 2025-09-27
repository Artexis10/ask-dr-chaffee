#!/usr/bin/env python3
"""
Real-time ingestion monitoring script for the segments-only pipeline.
Monitors database growth and processing progress.
"""

import os
import time
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()

def get_db_stats():
    """Get current database statistics"""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        return None
    
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            # Get counts
            cur.execute('SELECT COUNT(*) FROM sources')
            source_count = cur.fetchone()[0]
            
            cur.execute('SELECT COUNT(*) FROM segments')
            segment_count = cur.fetchone()[0]
            
            # Get latest activity
            cur.execute('''
                SELECT source_id, title, status, created_at 
                FROM sources 
                ORDER BY created_at DESC 
                LIMIT 3
            ''')
            latest_sources = cur.fetchall()
            
            # Get speaker distribution if segments exist
            speaker_stats = []
            if segment_count > 0:
                cur.execute('''
                    SELECT speaker_label, COUNT(*), 
                           ROUND(AVG(end_sec - start_sec), 2) as avg_duration
                    FROM segments 
                    GROUP BY speaker_label 
                    ORDER BY COUNT(*) DESC
                ''')
                speaker_stats = cur.fetchall()
            
            return {
                'source_count': source_count,
                'segment_count': segment_count,
                'latest_sources': latest_sources,
                'speaker_stats': speaker_stats
            }
    
    except Exception as e:
        print(f"Database error: {e}")
        return None
    finally:
        if conn:
            conn.close()

def monitor_ingestion():
    """Monitor ingestion progress in real-time"""
    print("=" * 60)
    print("SEGMENTS-ONLY PIPELINE MONITORING")
    print("=" * 60)
    print("Press Ctrl+C to exit")
    print()
    
    last_segment_count = 0
    
    try:
        while True:
            stats = get_db_stats()
            if not stats:
                print(f"{datetime.now().strftime('%H:%M:%S')} - Database connection failed")
                time.sleep(10)
                continue
            
            # Calculate growth
            segment_growth = stats['segment_count'] - last_segment_count
            growth_indicator = f" (+{segment_growth})" if segment_growth > 0 else ""
            
            # Print current status
            print(f"\n{datetime.now().strftime('%H:%M:%S')} - DATABASE STATUS:")
            print(f"  Sources: {stats['source_count']}")
            print(f"  Segments: {stats['segment_count']}{growth_indicator}")
            
            # Show latest activity
            if stats['latest_sources']:
                print("  Latest Videos:")
                for source_id, title, status, created_at in stats['latest_sources']:
                    title_short = title[:40] + "..." if title and len(title) > 40 else title or "No title"
                    time_str = created_at.strftime('%H:%M:%S') if created_at else "Unknown"
                    print(f"    {source_id}: {title_short} ({status}) [{time_str}]")
            
            # Show speaker distribution
            if stats['speaker_stats']:
                print("  Speaker Distribution:")
                for speaker, count, avg_dur in stats['speaker_stats']:
                    print(f"    {speaker}: {count} segments ({avg_dur}s avg)")
            
            last_segment_count = stats['segment_count']
            time.sleep(30)  # Check every 30 seconds
            
    except KeyboardInterrupt:
        print(f"\n{datetime.now().strftime('%H:%M:%S')} - Monitoring stopped")

if __name__ == "__main__":
    monitor_ingestion()
