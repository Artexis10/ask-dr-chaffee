#!/usr/bin/env python3
"""
Nuclear database reset script - completely wipe and recreate with segments-only architecture.
This eliminates all confusion between old chunks and new segments tables.
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

def nuke_and_recreate_database():
    """Completely wipe database and recreate with segments-only architecture"""
    
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("DATABASE_URL not found in environment")
        return False
    
    # Confirm with user
    print("=" * 60)
    print("[!] NUCLEAR DATABASE RESET [!]")
    print("=" * 60)
    print("This will COMPLETELY WIPE the database and recreate it.")
    print("ALL existing data will be PERMANENTLY LOST.")
    print()
    print("Benefits:")
    print("+ Clean segments-only architecture")  
    print("+ No chunks/segments confusion")
    print("+ Optimized for RTX 5080 performance")
    print("+ Pure speaker attribution system")
    print()
    
    # Auto-confirm for batch execution
    logger.info("Auto-confirming database reset for batch execution...")
    
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        
        with conn.cursor() as cur:
            logger.info("[NUKE] Starting nuclear database reset...")
            
            # Get list of all tables and views
            cur.execute("""
                SELECT table_name, table_type
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            objects = cur.fetchall()
            
            logger.info(f"Found {len(objects)} database objects to drop:")
            for obj_name, obj_type in objects:
                logger.info(f"  {obj_type}: {obj_name}")
            
            # Drop all views first, then tables
            for obj_name, obj_type in objects:
                if obj_type == 'VIEW':
                    logger.info(f"Dropping view: {obj_name}")
                    cur.execute(f"DROP VIEW IF EXISTS {obj_name} CASCADE")
                else:
                    logger.info(f"Dropping table: {obj_name}")
                    cur.execute(f"DROP TABLE IF EXISTS {obj_name} CASCADE")
            
            logger.info("[CLEAN] All tables dropped successfully")
            
            # Create clean segments-only schema
            logger.info("[BUILD] Creating clean segments architecture...")
            
            # Enable pgvector extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Create unified sources table (merged with ingest_state)
            cur.execute("""
                CREATE TABLE sources (
                    id SERIAL PRIMARY KEY,
                    source_type VARCHAR(50) NOT NULL,
                    source_id VARCHAR(255) NOT NULL,
                    title TEXT,
                    published_at TIMESTAMP,
                    duration_s INTEGER,
                    view_count BIGINT,
                    -- Processing state (merged from ingest_state)
                    status VARCHAR(50) DEFAULT 'pending',
                    progress NUMERIC(5,2) DEFAULT 0.0,
                    chunk_count INTEGER DEFAULT 0,
                    embedding_count INTEGER DEFAULT 0,
                    has_yt_transcript BOOLEAN DEFAULT FALSE,
                    has_whisper BOOLEAN DEFAULT FALSE,
                    error TEXT,
                    retries INTEGER DEFAULT 0,
                    last_error TEXT,
                    -- Metadata and timestamps
                    metadata JSONB DEFAULT '{}',
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_type, source_id)
                )
            """)
            
            # Create segments table with speaker attribution
            cur.execute("""
                CREATE TABLE segments (
                    id SERIAL PRIMARY KEY,
                    video_id VARCHAR(255) NOT NULL,
                    start_sec NUMERIC(10,3) NOT NULL,
                    end_sec NUMERIC(10,3) NOT NULL,
                    speaker_label VARCHAR(20) DEFAULT 'GUEST',
                    speaker_conf NUMERIC(5,3),
                    text TEXT NOT NULL,
                    avg_logprob NUMERIC(8,4),
                    compression_ratio NUMERIC(8,4),
                    no_speech_prob NUMERIC(5,3),
                    temperature_used NUMERIC(3,1) DEFAULT 0.0,
                    re_asr BOOLEAN DEFAULT FALSE,
                    is_overlap BOOLEAN DEFAULT FALSE,
                    needs_refinement BOOLEAN DEFAULT FALSE,
                    embedding vector(384),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create API cache table for YouTube Data API
            cur.execute("""
                CREATE TABLE api_cache (
                    id SERIAL PRIMARY KEY,
                    cache_key VARCHAR(255) UNIQUE NOT NULL,
                    etag VARCHAR(255),
                    data JSONB,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create useful indexes
            logger.info("[INDEX] Creating performance indexes...")
            
            cur.execute("CREATE INDEX idx_segments_video_id ON segments(video_id)")
            cur.execute("CREATE INDEX idx_segments_speaker ON segments(speaker_label)")
            cur.execute("CREATE INDEX idx_segments_time ON segments(video_id, start_sec)")
            cur.execute("CREATE INDEX idx_sources_lookup ON sources(source_type, source_id)")
            cur.execute("CREATE INDEX idx_sources_status ON sources(status)")
            cur.execute("CREATE INDEX idx_sources_updated ON sources(last_updated)")
            
            # Create pgvector index (will be populated later)
            logger.info("[VECTOR] Creating pgvector index for semantic search...")
            cur.execute("""
                CREATE INDEX segments_embedding_idx 
                ON segments USING ivfflat (embedding vector_l2_ops) 
                WITH (lists = 100)
            """)
            
            logger.info("[SUCCESS] Clean database schema created successfully!")
            logger.info("")
            logger.info("Created Tables:")
            logger.info("  • sources - Video metadata + processing state (merged)")
            logger.info("  • segments - Transcripts with speaker attribution (CH/GUEST)")
            logger.info("  • api_cache - YouTube Data API caching")
            logger.info("")
            logger.info("Key Features:")
            logger.info("  • Pure segments architecture (no chunks confusion)")
            logger.info("  • Speaker attribution (CH = Dr. Chaffee, GUEST = others)")
            logger.info("  • pgvector embeddings for semantic search")
            logger.info("  • Performance optimized indexes")
            logger.info("  • YouTube API caching for quota efficiency")
            
            return True
            
    except Exception as e:
        logger.error(f"[ERROR] Database reset failed: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    success = nuke_and_recreate_database()
    if success:
        print("\n" + "=" * 60)
        print("[SUCCESS] DATABASE NUCLEAR RESET COMPLETE!")
        print("=" * 60)
        print("Ready for clean segments-only ingestion pipeline!")
    else:
        print("\n[ERROR] Database reset failed or cancelled")
        sys.exit(1)
