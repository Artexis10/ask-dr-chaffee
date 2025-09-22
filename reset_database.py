#!/usr/bin/env python3
"""Reset database for clean start"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def reset_database():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cursor = conn.cursor()
    
    print("Cleaning database for fresh start...")
    
    # Delete all ingestion data (keep schema)
    tables_to_clear = [
        'chunks',
        'sources', 
        'ingest_state',
        'api_cache'
    ]
    
    for table in tables_to_clear:
        try:
            cursor.execute(f"DELETE FROM {table};")
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"Cleared {table}: {count} rows remaining")
        except Exception as e:
            print(f"Warning {table}: {e}")
    
    # Reset sequences
    try:
        cursor.execute("SELECT setval('sources_id_seq', 1, false);")
        cursor.execute("SELECT setval('chunks_id_seq', 1, false);")
        print("Reset ID sequences")
    except Exception as e:
        print(f"Warning Sequences: {e}")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print("\nDatabase reset complete - ready for fresh ingestion!")

if __name__ == "__main__":
    reset_database()
