#!/usr/bin/env python3
"""Full chunk breakdown for quality verification of video 3GlEPRo5yjY"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

print('=== COMPLETE CHUNK BREAKDOWN: 3GlEPRo5yjY ===')
print('Title: "Are You Willing To Give Up What\'s Making You Sick?"')
print('System Result: 95.1% Chaffee, 4.9% Unknown')
print('=' * 80)

# Get all chunks with full text
cur.execute("""
    SELECT start_time_seconds, end_time_seconds, text, chunk_index
    FROM chunks 
    WHERE source_id = (SELECT id FROM sources WHERE source_id = '3GlEPRo5yjY')
    ORDER BY start_time_seconds
""")

chunks = cur.fetchall()
total_duration = 0

for i, (start, end, text, chunk_idx) in enumerate(chunks, 1):
    start_min, start_sec = int(start)//60, int(start)%60
    end_min, end_sec = int(end)//60, int(end)%60
    duration = end - start
    total_duration += duration
    
    print(f'\nCHUNK {i:2d} [{start_min:02d}:{start_sec:02d}-{end_min:02d}:{end_sec:02d}] ({duration:.1f}s)')
    print('-' * 60)
    print(text)
    print()

print('=' * 80)
print(f'SUMMARY:')
print(f'Total chunks: {len(chunks)}')
print(f'Total attributed time: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)')
print(f'Video duration: 8:40 (520 seconds)')
print(f'Coverage: {total_duration/520*100:.1f}%')
print()
print('VERIFICATION QUESTIONS:')
print('1. Do all chunks sound like Dr. Chaffee speaking?')
print('2. Are there any obvious guest voices that should be "Unknown"?')
print('3. Does the medical terminology and speaking style match Dr. Chaffee?')
print('4. Are there gaps where guest speech might have been correctly excluded?')

conn.close()
