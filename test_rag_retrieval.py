#!/usr/bin/env python3
"""
Test RAG retrieval functionality without OpenAI API calls
Shows the power of semantic search across 190 videos
"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from dotenv import load_dotenv
load_dotenv()

def test_semantic_search(query, max_chunks=8):
    """Test semantic search retrieval"""
    print(f"Testing semantic search for: '{query}'")
    print(f"Searching across your 190-video database...")
    print()
    
    try:
        from scripts.common.embeddings import EmbeddingGenerator
        import psycopg2
        
        # Generate query embedding
        embedder = EmbeddingGenerator()
        query_embedding = embedder.generate_embeddings([query])[0]
        
        # Search database
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.text, s.title, s.url,
                   1 - (c.embedding <=> %s::vector) as similarity
            FROM chunks c
            JOIN sources s ON c.source_id = s.id
            WHERE s.source_type = 'youtube'
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, max_chunks))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not results:
            print("No results found")
            return
        
        print(f"Found {len(results)} relevant chunks:")
        print("=" * 80)
        
        for i, (text, title, url, similarity) in enumerate(results, 1):
            # Extract video ID
            video_id = url.split('v=')[-1].split('&')[0] if 'v=' in url else url.split('/')[-1]
            
            print(f"\nResult {i} | Similarity: {similarity:.3f}")
            print(f"Video: {title}")
            print(f"URL: https://youtube.com/watch?v={video_id}")
            print(f"Content: {text[:200]}{'...' if len(text) > 200 else ''}")
            print("-" * 40)
        
        print(f"\nSearch completed successfully!")
        print(f"Average similarity: {sum(r[3] for r in results) / len(results):.3f}")
        print(f"These chunks would be sent to RAG for domain-aware summarization")
        
    except Exception as e:
        print(f"Error: {e}")

def test_multiple_queries():
    """Test multiple medical queries"""
    queries = [
        "What does Dr. Chaffee say about autoimmune conditions?",
        "How does the carnivore diet help with inflammation?",
        "What are Dr. Chaffee's views on plant toxins?",
        "Does Dr. Chaffee recommend any supplements?",
        "What does Dr. Chaffee think about ketosis?"
    ]
    
    for query in queries:
        test_semantic_search(query, max_chunks=5)
        print("\n" + "="*100 + "\n")

if __name__ == "__main__":
    print("RAG RETRIEVAL TEST - Your 190-Video Database")
    print("=" * 60)
    print()
    
    if len(sys.argv) > 1:
        # Single query from command line
        query = " ".join(sys.argv[1:])
        test_semantic_search(query)
    else:
        # Test multiple queries
        test_multiple_queries()
