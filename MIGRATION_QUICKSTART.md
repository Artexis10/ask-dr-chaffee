# Migration System Quick Start

## ✅ What Was Set Up

You now have a **professional database migration system** using Alembic!

### Files Created:
```
backend/
├── alembic.ini                                        # Configuration
├── migrations/
│   ├── env.py                                        # Environment setup
│   ├── script.py.mako                                # Template
│   ├── README.md                                     # Full documentation
│   └── versions/
│       ├── 001_initial_schema.py                    # Initial DB setup
│       └── 002_fix_duplicates_and_speaker_labels.py # Duplicate fixes
└── requirements.txt (updated)                        # Added alembic + sqlalchemy
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r backend/requirements.txt
```

### 2. Apply Migrations

```bash
cd backend
alembic upgrade head
```

This will:
- ✅ Create your database schema (sources, segments, api_cache tables)
- ✅ Set up pgvector extension
- ✅ Create all indexes
- ✅ Remove any duplicate segments
- ✅ Fix NULL speaker labels

### 3. Verify

```bash
# Check current migration
alembic current

# Should show:
# 002 (head)
```

## 📝 Common Commands

### Apply All Migrations
```bash
cd backend
alembic upgrade head
```

### Check Status
```bash
alembic current
alembic history
```

### Rollback One Step
```bash
alembic downgrade -1
```

### Create New Migration
```bash
alembic revision -m "Add new feature"
```

## 🔄 Workflow

### For Fresh Database (Development)

**Option A: Use migrations (preserves if data exists)**
```bash
cd backend
alembic upgrade head
```

**Option B: Use reset script (destroys data)**
```bash
python backend/scripts/reset_database_clean.py
cd backend
alembic stamp head  # Mark as up-to-date
```

### For Existing Database (Production)

**Always use migrations:**
```bash
cd backend
alembic upgrade head
```

## 🎯 Benefits Over Reset Script

| Feature | reset_database_clean.py | Alembic Migrations |
|---------|------------------------|-------------------|
| Preserves data | ❌ No | ✅ Yes |
| Version control | ❌ No | ✅ Yes |
| Rollback | ❌ No | ✅ Yes |
| Team collaboration | ❌ Hard | ✅ Easy |
| Production-safe | ❌ No | ✅ Yes |
| Incremental changes | ❌ No | ✅ Yes |

## 📚 Documentation

**Full documentation:** `backend/migrations/README.md`

Includes:
- Creating new migrations
- Best practices
- Production workflow
- Troubleshooting
- Advanced examples

## 🔧 Integration with Your Pipeline

### Before Starting Ingestion

```bash
# Ensure database is up-to-date
cd backend
alembic upgrade head

# Then start ingestion
cd ..
python backend/scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 50
```

### In Production

```bash
# Deploy workflow
git pull
pip install -r backend/requirements.txt
cd backend
alembic upgrade head  # Apply any new migrations
cd ..
# Start services...
```

## ⚠️ Important Notes

### Migration 002 (Duplicate Fixes)

When you run `alembic upgrade head`, migration 002 will:
1. Remove duplicate segments (keeps first occurrence)
2. Fix NULL speaker labels → 'Chaffee'
3. Add unique constraint to prevent future duplicates

**This is exactly what you need** to fix the issue you saw in your screenshot!

### Reset Script Still Useful

Keep `reset_database_clean.py` for:
- Local development fresh starts
- Testing
- CI/CD test databases

Just remember to run `alembic stamp head` after using it.

## 🎉 Summary

You now have:
- ✅ Professional migration system
- ✅ Initial schema migration (001)
- ✅ Duplicate fix migration (002)
- ✅ Full documentation
- ✅ Production-ready workflow

**Next step:** Run `pip install -r backend/requirements.txt` then `alembic upgrade head`!
