#!/usr/bin/env python3

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/askdrchaffee')

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Test the exact query that the API would use
    query = "carnivore diet benefits"
    search_pattern = f"%{query}%"
    
    print(f"Testing search for: '{query}'")
    print(f"Search pattern: '{search_pattern}'")
    
    # This matches the fallback query from the API
    search_query = """
        SELECT 
          c.id,
          c.source_id,
          s.source_id as video_id,
          s.title,
          c.text,
          c.start_time_seconds,
          c.end_time_seconds,
          s.published_at,
          s.source_type,
          0.5 as similarity
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        WHERE c.text ILIKE %s
        ORDER BY 
          CASE WHEN c.text ILIKE %s THEN 1 ELSE 2 END,
          COALESCE(s.provenance, 'yt_caption') = 'owner' DESC,
          s.published_at DESC,
          c.start_time_seconds ASC
        LIMIT %s
    """
    
    cur.execute(search_query, [search_pattern, search_pattern, 40])
    results = cur.fetchall()
    
    print(f"\nFound {len(results)} results")
    
    if results:
        print("\nFirst 3 results:")
        for i, row in enumerate(results[:3]):
            print(f"{i+1}. Video: {row[2]} | Text: {row[4][:100]}...")
    else:
        # Try simpler searches
        print("\nTrying simpler searches...")
        
        cur.execute("SELECT COUNT(*) FROM chunks WHERE text ILIKE %s", ['%carnivore%'])
        carnivore_count = cur.fetchone()[0]
        print(f"Chunks with 'carnivore': {carnivore_count}")
        
        cur.execute("SELECT COUNT(*) FROM chunks WHERE text ILIKE %s", ['%diet%'])
        diet_count = cur.fetchone()[0]
        print(f"Chunks with 'diet': {diet_count}")
        
        if carnivore_count > 0:
            cur.execute("SELECT text FROM chunks WHERE text ILIKE %s LIMIT 2", ['%carnivore%'])
            samples = cur.fetchall()
            print(f"\nSample carnivore chunks:")
            for sample in samples:
                print(f"  - {sample[0][:150]}...")
    
    conn.close()
    
except Exception as e:
    print(f'Database error: {e}')
