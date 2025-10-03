#!/usr/bin/env python3
"""Add unique constraint to prevent duplicate segments"""
import psycopg2

conn = psycopg2.connect('postgresql://postgres:password@localhost:5432/askdrchaffee')
cur = conn.cursor()

print("Adding unique constraint to prevent duplicate segments...")

try:
    # Add unique constraint on (video_id, start_sec, end_sec, text)
    # This prevents the same segment from being inserted twice
    cur.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS segments_unique_idx 
        ON segments (video_id, start_sec, end_sec, text)
    ''')
    conn.commit()
    print("SUCCESS: Unique constraint added!")
    print("Future duplicate insertions will be rejected automatically.")
except Exception as e:
    print(f"ERROR: {e}")
    conn.rollback()

conn.close()
