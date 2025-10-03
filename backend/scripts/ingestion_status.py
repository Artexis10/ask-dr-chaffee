#!/usr/bin/env python3
"""Comprehensive ingestion status check"""
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect('postgresql://postgres:password@localhost:5432/askdrchaffee')
cur = conn.cursor()

print("=" * 80)
print("INGESTION STATUS REPORT")
print("=" * 80)

# Total videos and segments
cur.execute('SELECT COUNT(*) FROM sources')
total_sources = cur.fetchone()[0]

cur.execute('SELECT COUNT(*) FROM segments')
total_segments = cur.fetchone()[0]

cur.execute('SELECT COUNT(DISTINCT video_id) FROM segments')
videos_with_segments = cur.fetchone()[0]

print(f"\nDATABASE OVERVIEW:")
print(f"  Total sources: {total_sources}")
print(f"  Videos with segments: {videos_with_segments}")
print(f"  Total segments: {total_segments:,}")
print(f"  Avg segments per video: {total_segments/videos_with_segments if videos_with_segments > 0 else 0:.1f}")

# Average duration
cur.execute('SELECT AVG(duration_s)/60.0, SUM(duration_s)/3600.0 FROM sources WHERE duration_s IS NOT NULL')
avg_duration, total_hours = cur.fetchone()
print(f"\nDURATION STATS:")
print(f"  Average video duration: {avg_duration:.1f} minutes")
print(f"  Total audio processed: {total_hours:.1f} hours")

# Recent activity (last hour)
cur.execute("""
    SELECT COUNT(*), MAX(created_at)
    FROM sources 
    WHERE created_at > NOW() - INTERVAL '1 hour'
""")
recent_sources, last_source_time = cur.fetchone()

cur.execute("""
    SELECT COUNT(DISTINCT video_id)
    FROM segments 
    WHERE created_at > NOW() - INTERVAL '1 hour'
""")
recent_videos = cur.fetchone()[0]

print(f"\nRECENT ACTIVITY (last hour):")
print(f"  New sources added: {recent_sources}")
print(f"  Videos processed: {recent_videos}")
if last_source_time:
    print(f"  Last activity: {last_source_time}")

# Check for duplicates
cur.execute("""
    SELECT COUNT(*) 
    FROM (
        SELECT video_id, text, COUNT(*) as cnt
        FROM segments
        GROUP BY video_id, text
        HAVING COUNT(*) > 1
    ) dup
""")
duplicate_patterns = cur.fetchone()[0]

if duplicate_patterns > 0:
    print(f"\nWARNING: {duplicate_patterns} duplicate text patterns found!")
else:
    print(f"\nOK: No duplicates detected")

# Check for NULL speaker labels
cur.execute("SELECT COUNT(*) FROM segments WHERE speaker_label IS NULL")
null_speakers = cur.fetchone()[0]

if null_speakers > 0:
    print(f"WARNING: {null_speakers} segments with NULL speaker_label!")
else:
    print(f"OK: All segments have speaker labels")

# Check for NULL embeddings
cur.execute("SELECT COUNT(*) FROM segments WHERE embedding IS NULL")
null_embeddings = cur.fetchone()[0]

print(f"\nEMBEDDING STATUS:")
print(f"  Segments with embeddings: {total_segments - null_embeddings:,}")
print(f"  Segments without embeddings: {null_embeddings:,}")
print(f"  Embedding coverage: {((total_segments - null_embeddings)/total_segments*100) if total_segments > 0 else 0:.1f}%")

# Latest videos processed
cur.execute("""
    SELECT s.source_id, s.title, s.duration_s/60.0, COUNT(seg.id) as seg_count
    FROM sources s
    LEFT JOIN segments seg ON s.source_id = seg.video_id
    GROUP BY s.id, s.source_id, s.title, s.duration_s
    ORDER BY s.created_at DESC
    LIMIT 5
""")

print(f"\nLATEST VIDEOS PROCESSED:")
for video_id, title, duration, seg_count in cur.fetchall():
    print(f"  {video_id}: {title[:50]} ({duration:.1f}min, {seg_count} segments)")

print("\n" + "=" * 80)

conn.close()
