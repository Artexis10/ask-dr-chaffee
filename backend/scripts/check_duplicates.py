#!/usr/bin/env python3
"""Quick diagnostic script to check for duplicate segments"""
import psycopg2

conn = psycopg2.connect('postgresql://postgres:password@localhost:5432/askdrchaffee')
cur = conn.cursor()

# Average video duration
cur.execute('SELECT AVG(duration_s)/60.0 as avg_minutes, COUNT(*) as total_videos FROM sources WHERE duration_s IS NOT NULL')
result = cur.fetchone()
print(f"Average video duration: {result[0]:.1f} minutes")
print(f"Total videos: {result[1]}\n")

# Total segments
cur.execute('SELECT COUNT(*) FROM segments')
total_segments = cur.fetchone()[0]
print(f"Total segments in DB: {total_segments:,}\n")

# Duplicate segments
cur.execute('''
    SELECT video_id, text, COUNT(*) as dup_count 
    FROM segments 
    GROUP BY video_id, text 
    HAVING COUNT(*) > 1 
    ORDER BY dup_count DESC 
    LIMIT 20
''')
duplicates = cur.fetchall()

if duplicates:
    print(f"Found {len(duplicates)} unique duplicate text patterns:\n")
    total_duplicate_segments = 0
    for video_id, text, count in duplicates:
        print(f"  {video_id}: {count} copies of '{text[:70]}...'")
        total_duplicate_segments += (count - 1)  # -1 because one is the original
    print(f"\nTotal duplicate segments (wasted): {total_duplicate_segments:,}")
    print(f"Percentage of DB that's duplicates: {(total_duplicate_segments/total_segments)*100:.1f}%")
else:
    print("No duplicates found!")

# Check one specific video
cur.execute('''
    SELECT video_id, COUNT(*) as segment_count, COUNT(DISTINCT text) as unique_texts
    FROM segments
    WHERE video_id = 'l0plgGC4HmU'
    GROUP BY video_id
''')
result = cur.fetchone()
if result:
    print(f"\nVideo l0plgGC4HmU:")
    print(f"  Total segments: {result[1]}")
    print(f"  Unique texts: {result[2]}")
    print(f"  Duplicates: {result[1] - result[2]}")

conn.close()
