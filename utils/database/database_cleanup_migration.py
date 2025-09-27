#!/usr/bin/env python3
"""
Database cleanup migration to remove redundant fields from sources table
- Remove unused 'duration_s' field (duplicate of duration_seconds)
- Remove unused 'description' field (not needed for ingestion)
"""

import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Run database cleanup migration"""
    print("Starting database cleanup migration...")
    
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    
    with conn.cursor() as cur:
        # Check current field usage
        print("Analyzing current field usage...")
        
        cur.execute('SELECT COUNT(*) FROM sources WHERE duration_seconds IS NOT NULL')
        duration_seconds_count = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM sources WHERE duration_s IS NOT NULL')  
        duration_s_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM sources WHERE description IS NOT NULL AND description != ''")
        description_count = cur.fetchone()[0]
        
        print(f"   duration_seconds with data: {duration_seconds_count}")
        print(f"   duration_s with data: {duration_s_count}") 
        print(f"   description with data: {description_count}")
        
        if duration_s_count > 0:
            print("WARNING: duration_s has data! Migration aborted.")
            return False
            
        if description_count > 0:
            print("WARNING: description has data! You may want to preserve it.")
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                return False
        
        print("Removing redundant fields...")
        
        # Remove duration_s column (redundant with duration_seconds)
        try:
            cur.execute('ALTER TABLE sources DROP COLUMN IF EXISTS duration_s')
            print("   Removed duration_s column")
        except Exception as e:
            print(f"   Failed to remove duration_s: {e}")
            return False
        
        # Remove description column (unused)
        try:
            cur.execute('ALTER TABLE sources DROP COLUMN IF EXISTS description')
            print("   Removed description column")
        except Exception as e:
            print(f"   Failed to remove description: {e}")
            return False
        
        # Commit changes
        conn.commit()
        print("Database cleanup migration completed successfully!")
        
        # Show updated schema
        print("Updated sources table schema:")
        cur.execute('''
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'sources' 
            ORDER BY ordinal_position
        ''')
        
        for row in cur.fetchall():
            col_name, data_type, nullable = row
            print(f"   {col_name:20} | {data_type:15} | {nullable}")
    
    conn.close()
    return True

if __name__ == "__main__":
    success = run_migration()
    exit(0 if success else 1)
