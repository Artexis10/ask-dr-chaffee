#!/usr/bin/env python3
"""
Database Monitoring for Production Ingestion
Tracks ingested chunks, sources, and processing status
"""

import os
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("psycopg2 not available - cannot monitor database")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection"""
    if not DB_AVAILABLE:
        return None
    
    try:
        db_url = os.getenv('DATABASE_URL')
        return psycopg2.connect(db_url)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

def get_ingestion_stats(conn):
    """Get current ingestion statistics"""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get total chunks and sources
            cur.execute("SELECT COUNT(*) as chunk_count FROM chunks")
            chunk_count = cur.fetchone()['chunk_count']
            
            cur.execute("SELECT COUNT(*) as source_count FROM sources WHERE source_type = 'youtube'")
            source_count = cur.fetchone()['source_count']
            
            # Get recent activity (last 10 minutes)
            cur.execute("""
                SELECT COUNT(*) as recent_chunks 
                FROM chunks 
                WHERE created_at > NOW() - INTERVAL '10 minutes'
            """)
            recent_chunks = cur.fetchone()['recent_chunks']
            
            # Get ingest state summary
            cur.execute("""
                SELECT status, COUNT(*) as count 
                FROM ingest_state 
                GROUP BY status 
                ORDER BY count DESC
            """)
            ingest_states = cur.fetchall()
            
            return {
                'total_chunks': chunk_count,
                'total_sources': source_count,
                'recent_chunks': recent_chunks,
                'ingest_states': ingest_states
            }
    except Exception as e:
        logger.error(f"Error getting ingestion stats: {e}")
        return None

def monitor_database_progress():
    """Monitor database ingestion progress"""
    logger.info("📊 Database Monitoring Started for Production Ingestion")
    logger.info("=" * 80)
    
    if not DB_AVAILABLE:
        logger.error("❌ Database monitoring not available - psycopg2 required")
        return
    
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Cannot connect to database")
        return
    
    start_time = time.time()
    last_chunk_count = 0
    
    try:
        while True:
            current_time = datetime.now().strftime("%H:%M:%S")
            elapsed = time.time() - start_time
            
            stats = get_ingestion_stats(conn)
            if not stats:
                time.sleep(10)
                continue
            
            # Calculate ingestion rate
            chunk_rate = 0
            if elapsed > 0:
                chunk_rate = (stats['total_chunks'] - last_chunk_count) / 10 if last_chunk_count > 0 else 0
            
            # Format output
            status_line = f"⏰ {current_time} | ⏱️ {elapsed/60:.1f}m"
            status_line += f" | 📝 Chunks: {stats['total_chunks']:,}"
            status_line += f" | 🎬 Sources: {stats['total_sources']:,}"
            status_line += f" | 🚀 Rate: {chunk_rate:.1f}/s"
            status_line += f" | 🆕 Recent: {stats['recent_chunks']}"
            
            logger.info(status_line)
            
            # Show ingest state breakdown
            if stats['ingest_states']:
                state_summary = " | ".join([f"{state['status']}: {state['count']}" 
                                          for state in stats['ingest_states'][:3]])
                logger.info(f"📊 Status: {state_summary}")
            
            # Check if we're making good progress
            if stats['recent_chunks'] > 0:
                logger.info("🎯 ACTIVE: New chunks being ingested!")
            
            if stats['total_chunks'] > 10000:
                logger.info("🎯 MILESTONE: 10,000+ chunks ingested!")
            
            last_chunk_count = stats['total_chunks']
            time.sleep(10)
            
    except KeyboardInterrupt:
        logger.info("👋 Database monitoring stopped by user")
    except Exception as e:
        logger.error(f"Database monitoring error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    monitor_database_progress()
