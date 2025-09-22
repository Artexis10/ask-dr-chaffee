#!/usr/bin/env python3
"""Check which videos are stuck and at what stage"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def check_stuck_videos():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cursor = conn.cursor()
    
    print("=== INGESTION STATUS CHECK ===")
    
    # Check ingest_state table
    cursor.execute("""
        SELECT video_id, status, retries, last_error, created_at 
        FROM ingest_state 
        ORDER BY created_at DESC 
        LIMIT 20
    """)
    
    rows = cursor.fetchall()
    if rows:
        print(f"\nFound {len(rows)} videos in ingest_state:")
        for row in rows:
            video_id, status, retries, error, created = row
            print(f"  {video_id}: {status} (retries: {retries}) - {created}")
            if error:
                print(f"    Error: {error}")
    else:
        print("\nNo videos found in ingest_state table!")
    
    # Check for videos being processed right now
    cursor.execute("""
        SELECT status, COUNT(*) 
        FROM ingest_state 
        GROUP BY status
    """)
    
    status_counts = cursor.fetchall()
    if status_counts:
        print(f"\nStatus distribution:")
        for status, count in status_counts:
            print(f"  {status}: {count} videos")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_stuck_videos()
