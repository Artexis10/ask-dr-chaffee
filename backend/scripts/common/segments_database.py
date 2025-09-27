#!/usr/bin/env python3
"""
Enhanced segments database integration for distil-large-v3 + Chaffee-aware system
Replaces the old chunks-based system with proper speaker attribution
"""

import os
import uuid
import logging
import psycopg2
import psycopg2.extras
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class SegmentsDatabase:
    """Enhanced segments database with speaker attribution and pgvector support"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.connection = None
        
    def get_connection(self):
        """Get database connection"""
        if not self.connection or self.connection.closed:
            self.connection = psycopg2.connect(self.db_url)
        return self.connection
    
    def upsert_source(self, video_id: str, title: str, 
                     source_type: str = 'youtube', 
                     metadata: Optional[Dict] = None) -> int:
        """Upsert video source and return source_id"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                # Check if source exists
                cur.execute(
                    "SELECT id FROM sources WHERE source_type = %s AND source_id = %s",
                    (source_type, video_id)
                )
                result = cur.fetchone()
                
                if result:
                    source_id = result[0]
                    logger.debug(f"Source {video_id} already exists with id {source_id}")
                else:
                    # Insert new source
                    import json
                    metadata_json = json.dumps(metadata or {})
                    cur.execute("""
                        INSERT INTO sources (source_type, source_id, title, metadata, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                    """, (source_type, video_id, title, metadata_json, datetime.now()))
                    
                    source_id = cur.fetchone()[0]
                    conn.commit()
                    logger.info(f"Created new source {video_id} with id {source_id}")
                
                return source_id
                
        except Exception as e:
            logger.error(f"Failed to upsert source {video_id}: {e}")
            if conn:
                conn.rollback()
            raise
    
    def batch_insert_segments(self, segments: List[Dict[str, Any]], 
                            video_id: str,
                            chaffee_only_storage: bool = False,
                            embed_chaffee_only: bool = True) -> int:
        """Batch insert segments with speaker attribution"""
        
        if not segments:
            return 0
        
        # Filter segments if chaffee_only_storage is enabled
        if chaffee_only_storage:
            segments = [seg for seg in segments if seg.get('speaker_label') in ['CH', 'Chaffee']]
            logger.info(f"Chaffee-only storage: filtered to {len(segments)} Chaffee segments")
        
        if not segments:
            logger.info("No segments to insert after filtering")
            return 0
        
        try:
            conn = self.get_connection()
            inserted_count = 0
            
            with conn.cursor() as cur:
                # Prepare batch insert
                insert_query = """
                    INSERT INTO segments (
                        video_id, start_sec, end_sec, speaker_label, speaker_conf,
                        text, avg_logprob, compression_ratio, no_speech_prob,
                        temperature_used, re_asr, is_overlap, needs_refinement,
                        embedding
                    ) VALUES %s
                """
                
                # Prepare values for batch insert
                values = []
                for segment in segments:
                    # Determine if this segment should get an embedding
                    embedding = None
                    if segment.get('embedding'):
                        speaker_label = segment.get('speaker_label', 'GUEST')
                        # Accept both 'CH' and 'Chaffee' labels for embedding
                        if not embed_chaffee_only or speaker_label in ['CH', 'Chaffee']:
                            embedding = segment['embedding']
                    
                    values.append((
                        video_id,
                        segment.get('start', 0.0),
                        segment.get('end', 0.0),
                        segment.get('speaker_label', 'GUEST'),
                        segment.get('speaker_confidence', None),
                        segment.get('text', ''),
                        segment.get('avg_logprob', None),
                        segment.get('compression_ratio', None),
                        segment.get('no_speech_prob', None),
                        segment.get('temperature_used', 0.0),
                        segment.get('re_asr', False),
                        segment.get('is_overlap', False),
                        segment.get('needs_refinement', False),
                        embedding
                    ))
                
                # Execute batch insert
                psycopg2.extras.execute_values(cur, insert_query, values)
                inserted_count = cur.rowcount
                
                conn.commit()
                logger.info(f"Batch inserted {inserted_count} segments for video {video_id}")
                
                return inserted_count
                
        except Exception as e:
            logger.error(f"Failed to batch insert segments for {video_id}: {e}")
            if conn:
                conn.rollback()
            raise
    
    def check_video_exists(self, video_id: str) -> Tuple[Optional[int], int]:
        """Check if video exists and return source_id and segment count"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                # Check if source exists
                cur.execute(
                    "SELECT id FROM sources WHERE source_type = 'youtube' AND source_id = %s",
                    (video_id,)
                )
                result = cur.fetchone()
                
                if not result:
                    return None, 0
                
                source_id = result[0]
                
                # Count existing segments
                cur.execute(
                    "SELECT COUNT(*) FROM segments WHERE video_id = %s",
                    (video_id,)
                )
                segment_count = cur.fetchone()[0]
                
                return source_id, segment_count
                
        except Exception as e:
            logger.error(f"Failed to check video existence for {video_id}: {e}")
            return None, 0
    
    def get_video_stats(self, video_id: str) -> Dict[str, Any]:
        """Get comprehensive video statistics"""
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # Get segment statistics
                cur.execute("""
                    SELECT 
                        speaker_label,
                        COUNT(*) as segment_count,
                        SUM(end_sec - start_sec) as total_duration,
                        AVG(speaker_conf) as avg_confidence,
                        COUNT(*) FILTER (WHERE re_asr = true) as refined_count,
                        COUNT(*) FILTER (WHERE embedding IS NOT NULL) as embedded_count
                    FROM segments 
                    WHERE video_id = %s 
                    GROUP BY speaker_label
                """, (video_id,))
                
                speaker_stats = {}
                total_segments = 0
                total_duration = 0.0
                
                for row in cur.fetchall():
                    speaker_label = row['speaker_label']
                    speaker_stats[speaker_label] = {
                        'segment_count': row['segment_count'],
                        'duration': float(row['total_duration'] or 0),
                        'avg_confidence': float(row['avg_confidence'] or 0),
                        'refined_count': row['refined_count'],
                        'embedded_count': row['embedded_count']
                    }
                    total_segments += row['segment_count']
                    total_duration += float(row['total_duration'] or 0)
                
                # Calculate percentages
                for speaker, stats in speaker_stats.items():
                    if total_duration > 0:
                        stats['percentage'] = (stats['duration'] / total_duration) * 100
                    else:
                        stats['percentage'] = 0
                
                return {
                    'video_id': video_id,
                    'total_segments': total_segments,
                    'total_duration': total_duration,
                    'speaker_stats': speaker_stats,
                    'chaffee_percentage': speaker_stats.get('CH', {}).get('percentage', 0)
                }
                
        except Exception as e:
            logger.error(f"Failed to get video stats for {video_id}: {e}")
            return {}
    
    def create_embedding_index(self):
        """Create pgvector index for embeddings (run after bulk loading)"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                logger.info("Creating pgvector index for embeddings...")
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS segments_embedding_idx
                    ON segments USING ivfflat (embedding vector_l2_ops) WITH (lists = 100)
                """)
                conn.commit()
                logger.info("pgvector index created successfully")
                
        except Exception as e:
            logger.error(f"Failed to create embedding index: {e}")
            if conn:
                conn.rollback()
            raise
    
    def cleanup_old_segments(self, video_id: str):
        """Remove existing segments for a video (for re-processing)"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM segments WHERE video_id = %s", (video_id,))
                deleted_count = cur.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} existing segments for {video_id}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup segments for {video_id}: {e}")
            if conn:
                conn.rollback()
            raise
    
    def close(self):
        """Close database connection"""
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.connection = None
