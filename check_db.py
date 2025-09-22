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
    
    # Check chunks table
    cur.execute('SELECT COUNT(*) FROM chunks')
    chunk_count = cur.fetchone()[0]
    print(f'Total chunks: {chunk_count}')
    
    # Check sources table  
    cur.execute('SELECT COUNT(*) FROM sources')
    source_count = cur.fetchone()[0]
    print(f'Total sources: {source_count}')
    
    # Show sample sources
    cur.execute('SELECT source_id, title FROM sources LIMIT 5')
    print('\nSample sources:')
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1][:80]}...')
    
    # Check for embeddings
    cur.execute('SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL')
    embedded_count = cur.fetchone()[0]
    print(f'\nChunks with embeddings: {embedded_count}')
    
    # Sample chunks with carnivore content
    cur.execute("SELECT text FROM chunks WHERE text ILIKE '%carnivore%' LIMIT 3")
    carnivore_chunks = cur.fetchall()
    print(f'\nSample carnivore content ({len(carnivore_chunks)} chunks):')
    for i, chunk in enumerate(carnivore_chunks, 1):
        print(f'  {i}. {chunk[0][:100]}...')
    
    conn.close()
    print('\nDatabase connection successful!')
    
except Exception as e:
    print(f'Database error: {e}')
