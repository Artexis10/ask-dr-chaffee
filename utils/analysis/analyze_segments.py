#!/usr/bin/env python3
"""
Analyze segment text lengths and their impact on semantic search quality.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def analyze_segments():
    db_url = os.getenv('DATABASE_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            print('=== SEGMENT TEXT LENGTH ANALYSIS ===')
            
            # Basic stats
            cur.execute('SELECT COUNT(*) FROM segments')
            total_segments = cur.fetchone()[0]
            print(f'Total Segments: {total_segments}')
            
            # Text length analysis
            cur.execute('''
                SELECT 
                    MIN(LENGTH(text)) as min_chars,
                    MAX(LENGTH(text)) as max_chars,
                    AVG(LENGTH(text)) as avg_chars
                FROM segments
            ''')
            stats = cur.fetchone()
            min_chars, max_chars, avg_chars = stats
            
            print(f'\nText Length Statistics:')
            print(f'   Min: {min_chars} characters')
            print(f'   Max: {max_chars} characters')
            print(f'   Avg: {avg_chars:.1f} characters')
            
            # Duration analysis
            cur.execute('SELECT AVG(end_sec - start_sec) FROM segments')
            avg_duration = cur.fetchone()[0]
            print(f'   Avg Duration: {avg_duration:.2f}s')
            
            # Distribution analysis
            cur.execute('SELECT COUNT(*) FROM segments WHERE LENGTH(text) < 50')
            very_short = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM segments WHERE LENGTH(text) < 100')
            short = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM segments WHERE LENGTH(text) >= 150')
            good_length = cur.fetchone()[0]
            
            print(f'\nLength Distribution:')
            print(f'   Very Short (<50 chars): {very_short} ({very_short/total_segments*100:.1f}%)')
            print(f'   Short (<100 chars): {short} ({short/total_segments*100:.1f}%)')
            print(f'   Good Length (>=150 chars): {good_length} ({good_length/total_segments*100:.1f}%)')
            
            # Sample segments
            print(f'\nSample Segments:')
            cur.execute('SELECT text, LENGTH(text), (end_sec - start_sec) FROM segments ORDER BY LENGTH(text) LIMIT 3')
            print('Shortest:')
            for text, length, duration in cur.fetchall():
                print(f'   {length} chars ({duration:.1f}s): "{text}"')
                
            cur.execute('SELECT text, LENGTH(text), (end_sec - start_sec) FROM segments ORDER BY LENGTH(text) DESC LIMIT 2')
            print('\nLongest:')
            for text, length, duration in cur.fetchall():
                preview = text[:80] + '...' if len(text) > 80 else text
                print(f'   {length} chars ({duration:.1f}s): "{preview}"')
            
            # Impact assessment
            print(f'\n=== SEARCH IMPACT ASSESSMENT ===')
            short_percentage = short/total_segments*100
            
            if short_percentage > 70:
                print('🔴 HIGH IMPACT: Segments are too short for good semantic search')
                print('   - Recommended: Implement segment merging strategy')
                print('   - Target: 150-300 characters per segment')
            elif short_percentage > 50:
                print('🟡 MEDIUM IMPACT: Many segments are short')
                print('   - Consider segment optimization')
            else:
                print('🟢 LOW IMPACT: Segment lengths are reasonable')
            
            print(f'\nRecommendations:')
            if avg_chars < 120:
                print('   - URGENT: Average segment length is too short for semantic search')
                print('   - Solution: Merge consecutive same-speaker segments')
                print('   - Target: 150-300 characters (current: {:.1f})'.format(avg_chars))
                print('   - This will significantly improve search relevance')
            
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    analyze_segments()
