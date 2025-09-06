#!/usr/bin/env python3
"""
Database optimization utilities for large-scale ingestion.

This module provides functions to optimize PostgreSQL for handling
large-scale ingestion workloads, including:
- Index maintenance
- Vacuum operations
- Table statistics updates
- Connection pooling
"""

import os
import logging
import argparse
import time
from typing import Dict, Any, List, Optional
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseOptimizer:
    """Optimize PostgreSQL database for large-scale ingestion"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self._connection = None
    
    def get_connection(self):
        """Get database connection with lazy initialization"""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(self.db_url)
            self._connection.autocommit = True  # For maintenance operations
        return self._connection
    
    def close_connection(self):
        """Close database connection"""
        if self._connection and not self._connection.closed:
            self._connection.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection()
    
    def analyze_tables(self, tables: Optional[List[str]] = None):
        """Update table statistics for query optimizer"""
        conn = self.get_connection()
        
        if not tables:
            tables = ['sources', 'chunks', 'ingest_state', 'api_cache']
        
        with conn.cursor() as cur:
            for table in tables:
                logger.info(f"Analyzing table: {table}")
                cur.execute(f"ANALYZE {table}")
    
    def vacuum_tables(self, tables: Optional[List[str]] = None, full: bool = False):
        """Run VACUUM to reclaim storage and update statistics"""
        conn = self.get_connection()
        
        if not tables:
            tables = ['sources', 'chunks', 'ingest_state', 'api_cache']
        
        with conn.cursor() as cur:
            for table in tables:
                vacuum_type = "FULL" if full else ""
                logger.info(f"Vacuuming table {table} {vacuum_type}")
                # Need to execute with autocommit
                cur.execute(f"VACUUM {vacuum_type} {table}")
    
    def reindex_tables(self, tables: Optional[List[str]] = None):
        """Rebuild indexes to improve performance"""
        conn = self.get_connection()
        
        if not tables:
            tables = ['sources', 'chunks', 'ingest_state', 'api_cache']
        
        with conn.cursor() as cur:
            for table in tables:
                logger.info(f"Reindexing table: {table}")
                cur.execute(f"REINDEX TABLE {table}")
    
    def get_table_sizes(self) -> Dict[str, Dict[str, Any]]:
        """Get size information for tables"""
        conn = self.get_connection()
        
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    table_name,
                    pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) as total_size,
                    pg_size_pretty(pg_relation_size(quote_ident(table_name))) as table_size,
                    pg_size_pretty(pg_total_relation_size(quote_ident(table_name)) - 
                                  pg_relation_size(quote_ident(table_name))) as index_size,
                    pg_total_relation_size(quote_ident(table_name)) as total_bytes
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY total_bytes DESC
            """)
            
            return {row['table_name']: dict(row) for row in cur.fetchall()}
    
    def get_index_usage_stats(self) -> List[Dict[str, Any]]:
        """Get index usage statistics"""
        conn = self.get_connection()
        
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    schemaname || '.' || relname as table,
                    indexrelname as index,
                    pg_size_pretty(pg_relation_size(i.indexrelid)) as index_size,
                    idx_scan as index_scans,
                    idx_tup_read as tuples_read,
                    idx_tup_fetch as tuples_fetched
                FROM pg_stat_user_indexes ui
                JOIN pg_index i ON ui.indexrelid = i.indexrelid
                WHERE schemaname = 'public'
                ORDER BY pg_relation_size(i.indexrelid) DESC
            """)
            
            return [dict(row) for row in cur.fetchall()]
    
    def get_table_bloat_estimate(self) -> List[Dict[str, Any]]:
        """Estimate table bloat (space that could be reclaimed)"""
        conn = self.get_connection()
        
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # This is a simplified bloat query
            cur.execute("""
                SELECT
                    schemaname || '.' || tablename as table_name,
                    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as total_size,
                    n_dead_tup as dead_tuples,
                    n_live_tup as live_tuples,
                    CASE WHEN n_live_tup > 0 
                        THEN round(100 * n_dead_tup / (n_live_tup + n_dead_tup))
                        ELSE 0 
                    END as dead_tuple_percent
                FROM pg_stat_user_tables
                WHERE schemaname = 'public'
                ORDER BY dead_tuple_percent DESC
            """)
            
            return [dict(row) for row in cur.fetchall()]
    
    def optimize_for_ingestion(self):
        """Run all optimization steps for ingestion workload"""
        logger.info("Starting database optimization for ingestion workload")
        
        # Get initial table sizes
        logger.info("Current table sizes:")
        sizes = self.get_table_sizes()
        for table, info in sizes.items():
            logger.info(f"  {table}: {info['total_size']} (table: {info['table_size']}, indexes: {info['index_size']})")
        
        # Check for table bloat
        logger.info("Checking for table bloat:")
        bloat = self.get_table_bloat_estimate()
        for table_info in bloat:
            if table_info['dead_tuple_percent'] > 10:
                logger.info(f"  {table_info['table_name']}: {table_info['dead_tuple_percent']}% dead tuples")
        
        # Run vacuum analyze on tables with significant bloat
        bloated_tables = [t['table_name'].split('.')[-1] for t in bloat if t['dead_tuple_percent'] > 10]
        if bloated_tables:
            logger.info(f"Vacuuming bloated tables: {', '.join(bloated_tables)}")
            self.vacuum_tables(tables=bloated_tables)
        
        # Analyze all tables to update statistics
        logger.info("Updating table statistics...")
        self.analyze_tables()
        
        # Check index usage
        logger.info("Index usage statistics:")
        index_stats = self.get_index_usage_stats()
        for idx in index_stats:
            logger.info(f"  {idx['table']}.{idx['index']}: {idx['index_size']} ({idx['index_scans']} scans)")
        
        logger.info("Database optimization completed")
        
        return {
            'table_sizes': sizes,
            'bloat': bloat,
            'index_stats': index_stats
        }
    
    def create_pgvector_index(self, recreate: bool = False):
        """Create or recreate pgvector index for similarity search"""
        conn = self.get_connection()
        
        with conn.cursor() as cur:
            if recreate:
                logger.info("Dropping existing pgvector index...")
                try:
                    cur.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
                except Exception as e:
                    logger.error(f"Error dropping index: {e}")
            
            logger.info("Creating pgvector index (this may take a while)...")
            try:
                # Create IVFFlat index for faster similarity search
                # Lists parameter should be sqrt(row_count)
                cur.execute("SELECT COUNT(*) FROM chunks")
                row_count = cur.fetchone()[0]
                lists = max(100, int(row_count ** 0.5))
                
                logger.info(f"Creating IVFFlat index with {lists} lists for {row_count} rows")
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
                    ON chunks USING ivfflat (embedding vector_cosine_ops) 
                    WITH (lists = {lists})
                """)
                logger.info("pgvector index created successfully")
            except Exception as e:
                logger.error(f"Error creating pgvector index: {e}")
                raise

