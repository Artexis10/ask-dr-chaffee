# Embedding Dimensions Configuration Guide

## How to Change Embedding Models

The system supports different embedding models with different dimensions. The database schema automatically adapts to the dimensions specified in `.env`.

## Supported Models

### 384 Dimensions
- `sentence-transformers/all-MiniLM-L6-v2` (fast, lightweight)
- `sentence-transformers/all-MiniLM-L12-v2`
- `thenlper/gte-small`

### 768 Dimensions
- `sentence-transformers/all-mpnet-base-v2`
- `thenlper/gte-base`
- `BAAI/bge-base-en-v1.5`

### 1024 Dimensions
- `thenlper/gte-large`
- `BAAI/bge-large-en-v1.5`

### 1536 Dimensions (Default)
- `Alibaba-NLP/gte-Qwen2-1.5B-instruct` ✅ **Current**
- `Alibaba-NLP/gte-Qwen2-7B-instruct`

## How to Switch Models

### 1. Update .env

```bash
# Change embedding model and dimensions
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS=384
```

### 2. Run Migration

```bash
cd backend
alembic upgrade head
```

The migration will:
- Read `EMBEDDING_DIMENSIONS` from `.env`
- Update the database column to the new dimensions
- Recreate the pgvector index
- Update column comments

### 3. Clear Old Embeddings (Optional)

If you have existing embeddings with different dimensions:

```bash
# Option A: Clear all data (preserves schema)
python backend/scripts/cleanup_database_data.py

# Option B: Just clear embeddings
UPDATE segments SET embedding = NULL;
```

### 4. Regenerate Embeddings

Re-run ingestion to generate new embeddings:

```bash
python backend/scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 50
```

## Migration Details

**Migration:** `003_update_embedding_dimensions.py`

**What it does:**
1. Drops existing `segments_embedding_idx` index
2. Alters `segments.embedding` column to `vector(EMBEDDING_DIMENSIONS)`
3. Recreates index with optimal `lists` parameter
4. Updates column comment with current dimensions

**Rollback:**
```bash
cd backend
alembic downgrade -1
```

This reverts to 384 dimensions (original default).

## Performance Considerations

### Dimension Trade-offs

| Dimensions | Speed | Accuracy | VRAM | Storage |
|-----------|-------|----------|------|---------|
| 384 | ⚡⚡⚡ Fast | ⭐⭐ Good | 1-2GB | Small |
| 768 | ⚡⚡ Medium | ⭐⭐⭐ Better | 2-4GB | Medium |
| 1024 | ⚡ Slower | ⭐⭐⭐⭐ Great | 4-6GB | Large |
| 1536 | ⚡ Slowest | ⭐⭐⭐⭐⭐ Best | 6-10GB | Largest |

### Index Parameters

The migration automatically calculates optimal `lists` parameter:

```python
lists = max(100, min(1000, dimensions // 10))
```

- 384 dims → lists=100
- 768 dims → lists=100
- 1024 dims → lists=102
- 1536 dims → lists=153

## Example Workflows

### Switch to Lightweight Model (384-dim)

```bash
# 1. Update .env
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS=384

# 2. Run migration
cd backend
alembic upgrade head

# 3. Clear old embeddings
python backend/scripts/cleanup_database_data.py

# 4. Regenerate
cd ..
python backend/scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 100
```

### Switch to High-Quality Model (1536-dim)

```bash
# 1. Update .env
EMBEDDING_MODEL=Alibaba-NLP/gte-Qwen2-1.5B-instruct
EMBEDDING_DIMENSIONS=1536

# 2. Run migration
cd backend
alembic upgrade head

# 3. Regenerate embeddings
cd ..
python backend/scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 100
```

## Troubleshooting

### Error: "expected X dimensions, not Y"

This means the database has different dimensions than your model.

**Solution:**
```bash
cd backend
alembic upgrade head  # Re-run migration to sync
```

### Migration Failed

If migration fails partway:

```bash
# Check current state
cd backend
alembic current

# Manually fix if needed
python ../fix_embedding_dimensions.py

# Stamp as complete
alembic stamp 003
```

### Want to Test Different Models

```bash
# 1. Backup database
pg_dump $DATABASE_URL > backup.sql

# 2. Test new model
# Update .env, run migration, regenerate embeddings

# 3. If not satisfied, restore
psql $DATABASE_URL < backup.sql
alembic stamp 002  # Reset migration state
```

## Best Practices

1. **Choose model based on use case:**
   - Fast search: 384-dim models
   - Balanced: 768-dim models
   - Best quality: 1536-dim models

2. **Always run migration after changing dimensions:**
   ```bash
   cd backend && alembic upgrade head
   ```

3. **Clear old embeddings when switching:**
   - Different dimensions are incompatible
   - Must regenerate all embeddings

4. **Test on small dataset first:**
   ```bash
   python backend/scripts/ingest_youtube_enhanced.py --limit 10
   ```

5. **Monitor VRAM usage:**
   - Larger dimensions use more VRAM
   - Ensure your GPU can handle it

## Summary

✅ **Flexible:** Change models via `.env`
✅ **Automated:** Migration handles schema updates
✅ **Safe:** Rollback capability
✅ **Documented:** Clear upgrade/downgrade paths

The system is now fully configurable for different embedding models!
