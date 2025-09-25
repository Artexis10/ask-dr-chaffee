#!/usr/bin/env python3
"""Monitor test results in real-time"""

import os
import time
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def monitor_progress():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    
    while True:
        try:
            cur = conn.cursor()
            
            # Get current progress
            cur.execute("""
                SELECT 
                    source_id,
                    title,
                    metadata->>'chaffee_percentage' as chaffee_pct,
                    metadata->>'total_speakers_detected' as speakers,
                    metadata->>'segments_count' as segments,
                    created_at
                FROM sources 
                WHERE metadata->>'enhanced_asr' = 'true'
                ORDER BY created_at DESC
            """)
            
            results = cur.fetchall()
            
            print(f"\n=== ENHANCED ASR TEST PROGRESS ===")
            print(f"Time: {time.strftime('%H:%M:%S')}")
            print(f"Completed Videos: {len(results)}")
            
            for source_id, title, chaffee_pct, speakers, segments, created_at in results:
                title_short = title[:40] + "..." if len(title) > 40 else title
                chaffee_pct = float(chaffee_pct) if chaffee_pct else 0.0
                speakers = int(speakers) if speakers else 0
                segments = int(segments) if segments else 0
                
                print(f"  {source_id}: {chaffee_pct:.1f}% Chaffee, {speakers} speakers, {segments} segments")
                print(f"    {title_short}")
            
            time.sleep(30)  # Check every 30 seconds
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)
    
    conn.close()

if __name__ == "__main__":
    monitor_progress()
