#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clean up database data (TRUNCATE tables) without dropping schema.

This script removes all data from tables but preserves:
- Table structure
- Indexes
- Constraints
- Extensions (pgvector)

Use this when you want a fresh start without destroying the schema.
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv
import logging

# Windows UTF-8 fix
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

def cleanup_data():
    """Remove all data from tables while preserving schema"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        logger.error("DATABASE_URL not found in environment")
        return False
    
    try:
        logger.info("=" * 80)
        logger.info("DATABASE DATA CLEANUP")
        logger.info("=" * 80)
        logger.info("")
        logger.info("This will remove ALL DATA from the following tables:")
        logger.info("  • segments (transcript segments)")
        logger.info("  • sources (video metadata)")
        logger.info("  • api_cache (YouTube API cache)")
        logger.info("")
        logger.info("The following will be PRESERVED:")
        logger.info("  ✓ Table structure")
        logger.info("  ✓ Indexes (including pgvector)")
        logger.info("  ✓ Constraints")
        logger.info("  ✓ Extensions (pgvector)")
        logger.info("")
        logger.warning("⚠️  This action CANNOT be undone!")
        logger.info("=" * 80)
        
        # Ask for confirmation
        response = input("\nType 'YES' to proceed with data cleanup: ").strip()
        
        if response != 'YES':
            logger.info("Cleanup cancelled by user")
            return False
        
        logger.info("\n[CONNECT] Connecting to database...")
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Check if tables exist
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            AND table_name IN ('segments', 'sources', 'api_cache')
            ORDER BY table_name
        """)
        
        existing_tables = [row[0] for row in cur.fetchall()]
        
        if not existing_tables:
            logger.warning("No tables found to clean up")
            conn.close()
            return True
        
        logger.info(f"[FOUND] Tables to clean: {', '.join(existing_tables)}")
        
        # Get row counts before cleanup
        logger.info("\n[BEFORE] Current row counts:")
        for table in existing_tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            logger.info(f"  • {table}: {count:,} rows")
        
        # Truncate tables (preserves structure)
        logger.info("\n[CLEANUP] Removing all data...")
        
        # Use CASCADE to handle foreign key constraints
        for table in existing_tables:
            logger.info(f"  • Truncating {table}...")
            cur.execute(f"TRUNCATE TABLE {table} CASCADE")
        
        # Commit changes
        conn.commit()
        
        # Verify cleanup
        logger.info("\n[AFTER] Row counts after cleanup:")
        for table in existing_tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            logger.info(f"  • {table}: {count:,} rows")
        
        # Verify schema is intact
        logger.info("\n[VERIFY] Checking schema integrity...")
        
        # Check tables
        cur.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
        """)
        table_count = cur.fetchone()[0]
        
        # Check indexes
        cur.execute("""
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE schemaname = 'public'
        """)
        index_count = cur.fetchone()[0]
        
        # Check constraints
        cur.execute("""
            SELECT COUNT(*) 
            FROM information_schema.table_constraints 
            WHERE table_schema = 'public'
        """)
        constraint_count = cur.fetchone()[0]
        
        # Check pgvector extension
        cur.execute("""
            SELECT COUNT(*) 
            FROM pg_extension 
            WHERE extname = 'vector'
        """)
        has_pgvector = cur.fetchone()[0] > 0
        
        logger.info(f"  ✓ Tables: {table_count}")
        logger.info(f"  ✓ Indexes: {index_count}")
        logger.info(f"  ✓ Constraints: {constraint_count}")
        logger.info(f"  ✓ pgvector extension: {'Yes' if has_pgvector else 'No'}")
        
        cur.close()
        conn.close()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ DATA CLEANUP SUCCESSFUL!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("All data has been removed from tables.")
        logger.info("Schema, indexes, and constraints are intact.")
        logger.info("")
        logger.info("You can now run ingestion to populate with fresh data:")
        logger.info("  python backend/scripts/ingest_youtube_enhanced.py ...")
        logger.info("")
        
        return True
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def main():
    """Main entry point"""
    success = cleanup_data()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
