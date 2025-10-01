#!/usr/bin/env python3
"""Convenience wrapper for running migrations"""
import sys
from utils.database.run_migration import run_migration

if __name__ == '__main__':
    if len(sys.argv) > 1:
        run_migration(sys.argv[1])
    else:
        print("Usage: python migrate.py <migration_file>")
        print("Example: python migrate.py db/migrations/008_cleanup_redundant_fields.sql")
