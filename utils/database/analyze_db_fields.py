#!/usr/bin/env python3
"""Analyze database field usage to identify missing values"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Check what fields are actually being used vs not used
cur.execute("""
    SELECT 
        COUNT(*) as total_sources,
        COUNT(duration_seconds) as has_duration_seconds, 
        COUNT(published_at) as has_published_at,
        COUNT(url) as has_url,
        COUNT(view_count) as has_view_count
    FROM sources 
    WHERE created_at > NOW() - INTERVAL '3 hours'
""")

result = cur.fetchone()
print('=== ESSENTIAL FIELD USAGE ANALYSIS ===')
total = result[0]
print(f'Total sources: {total}')
print(f'Sources with duration_seconds: {result[1]}/{total} ({result[1]/total*100:.1f}%)')
print(f'Sources with published_at: {result[2]}/{total} ({result[2]/total*100:.1f}%)')
print(f'Sources with url: {result[3]}/{total} ({result[3]/total*100:.1f}%)')
print(f'Sources with view_count: {result[4]}/{total} ({result[4]/total*100:.1f}%)')

# Check metadata fields
cur.execute("""
    SELECT 
        COUNT(CASE WHEN metadata->>'processing_timestamp' IS NOT NULL THEN 1 END) as has_processing_timestamp,
        COUNT(CASE WHEN metadata->>'confidence_stats' != '{}' THEN 1 END) as has_confidence_stats,
        COUNT(CASE WHEN metadata->>'similarity_stats' != '{}' THEN 1 END) as has_similarity_stats,
        COUNT(CASE WHEN metadata->>'segments_with_high_confidence' > '0' THEN 1 END) as has_high_conf_segments
    FROM sources 
    WHERE created_at > NOW() - INTERVAL '3 hours'
""")

result = cur.fetchone()
print(f'Sources with processing_timestamp: {result[0]}/{total} ({result[0]/total*100:.1f}%)')
print(f'Sources with confidence_stats: {result[1]}/{total} ({result[1]/total*100:.1f}%)')
print(f'Sources with similarity_stats: {result[2]}/{total} ({result[2]/total*100:.1f}%)')
print(f'Sources with high_confidence_segments: {result[3]}/{total} ({result[3]/total*100:.1f}%)')

# Sample the essential fields
print('\n=== SAMPLE ESSENTIAL FIELD VALUES ===')
cur.execute("""
    SELECT source_id, duration_seconds, published_at, url, view_count
    FROM sources 
    WHERE created_at > NOW() - INTERVAL '3 hours'
    LIMIT 3
""")

for row in cur.fetchall():
    print(f'Source {row[0]}:')
    print(f'  duration_seconds: {row[1] if row[1] else "NULL"}') 
    print(f'  published_at: {row[2] if row[2] else "NULL"}')
    print(f'  url: {row[3] if row[3] else "NULL"}')
    print(f'  view_count: {row[4] if row[4] else "NULL"}')

conn.close()
