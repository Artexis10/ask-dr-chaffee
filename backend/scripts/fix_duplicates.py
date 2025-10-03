#!/usr/bin/env python3
"""Remove duplicate segments from the database"""
import psycopg2

conn = psycopg2.connect('postgresql://postgres:password@localhost:5432/askdrchaffee')
cur = conn.cursor()

print("Removing duplicate segments...")
print("This will keep the first occurrence of each (video_id, text) pair\n")

# Delete duplicates, keeping only the first occurrence (lowest id)
cur.execute('''
    DELETE FROM segments
    WHERE id IN (
        SELECT id
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY video_id, text ORDER BY id) as rn
            FROM segments
        ) t
        WHERE t.rn > 1
    )
''')

deleted_count = cur.rowcount
conn.commit()

print(f"DELETED {deleted_count:,} duplicate segments")

# Check remaining
cur.execute('SELECT COUNT(*) FROM segments')
remaining = cur.fetchone()[0]
print(f"Remaining segments: {remaining:,}")

conn.close()
