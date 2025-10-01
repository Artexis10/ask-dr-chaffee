#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run database migrations"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()

def run_migration(migration_file):
    """Run a migration file with proper error handling"""
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cur = conn.cursor()
    
    try:
        # Check if segments table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'segments'
            );
        """)
        segments_exists = cur.fetchone()[0]
        
        if not segments_exists:
            print("⚠️  Segments table doesn't exist. Running migration 005 first...")
            with open('db/migrations/005_enhanced_segments.sql', 'r') as f:
                cur.execute(f.read())
            conn.commit()
            print("✅ Migration 005 completed")
        
        # Run the requested migration
        print(f"\n🔄 Running {migration_file}...")
        with open(migration_file, 'r', encoding='utf-8') as f:
            sql = f.read()
        
        # Split into statements more carefully
        statements = []
        current_stmt = []
        in_comment = False
        
        for line in sql.split('\n'):
            stripped = line.strip()
            
            # Skip empty lines and comment-only lines
            if not stripped or stripped.startswith('--'):
                continue
            
            # Add line to current statement
            current_stmt.append(line)
            
            # Check if statement ends with semicolon
            if stripped.endswith(';'):
                stmt = '\n'.join(current_stmt).strip()
                if stmt:
                    statements.append(stmt)
                current_stmt = []
        
        # Execute each statement
        success_count = 0
        warning_count = 0
        
        for i, statement in enumerate(statements, 1):
            # Extract statement type for display
            stmt_type = statement.split()[0].upper() if statement else "UNKNOWN"
            
            # Show what we're executing
            preview = statement[:80].replace('\n', ' ')
            if len(statement) > 80:
                preview += "..."
            
            print(f"  [{i}/{len(statements)}] {stmt_type}: {preview}")
            
            try:
                cur.execute(statement)
                conn.commit()
                success_count += 1
                print(f"      ✅ Success")
            except Exception as e:
                error_msg = str(e).split('\n')[0]  # First line of error
                
                # Check if it's a benign error (e.g., column doesn't exist)
                if 'does not exist' in error_msg or 'already exists' in error_msg:
                    print(f"      ⚠️  Skipped: {error_msg}")
                    warning_count += 1
                    conn.rollback()
                    cur = conn.cursor()  # Get new cursor after rollback
                else:
                    # This is a real error
                    print(f"      ❌ ERROR: {error_msg}")
                    conn.rollback()
                    raise Exception(f"Migration failed at statement {i}: {error_msg}")
        
        print(f"\n✅ Migration completed: {success_count} statements executed, {warning_count} skipped")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        run_migration(sys.argv[1])
    else:
        run_migration('db/migrations/007_sources_rich_metadata.sql')
