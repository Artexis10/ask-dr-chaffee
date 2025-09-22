#!/usr/bin/env python3
"""
Morning progress checker for overnight ingestion
"""

import os
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

def check_progress():
    """Check ingestion progress and database stats"""
    load_dotenv()
    
    print("="*60)
    print("ASK DR. CHAFFEE - OVERNIGHT INGESTION PROGRESS")
    print("="*60)
    print(f"Check time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Database stats
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        # Overall stats
        cursor.execute("SELECT COUNT(*) FROM chunks;")
        total_chunks = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM sources;")
        total_sources = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM sources WHERE source_type='youtube';")
        youtube_sources = cursor.fetchone()[0]
        
        print(f"\nDATABASE STATS:")
        print(f"  Total chunks: {total_chunks:,}")
        print(f"  Total sources: {total_sources}")
        print(f"  YouTube sources: {youtube_sources}")
        
        # Recent activity
        cursor.execute("""
            SELECT title, created_at 
            FROM sources 
            WHERE source_type='youtube' 
            ORDER BY created_at DESC 
            LIMIT 10;
        """)
        recent = cursor.fetchall()
        
        print(f"\nRECENT VIDEOS PROCESSED:")
        for title, created_at in recent:
            time_ago = datetime.now() - created_at.replace(tzinfo=None)
            print(f"  • {title[:50]}... ({time_ago.total_seconds()/3600:.1f}h ago)")
        
        # Processing stats by hour
        cursor.execute("""
            SELECT 
                DATE_TRUNC('hour', created_at) as hour,
                COUNT(*) as videos_processed
            FROM sources 
            WHERE source_type='youtube' 
              AND created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY DATE_TRUNC('hour', created_at)
            ORDER BY hour DESC
            LIMIT 12;
        """)
        
        hourly_stats = cursor.fetchall()
        print(f"\nHOURLY PROCESSING RATE (last 12 hours):")
        for hour, count in hourly_stats:
            print(f"  {hour.strftime('%H:00')}: {count} videos")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Database error: {e}")
    
    # Check log file
    log_file = "youtube_ingestion.log"
    if os.path.exists(log_file):
        file_size = os.path.getsize(log_file) / (1024 * 1024)  # MB
        mod_time = datetime.fromtimestamp(os.path.getmtime(log_file))
        time_since_update = datetime.now() - mod_time
        
        print(f"\nLOG FILE STATUS:")
        print(f"  Size: {file_size:.1f} MB")
        print(f"  Last updated: {time_since_update.total_seconds()/60:.1f} minutes ago")
        
        # Show last few log lines
        print(f"\nLAST LOG ENTRIES:")
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[-5:]:
                    if 'INFO' in line or 'ERROR' in line:
                        print(f"  {line.strip()}")
        except Exception as e:
            print(f"  Could not read log: {e}")
    
    # Estimate completion
    if 'hourly_stats' in locals() and hourly_stats:
        recent_rate = sum(count for _, count in hourly_stats[:3]) / 3  # avg last 3 hours
        if recent_rate > 0:
            estimated_hours_remaining = (500 - youtube_sources) / recent_rate
            completion_time = datetime.now() + timedelta(hours=estimated_hours_remaining)
            print(f"\nESTIMATED COMPLETION:")
            print(f"  Rate: {recent_rate:.1f} videos/hour")
            print(f"  Remaining: ~{estimated_hours_remaining:.1f} hours")
            print(f"  Completion: {completion_time.strftime('%Y-%m-%d %H:%M')}")
    
    print("="*60)

if __name__ == "__main__":
    check_progress()