def main():
    """CLI for database optimization"""
    parser = argparse.ArgumentParser(description='Optimize database for large-scale ingestion')
    parser.add_argument('--db-url', help='Database URL (or use DATABASE_URL env)')
    parser.add_argument('--vacuum', action='store_true', help='Run VACUUM on tables')
    parser.add_argument('--vacuum-full', action='store_true', help='Run VACUUM FULL (locks tables)')
    parser.add_argument('--analyze', action='store_true', help='Update table statistics')
    parser.add_argument('--reindex', action='store_true', help='Rebuild indexes')
    parser.add_argument('--rebuild-vector-index', action='store_true', help='Rebuild pgvector index')
    parser.add_argument('--all', action='store_true', help='Run all optimization steps')
    
    args = parser.parse_args()
    
    db_url = args.db_url or os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("Database URL required (--db-url or DATABASE_URL env)")
    
    with DatabaseOptimizer(db_url) as optimizer:
        if args.all:
            optimizer.optimize_for_ingestion()
        else:
            if args.vacuum:
                optimizer.vacuum_tables(full=False)
            if args.vacuum_full:
                optimizer.vacuum_tables(full=True)
            if args.analyze:
                optimizer.analyze_tables()
            if args.reindex:
                optimizer.reindex_tables()
            if args.rebuild_vector_index:
                optimizer.create_pgvector_index(recreate=True)
        
        # Always show table sizes
        sizes = optimizer.get_table_sizes()
        print("\nCurrent table sizes:")
        for table, info in sizes.items():
            print(f"  {table}: {info['total_size']}")

if __name__ == '__main__':
    main()
