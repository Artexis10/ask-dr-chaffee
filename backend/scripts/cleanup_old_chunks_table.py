#!/usr/bin/env python3
"""
Cleanup script to remove the old chunks table and migrate to segments-only architecture.

This prevents confusion between the old chunks table and the new segments table.
The segments table has proper speaker attribution while chunks was generic.
"""

import os
import sys
import psycopg2
import logging
from dotenv import load_dotenv

# Load environment
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_old_chunks_table():
    """Remove the old chunks table to prevent confusion"""
    
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("DATABASE_URL not found in environment")
        return False
    
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            # Check if chunks table exists
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'chunks'
            """)
            
            chunks_exists = cur.fetchone() is not None
            
            if chunks_exists:
                # Get count for info
                cur.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = cur.fetchone()[0]
                
                logger.info(f"Found old chunks table with {chunk_count} records")
                
                # Check if segments table exists and has data
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = 'segments'
                """)
                
                segments_exists = cur.fetchone() is not None
                
                if segments_exists:
                    cur.execute("SELECT COUNT(*) FROM segments")
                    segment_count = cur.fetchone()[0]
                    logger.info(f"Found segments table with {segment_count} records")
                    
                    if segment_count > 0:
                        # Safe to drop chunks table
                        logger.info("✅ Segments table has data. Safe to drop chunks table.")
                        
                        response = input("Drop the old chunks table? (y/N): ")
                        if response.lower() == 'y':
                            cur.execute("DROP TABLE chunks CASCADE")
                            conn.commit()
                            logger.info("✅ Successfully dropped chunks table")
                            return True
                        else:
                            logger.info("Keeping chunks table as requested")
                            return False
                    else:
                        logger.warning("⚠️ Segments table exists but is empty. Not safe to drop chunks yet.")
                        return False
                else:
                    logger.error("❌ Segments table does not exist! Do not drop chunks table yet.")
                    return False
            else:
                logger.info("✅ Chunks table does not exist - already cleaned up")
                return True
                
    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def show_table_status():
    """Show current status of tables"""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("DATABASE_URL not found in environment")
        return
    
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            logger.info("=== TABLE STATUS ===")
            
            # Check chunks table
            try:
                cur.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = cur.fetchone()[0]
                logger.info(f"[CHUNKS] chunks table: {chunk_count} records")
            except:
                logger.info("[CHUNKS] chunks table: DOES NOT EXIST")
            
            # Check segments table  
            try:
                cur.execute("SELECT COUNT(*) FROM segments")
                segment_count = cur.fetchone()[0]
                logger.info(f"[SEGMENTS] segments table: {segment_count} records")
                
                # Show speaker breakdown
                cur.execute("""
                    SELECT speaker_label, COUNT(*), 
                           ROUND(AVG(end_sec - start_sec), 2) as avg_duration_sec
                    FROM segments 
                    GROUP BY speaker_label 
                    ORDER BY COUNT(*) DESC
                """)
                
                logger.info("Speaker breakdown:")
                for row in cur.fetchall():
                    speaker, count, avg_dur = row
                    logger.info(f"  {speaker}: {count} segments, {avg_dur}s avg duration")
                    
            except Exception as e:
                logger.info(f"[SEGMENTS] segments table: ERROR - {e}")
                
    except Exception as e:
        logger.error(f"❌ Error checking table status: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("[CLEANUP] Chunks Table Cleanup Script")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        show_table_status()
    else:
        show_table_status()
        print("\n" + "=" * 40)
        cleanup_old_chunks_table()
