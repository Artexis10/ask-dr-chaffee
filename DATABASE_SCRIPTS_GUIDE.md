# Database Management Scripts Guide

You now have **three different scripts** for managing your database, each with a specific purpose.

## 📁 Available Scripts

### 1. Alembic Migrations (RECOMMENDED for production)

**Location:** `backend/migrations/`

**Purpose:** Version-controlled schema changes

**Use when:**
- ✅ You need to modify the database schema
- ✅ You're working in production/staging
- ✅ You want to preserve existing data
- ✅ You need rollback capability

**Commands:**
```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Check current version
alembic current

# Rollback one migration
alembic downgrade -1

# Create new migration
alembic revision -m "Description"
```

**Example workflow:**
```bash
# Add new column to existing table
cd backend
alembic revision -m "Add transcription_quality to sources"
# Edit the migration file
alembic upgrade head  # Apply it
```

---

### 2. Data Cleanup Script (NEW!)

**Location:** `backend/scripts/cleanup_database_data.py`

**Purpose:** Remove all data, keep schema intact

**Use when:**
- ✅ You want a fresh start with data
- ✅ You want to preserve the schema
- ✅ You want to keep indexes and constraints
- ✅ Testing ingestion from scratch

**Command:**
```bash
python backend/scripts/cleanup_database_data.py
```

**What it does:**
- ❌ Removes ALL data from tables (TRUNCATE)
- ✅ Preserves table structure
- ✅ Preserves indexes (including pgvector)
- ✅ Preserves constraints
- ✅ Preserves extensions (pgvector)

**Output:**
```
[BEFORE] Current row counts:
  • segments: 44,328 rows
  • sources: 50 rows
  • api_cache: 120 rows

[CLEANUP] Removing all data...
  • Truncating segments...
  • Truncating sources...
  • Truncating api_cache...

[AFTER] Row counts after cleanup:
  • segments: 0 rows
  • sources: 0 rows
  • api_cache: 0 rows

✅ DATA CLEANUP SUCCESSFUL!
```

---

### 3. Full Database Reset (DESTRUCTIVE!)

**Location:** `backend/scripts/reset_database_clean.py`

**Purpose:** Complete database recreation

**Use when:**
- ✅ Local development only
- ✅ You need to change schema fundamentally
- ✅ You want to start completely fresh
- ⚠️  NEVER use in production!

**Command:**
```bash
python backend/scripts/reset_database_clean.py
```

**What it does:**
- ❌ Drops ALL tables
- ❌ Drops ALL extensions
- ❌ Drops ALL indexes
- ✅ Recreates everything from scratch

**After using reset script:**
```bash
# Mark database as up-to-date with migrations
cd backend
alembic stamp head
```

---

## 🎯 Decision Matrix

### Scenario: Need to add a new column

```bash
# ✅ CORRECT: Use migrations
cd backend
alembic revision -m "Add new column"
# Edit migration file
alembic upgrade head
```

```bash
# ❌ WRONG: Reset database
python backend/scripts/reset_database_clean.py  # Destroys all data!
```

---

### Scenario: Want to test ingestion from scratch

```bash
# ✅ OPTION A: Use data cleanup (preserves schema)
python backend/scripts/cleanup_database_data.py
python backend/scripts/ingest_youtube_enhanced.py ...
```

```bash
# ✅ OPTION B: Use migrations (clears and applies migration 002)
cd backend
alembic downgrade base  # Remove all data
alembic upgrade head    # Re-apply migrations
cd ..
python backend/scripts/ingest_youtube_enhanced.py ...
```

```bash
# ⚠️  OPTION C: Full reset (local dev only)
python backend/scripts/reset_database_clean.py
cd backend
alembic stamp head
cd ..
python backend/scripts/ingest_youtube_enhanced.py ...
```

---

### Scenario: Remove duplicate segments from current data

```bash
# ✅ CORRECT: Use migration 002
cd backend
alembic downgrade 001   # Go back to before duplicate fix
alembic upgrade head    # Re-apply migration 002 (removes duplicates)
```

```bash
# ❌ WRONG: Clear all data
python backend/scripts/cleanup_database_data.py  # Loses all progress!
```

---

### Scenario: Production deployment with schema change

```bash
# ✅ CORRECT: Use migrations
git pull
pip install -r backend/requirements.txt
cd backend
alembic upgrade head  # Only applies new migrations
```

```bash
# ❌ WRONG: Reset database
python backend/scripts/reset_database_clean.py  # DISASTER!
```

---

## 📊 Comparison Table

| Feature | Data Cleanup | Migrations | Full Reset |
|---------|-------------|------------|------------|
| **Removes data** | ✅ Yes | Depends* | ✅ Yes |
| **Preserves schema** | ✅ Yes | ✅ Yes | ❌ No |
| **Preserves indexes** | ✅ Yes | ✅ Yes | ❌ No |
| **Version controlled** | ❌ No | ✅ Yes | ❌ No |
| **Rollback capability** | ❌ No | ✅ Yes | ❌ No |
| **Production-safe** | ⚠️  Caution | ✅ Yes | ❌ NO! |
| **Requires confirmation** | ✅ Yes | Auto | ✅ Yes |
| **Speed** | Fast | Fast | Slow |

*Migration 002 removes duplicates, others preserve data

---

## 🚦 Recommended Workflow

### Development (Local)

```bash
# When starting fresh
python backend/scripts/cleanup_database_data.py
# OR
python backend/scripts/reset_database_clean.py
cd backend && alembic stamp head && cd ..

# When making schema changes
cd backend
alembic revision -m "Description"
# Edit migration
alembic upgrade head

# When testing
python backend/scripts/ingest_youtube_enhanced.py --limit 5
```

### Staging/Production

```bash
# Initial setup
cd backend
alembic upgrade head

# Deployments
git pull
pip install -r backend/requirements.txt
cd backend
alembic upgrade head  # Only applies new migrations

# NEVER use reset_database_clean.py!
# NEVER use cleanup_database_data.py without backup!
```

---

## ⚠️ Safety Guidelines

### Data Cleanup Script
- ✅ Use in development freely
- ⚠️  Use in staging with caution
- ❌ Use in production only with backup and approval

### Full Reset Script
- ✅ Use in local development only
- ❌ NEVER use in staging
- ❌ NEVER use in production

### Migrations
- ✅ Always safe (preserves data)
- ✅ Use everywhere (dev, staging, production)
- ✅ Version controlled with git

---

## 📝 Quick Reference

```bash
# Clean data, keep schema
python backend/scripts/cleanup_database_data.py

# Full reset (dev only)
python backend/scripts/reset_database_clean.py
cd backend && alembic stamp head

# Apply migrations (production-safe)
cd backend && alembic upgrade head

# Check migration status
cd backend && alembic current

# Create new migration
cd backend && alembic revision -m "Description"

# Rollback one migration
cd backend && alembic downgrade -1
```

---

## 🎉 Summary

**You now have:**
- ✅ Professional migration system (Alembic)
- ✅ Data cleanup script (preserves schema)
- ✅ Full reset script (development only)

**Best practices:**
1. Use migrations for all schema changes
2. Use data cleanup for fresh data (preserves schema)
3. Use full reset only in local development
4. Always test migrations locally before production
5. Commit migrations to version control

**Current status:**
- ✅ Alembic installed and configured
- ✅ Database stamped at migration 002
- ✅ Ready to use any script as needed
