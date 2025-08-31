#!/usr/bin/env python3
"""
Test script for semantic search functionality.
Demonstrates how to perform vector similarity search.
"""

import os
import sys
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.database import DatabaseManager
from scripts.common.embeddings import EmbeddingGenerator

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SearchTester:
    def __init__(self):
        self.db = DatabaseManager()
        self.embedder = EmbeddingGenerator()
    
    def search_semantic(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Perform semantic search using vector similarity"""
        # Generate embedding for query
        query_embedding = self.embedder.generate_single_embedding(query)
        
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        s.title, s.url, s.source_type, c.text, 
                        c.start_time_seconds, c.end_time_seconds,
                        (c.embedding <=> %s::vector) as similarity
                    FROM chunks c
                    JOIN sources s ON c.source_id = s.id
                    WHERE c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                """, (query_embedding, query_embedding, limit))
                
                results = []
                for row in cur.fetchall():
                    results.append({
                        'title': row[0],
                        'url': row[1],
                        'source_type': row[2],
                        'text': row[3],
                        'start_time_seconds': row[4],
                        'end_time_seconds': row[5],
                        'similarity': float(row[6])
                    })
                
                return results
    
    def search_text(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Perform text-based search for comparison"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        s.title, s.url, s.source_type, c.text, 
                        c.start_time_seconds, c.end_time_seconds,
                        0.5 as similarity
                    FROM chunks c
                    JOIN sources s ON c.source_id = s.id
                    WHERE 
                        c.text ILIKE %s
                        OR s.title ILIKE %s
                    ORDER BY 
                        CASE 
                            WHEN c.text ILIKE %s THEN 1
                            WHEN s.title ILIKE %s THEN 2
                            ELSE 3
                        END,
                        c.start_time_seconds ASC
                    LIMIT %s
                """, (f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%', limit))
                
                results = []
                for row in cur.fetchall():
                    results.append({
                        'title': row[0],
                        'url': row[1],
                        'source_type': row[2],
                        'text': row[3],
                        'start_time_seconds': row[4],
                        'end_time_seconds': row[5],
                        'similarity': float(row[6])
                    })
                
                return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                # Count sources and chunks
                cur.execute("SELECT COUNT(*) FROM sources")
                source_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
                embedded_count = cur.fetchone()[0]
                
                # Get source breakdown
                cur.execute("""
                    SELECT source_type, COUNT(*) 
                    FROM sources 
                    GROUP BY source_type
                """)
                source_breakdown = dict(cur.fetchall())
                
                return {
                    'total_sources': source_count,
                    'total_chunks': chunk_count,
                    'embedded_chunks': embedded_count,
                    'embedding_progress': f"{embedded_count}/{chunk_count}" if chunk_count > 0 else "0/0",
                    'source_breakdown': source_breakdown
                }

def main():
    """Main test interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test search functionality')
    parser.add_argument('--query', type=str, help='Search query to test')
    parser.add_argument('--limit', type=int, default=5, help='Number of results to return')
    parser.add_argument('--stats', action='store_true', help='Show database statistics')
    
    args = parser.parse_args()
    
    tester = SearchTester()
    
    if args.stats:
        stats = tester.get_stats()
        print("\n=== Database Statistics ===")
        print(f"Total Sources: {stats['total_sources']}")
        print(f"Total Chunks: {stats['total_chunks']}")
        print(f"Embedded Chunks: {stats['embedding_progress']}")
        print(f"Source Breakdown: {stats['source_breakdown']}")
        print()
    
    if args.query:
        print(f"\n=== Searching for: '{args.query}' ===")
        
        # Try semantic search first
        try:
            semantic_results = tester.search_semantic(args.query, args.limit)
            print(f"\n--- Semantic Search Results ({len(semantic_results)}) ---")
            for i, result in enumerate(semantic_results, 1):
                similarity_pct = (1 - result['similarity']) * 100
                print(f"\n{i}. [{result['source_type'].upper()}] {result['title']}")
                print(f"   Relevance: {similarity_pct:.1f}%")
                print(f"   Time: {result['start_time_seconds']:.0f}s - {result['end_time_seconds']:.0f}s")
                print(f"   Text: {result['text'][:200]}...")
                if result['url']:
                    print(f"   URL: {result['url']}")
        except Exception as e:
            print(f"Semantic search failed: {e}")
            print("This is normal if embeddings haven't been generated yet.")
        
        # Fallback to text search
        text_results = tester.search_text(args.query, args.limit)
        print(f"\n--- Text Search Results ({len(text_results)}) ---")
        for i, result in enumerate(text_results, 1):
            print(f"\n{i}. [{result['source_type'].upper()}] {result['title']}")
            print(f"   Time: {result['start_time_seconds']:.0f}s - {result['end_time_seconds']:.0f}s")
            # Handle Unicode characters that can't be displayed in Windows console
            text_safe = result['text'][:200].encode('ascii', 'ignore').decode('ascii')
            print(f"   Text: {text_safe}...")
            if result['url']:
                print(f"   URL: {result['url']}")
    
    if not args.query and not args.stats:
        print("Use --query 'your search' to test search or --stats to show database info")
        print("Example: python test_search.py --query 'carnivore diet' --limit 3")

if __name__ == '__main__':
    main()
