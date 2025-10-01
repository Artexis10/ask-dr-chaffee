#!/usr/bin/env python3
"""Quick database cleanup without confirmation prompt"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

print("Cleaning database...")

# Truncate tables
cur.execute("TRUNCATE TABLE segments CASCADE")
cur.execute("TRUNCATE TABLE sources CASCADE")
cur.execute("TRUNCATE TABLE api_cache CASCADE")

conn.commit()

# Verify
cur.execute("SELECT COUNT(*) FROM segments")
segments_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM sources")
sources_count = cur.fetchone()[0]

print(f"Segments: {segments_count}")
print(f"Sources: {sources_count}")
print("Database cleaned!")

cur.close()
conn.close()
