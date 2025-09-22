#!/usr/bin/env python3
"""
Database upsert operations for video ingestion pipeline
"""

import logging
import hashlib
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values
import threading
from datetime import datetime, timezone

from .list_videos_yt_dlp import VideoInfo
from .transcripts import TranscriptSegment

logger = logging.getLogger(__name__)

@dataclass
class ChunkData:
    """Chunk data for database insertion"""
    chunk_hash: str
    source_id: str
    text: str
    t_start_s: float
    t_end_s: float
    embedding: Optional[np.ndarray] = None
    
    @classmethod
    def from_transcript_segment(cls, segment: TranscriptSegment, source_id: str) -> 'ChunkData':
        """Create chunk from transcript segment"""
        # Create deterministic hash
        content = f"{source_id}:{segment.start}:{segment.end}:{segment.text}"
        chunk_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        return cls(
            chunk_hash=chunk_hash,
            source_id=source_id,
            text=segment.text,
            t_start_s=float(segment.start),  # Ensure Python float
            t_end_s=float(segment.end)       # Ensure Python float
        )

class DatabaseUpserter:
    """Handle database upsert operations for video ingestion"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self._local = threading.local()
    
    def get_connection(self):
        """Get thread-local database connection"""
        if not hasattr(self._local, 'connection') or self._local.connection.closed:
            self._local.connection = psycopg2.connect(self.db_url)
            self._local.connection.autocommit = False
        return self._local.connection
    
    def close_connection(self):
        """Close thread-local database connection"""
        if hasattr(self._local, 'connection') and not self._local.connection.closed:
            self._local.connection.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection()
    
    def upsert_ingest_state(
        self, 
        video_id: str, 
        video_info: VideoInfo,
        status: str = 'pending',
        **kwargs
    ) -> None:
        """Upsert video into ingest_state table"""
        conn = self.get_connection()
        
        with conn.cursor() as cur:
            # Prepare values
            values = {
                'video_id': video_id,
                'title': video_info.title,
                'published_at': video_info.published_at,
                'duration_s': video_info.duration_s,
                'status': status,
                'view_count': video_info.view_count,
                'description': video_info.description,
                'updated_at': datetime.now(timezone.utc),
                **kwargs
            }
            
            # Build dynamic upsert query
            columns = list(values.keys())
            placeholders = [f'%({col})s' for col in columns]
            
            update_clauses = []
            for col in columns:
                if col != 'video_id':  # Don't update primary key
                    update_clauses.append(f"{col} = EXCLUDED.{col}")
            
            query = f"""
                INSERT INTO ingest_state ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                ON CONFLICT (video_id) DO UPDATE SET
                    {', '.join(update_clauses)}
            """
            
            cur.execute(query, values)
            conn.commit()
            
        logger.debug(f"Upserted ingest_state for {video_id}: {status}")
    
    def get_ingest_state(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get current ingest state for video"""
        conn = self.get_connection()
        
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM ingest_state WHERE video_id = %s",
                (video_id,)
            )
            result = cur.fetchone()
            return dict(result) if result else None
    
    def get_videos_by_status(
        self, 
        status: str, 
        limit: int = None,
        order_by: str = "created_at DESC"
    ) -> List[Dict[str, Any]]:
        """Get videos by ingest status"""
        try:
            with self.get_connection().cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                query = f"SELECT * FROM ingest_state WHERE status = %s ORDER BY {order_by}"
                if limit:
                    query += f" LIMIT {limit}"
                
                cur.execute(query, (status,))
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            self.get_connection().rollback()  # Reset transaction on error
            logger.warning(f"Database query failed, rolling back: {e}")
            return []
    
    def update_ingest_status(
        self, 
        video_id: str, 
        status: str, 
        error: Optional[str] = None,
        increment_retries: bool = False,
        **kwargs
    ) -> None:
        """Update ingest status for video"""
        conn = self.get_connection()
        
        with conn.cursor() as cur:
            updates = {
                'status': status,
                'updated_at': datetime.now(timezone.utc),
                **kwargs
            }
            
            if error:
                updates['last_error'] = error
            
            # Build update query components
            set_clauses = []
            values = {'video_id': video_id}
            
            for key, value in updates.items():
                set_clauses.append(f"{key} = %({key})s")
                values[key] = value
            
            if increment_retries:
                # Handle retries increment separately to avoid SQL injection
                set_clauses.append("retries = retries + 1")
            
            query = f"""
                UPDATE ingest_state 
                SET {', '.join(set_clauses)}
                WHERE video_id = %(video_id)s
            """
            
            cur.execute(query, values)
            conn.commit()
        
        logger.debug(f"Updated {video_id} status to {status}")
    
    def upsert_source(
        self, 
        video_info: VideoInfo, 
        source_type: str = 'youtube',
        provenance: str = 'yt_caption',
        access_level: str = 'public',
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Upsert video into sources table and return database ID
        
        Args:
            video_info: Video information
            source_type: Source type (youtube, zoom, etc.)
            provenance: Transcript source ('owner', 'yt_caption', 'yt_dlp', 'whisper')
            access_level: Content access level ('public', 'restricted', 'private')
            extra_metadata: Additional metadata to store (preprocessing flags, quality info, etc.)
            
        Returns:
            Database ID of the upserted source
        """
        conn = self.get_connection()
        
        with conn.cursor() as cur:
            playback_url = f"https://www.youtube.com/watch?v={video_info.video_id}"
            
            # Build metadata object
            metadata = extra_metadata or {}
            
            # Convert duration_s to duration_seconds to match schema
            query = """
                INSERT INTO sources (
                    source_type, source_id, title, published_at, 
                    url, duration_seconds, view_count, provenance, access_level, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_type, source_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    published_at = EXCLUDED.published_at,
                    url = EXCLUDED.url,
                    duration_seconds = EXCLUDED.duration_seconds,
                    view_count = EXCLUDED.view_count,
                    provenance = EXCLUDED.provenance,
                    access_level = EXCLUDED.access_level,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                RETURNING id
            """
            
            cur.execute(query, (
                source_type,
                video_info.video_id,
                video_info.title,
                video_info.published_at,
                playback_url,
                video_info.duration_s,
                video_info.view_count,
                provenance,
                access_level,
                psycopg2.extras.Json(metadata) if metadata else None
            ))
            
            source_id = cur.fetchone()[0]
            conn.commit()
        
        logger.debug(f"Upserted source for {video_info.video_id} with ID {source_id}, provenance: {provenance}, access: {access_level}")
        return source_id
    
    def upsert_chunks(self, chunks: List[ChunkData]) -> int:
        """Batch upsert chunks into database"""
        if not chunks:
            return 0
        
        conn = self.get_connection()
        
        with conn.cursor() as cur:
            # Prepare data for batch insert
            chunk_data = []
            for i, chunk in enumerate(chunks):
                # Ensure embedding is properly converted to list format
                embedding_list = None
                if chunk.embedding is not None:
                    if hasattr(chunk.embedding, 'tolist'):
                        embedding_list = chunk.embedding.tolist()
                    elif isinstance(chunk.embedding, list):
                        embedding_list = chunk.embedding
                    else:
                        # Convert any other array-like object
                        embedding_list = list(chunk.embedding)
                
                chunk_data.append((
                    chunk.source_id,
                    i,  # chunk_index
                    chunk.t_start_s,  # start_time_seconds  
                    chunk.t_end_s,    # end_time_seconds
                    chunk.text,
                    embedding_list,
                    len(chunk.text.split())  # word_count
                ))
            
            # Batch upsert with ON CONFLICT
            query = """
                INSERT INTO chunks (
                    source_id, chunk_index, start_time_seconds, end_time_seconds, 
                    text, embedding, word_count
                )
                VALUES %s
                ON CONFLICT (source_id, chunk_index) DO UPDATE SET
                    start_time_seconds = EXCLUDED.start_time_seconds,
                    end_time_seconds = EXCLUDED.end_time_seconds,
                    text = EXCLUDED.text,
                    embedding = EXCLUDED.embedding,
                    word_count = EXCLUDED.word_count
                RETURNING id
            """
            
            execute_values(
                cur,
                query,
                chunk_data,
                template=None,
                page_size=100
            )
            
            conn.commit()
            
        logger.info(f"Upserted {len(chunks)} chunks")
        return len(chunks)
    
    def get_chunk_count(self, source_id: str) -> int:
        """Get number of chunks for a source"""
        conn = self.get_connection()
        
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM chunks WHERE source_id = %s",
                (source_id,)
            )
            return cur.fetchone()[0]
    
    def delete_chunks(self, source_id: str) -> int:
        """Delete all chunks for a source"""
        conn = self.get_connection()
        
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chunks WHERE source_id = %s",
                (source_id,)
            )
            deleted_count = cur.rowcount
            conn.commit()
            
        logger.info(f"Deleted {deleted_count} chunks for {source_id}")
        return deleted_count
    
    def get_ingestion_stats(self) -> Dict[str, Any]:
        """Get ingestion pipeline statistics"""
        conn = self.get_connection()
        
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Status counts
            cur.execute("""
                SELECT status, COUNT(*) as count 
                FROM ingest_state 
                GROUP BY status 
                ORDER BY count DESC
            """)
            status_counts = {row['status']: row['count'] for row in cur.fetchall()}
            
            # Total videos and chunks
            cur.execute("SELECT COUNT(*) FROM ingest_state")
            total_videos = cur.fetchone()['count']
            
            cur.execute("SELECT COUNT(*) FROM chunks")
            total_chunks = cur.fetchone()['count']
            
            cur.execute("SELECT COUNT(*) FROM sources WHERE source_type = 'youtube'")
            total_sources = cur.fetchone()['count']
            
            # Error summary
            cur.execute("""
                SELECT last_error, COUNT(*) as count
                FROM ingest_state 
                WHERE status = 'error' AND last_error IS NOT NULL
                GROUP BY last_error
                ORDER BY count DESC
                LIMIT 5
            """)
            error_summary = {row['last_error']: row['count'] for row in cur.fetchall()}
            
            return {
                'total_videos': total_videos,
                'total_sources': total_sources,
                'total_chunks': total_chunks,
                'status_counts': status_counts,
                'error_summary': error_summary
            }

def main():
    """CLI for testing database operations"""
    import argparse
    import os
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description='Test database upsert operations')
    parser.add_argument('--db-url', help='Database URL (or use DATABASE_URL env)')
    parser.add_argument('--stats', action='store_true', help='Show ingestion stats')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    db_url = args.db_url or os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("Database URL required (--db-url or DATABASE_URL env)")
    
    with DatabaseUpserter(db_url) as upserter:
        if args.stats:
            stats = upserter.get_ingestion_stats()
            print("\nIngestion Statistics:")
            print(f"  Total videos: {stats['total_videos']}")
            print(f"  Total sources: {stats['total_sources']}")
            print(f"  Total chunks: {stats['total_chunks']}")
            print(f"\nStatus breakdown:")
            for status, count in stats['status_counts'].items():
                print(f"  {status}: {count}")
            if stats['error_summary']:
                print(f"\nTop errors:")
                for error, count in stats['error_summary'].items():
                    print(f"  {error}: {count}")

if __name__ == '__main__':
    main()
