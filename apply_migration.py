#!/usr/bin/env python3
"""
Apply the enhanced segments migration
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def apply_migration():
    """Apply the enhanced segments migration"""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL not found in environment")
        return False
    
    try:
        # Read migration file
        with open('db/migrations/005_enhanced_segments.sql', 'r') as f:
            migration_sql = f.read()
        
        # Apply migration
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        
        with conn.cursor() as cur:
            print("Applying enhanced segments migration...")
            cur.execute(migration_sql)
            print("Migration applied successfully!")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Migration failed: {e}")
        return False

if __name__ == '__main__':
    apply_migration()
