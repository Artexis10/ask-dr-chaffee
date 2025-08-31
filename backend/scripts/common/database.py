import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or os.getenv('DATABASE_URL')
        if not self.connection_string:
            raise ValueError("DATABASE_URL environment variable is required")
        
    def get_connection(self):
        """Get a database connection"""
        return psycopg2.connect(self.connection_string)
    
    def insert_source(self, source_type: str, source_id: str, title: str, 
                     description: str = None, duration_seconds: int = None, 
                     published_at: str = None, url: str = None, 
                     metadata: dict = None) -> int:
        """Insert a new source record"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sources (source_type, source_id, title, description, 
                                       duration_seconds, published_at, url, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_type, source_id) 
                    DO UPDATE SET 
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        duration_seconds = EXCLUDED.duration_seconds,
                        published_at = EXCLUDED.published_at,
                        url = EXCLUDED.url,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    RETURNING id
                """, (source_type, source_id, title, description, duration_seconds, 
                      published_at, url, Json(metadata) if metadata else None))
                
                return cur.fetchone()[0]
    
    def insert_chunks(self, source_db_id: int, chunks: List[Dict[str, Any]]):
        """Insert transcript chunks for a source"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Delete existing chunks for this source
                cur.execute("DELETE FROM chunks WHERE source_id = %s", (source_db_id,))
                
                # Insert new chunks
                for chunk in chunks:
                    cur.execute("""
                        INSERT INTO chunks (source_id, chunk_index, start_time_seconds, 
                                          end_time_seconds, text, embedding, word_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        source_db_id,
                        chunk['chunk_index'],
                        chunk['start_time_seconds'],
                        chunk['end_time_seconds'],
                        chunk['text'],
                        chunk.get('embedding'),  # Can be None initially
                        chunk['word_count']
                    ))
                
                logger.info(f"Inserted {len(chunks)} chunks for source {source_db_id}")
    
    def get_sources_without_embeddings(self) -> List[Dict[str, Any]]:
        """Get chunks that need embeddings generated"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT c.id, c.text, s.id as source_id, s.title
                    FROM chunks c
                    JOIN sources s ON c.source_id = s.id
                    WHERE c.embedding IS NULL
                    ORDER BY s.id, c.chunk_index
                """)
                return cur.fetchall()
    
    def update_chunk_embedding(self, chunk_id: int, embedding: List[float]):
        """Update a chunk with its embedding vector"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE chunks 
                    SET embedding = %s::vector 
                    WHERE id = %s
                """, (embedding, chunk_id))
    
    def source_exists(self, source_type: str, source_id: str) -> bool:
        """Check if a source already exists"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM sources 
                    WHERE source_type = %s AND source_id = %s
                """, (source_type, source_id))
                return cur.fetchone() is not None
