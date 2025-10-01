# Database Migrations with Alembic

This directory contains database migrations managed by [Alembic](https://alembic.sqlalchemy.org/), the standard Python migration tool.

## Why Migrations?

**Before (reset_database_clean.py):**
- ❌ Destroys all data every time
- ❌ No version control
- ❌ Can't rollback
- ❌ Not production-safe

**After (Alembic migrations):**
- ✅ Incremental, versioned changes
- ✅ Preserves existing data
- ✅ Rollback capability
- ✅ Production-safe
- ✅ Team collaboration friendly

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `alembic>=1.13.0` - Migration framework
- `sqlalchemy>=2.0.0` - Database toolkit
- `psycopg2-binary>=2.9.9` - PostgreSQL adapter

### 2. Configure Database URL

Migrations read from your `.env` file:

```bash
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

## Common Commands

### Apply All Pending Migrations

```bash
cd backend
alembic upgrade head
```

This applies all migrations that haven't been run yet.

### Check Current Migration Status

```bash
cd backend
alembic current
```

Shows which migration is currently applied.

### View Migration History

```bash
cd backend
alembic history --verbose
```

Shows all available migrations.

### Rollback One Migration

```bash
cd backend
alembic downgrade -1
```

Rolls back the most recent migration.

### Rollback to Specific Version

```bash
cd backend
alembic downgrade 001
```

Rolls back to migration 001.

### Create New Migration

```bash
cd backend
alembic revision -m "Add new column to segments"
```

Creates a new empty migration file in `migrations/versions/`.

## Migration Files

### Structure

```
backend/
├── alembic.ini              # Alembic configuration
├── migrations/
│   ├── env.py              # Migration environment setup
│   ├── script.py.mako      # Template for new migrations
│   ├── versions/           # Migration files
│   │   ├── 001_initial_schema.py
│   │   ├── 002_fix_duplicates_and_speaker_labels.py
│   │   └── ...
│   └── README.md           # This file
```

### Existing Migrations

**001_initial_schema.py** - Initial database setup
- Creates `sources` table (video metadata)
- Creates `segments` table (transcripts with speaker attribution)
- Creates `api_cache` table (YouTube API caching)
- Creates pgvector extension and indexes
- Creates performance indexes

**002_fix_duplicates_and_speaker_labels.py** - Data quality fixes
- Removes duplicate segments
- Fixes NULL speaker labels (defaults to 'Chaffee')
- Adds unique constraint to prevent future duplicates

## Creating New Migrations

### Example: Add New Column

```bash
# Create migration file
cd backend
alembic revision -m "Add transcription_model to sources"
```

Edit the generated file:

```python
"""Add transcription_model to sources

Revision ID: 003
Revises: 002
Create Date: 2025-10-01 14:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'

def upgrade() -> None:
    op.add_column('sources',
        sa.Column('transcription_model', sa.String(100), nullable=True)
    )

def downgrade() -> None:
    op.drop_column('sources', 'transcription_model')
```

Apply it:

```bash
alembic upgrade head
```

### Example: Add New Index

```python
def upgrade() -> None:
    op.create_index(
        'idx_segments_created',
        'segments',
        ['created_at']
    )

def downgrade() -> None:
    op.drop_index('idx_segments_created')
```

### Example: Modify Existing Data

```python
def upgrade() -> None:
    # Add column with NULL allowed
    op.add_column('segments',
        sa.Column('language', sa.String(10), nullable=True)
    )
    
    # Set default value for existing rows
    op.execute("UPDATE segments SET language = 'en' WHERE language IS NULL")
    
    # Make column NOT NULL
    op.alter_column('segments', 'language',
                    existing_type=sa.String(10),
                    nullable=False)

def downgrade() -> None:
    op.drop_column('segments', 'language')
```

## Production Workflow

### 1. Development

```bash
# Create migration
alembic revision -m "Description of change"

# Edit the migration file
# ...

# Test locally
alembic upgrade head

# Verify it works
# ...

# Test rollback
alembic downgrade -1
alembic upgrade head
```

### 2. Version Control

```bash
git add migrations/versions/00X_description.py
git commit -m "Add migration: description"
git push
```

### 3. Production Deployment

```bash
# On production server
git pull
pip install -r requirements.txt
alembic upgrade head
```

## Best Practices

### 1. Always Test Rollbacks

```bash
# Apply migration
alembic upgrade head

# Test rollback
alembic downgrade -1

# Re-apply
alembic upgrade head
```

### 2. Use Transactions

Alembic runs migrations in transactions by default. If a migration fails, it rolls back automatically.

### 3. Add Comments

```python
def upgrade() -> None:
    # Add speaker_verified column to track manual verification
    op.add_column('segments',
        sa.Column('speaker_verified', sa.Boolean(), 
                  nullable=False, 
                  server_default='false',
                  comment='Manually verified speaker attribution')
    )
```

### 4. Handle Data Migrations Carefully

```python
def upgrade() -> None:
    # BAD: This will fail if there are NULL values
    op.alter_column('segments', 'speaker_label', nullable=False)
    
    # GOOD: Fix data first, then add constraint
    op.execute("UPDATE segments SET speaker_label = 'Chaffee' WHERE speaker_label IS NULL")
    op.alter_column('segments', 'speaker_label', nullable=False)
```

### 5. Use Batch Operations for Large Tables

```python
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    with op.batch_alter_table('segments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('new_field', sa.String(50)))
        batch_op.create_index('idx_new_field', ['new_field'])
```

## Comparison: Reset Script vs Migrations

### When to Use reset_database_clean.py

- ✅ Local development (fresh start)
- ✅ Testing
- ✅ CI/CD test databases

### When to Use Alembic Migrations

- ✅ Production databases
- ✅ Staging environments
- ✅ Any database with data you want to preserve
- ✅ Team collaboration
- ✅ Schema version control

## Troubleshooting

### Migration Failed

```bash
# Check current state
alembic current

# Check history
alembic history

# Manual rollback if needed
alembic downgrade <previous_version>
```

### Database Out of Sync

```bash
# Stamp database as current version (use carefully!)
alembic stamp head

# Or specific version
alembic stamp 001
```

### Conflict Between Migrations

```bash
# Check for multiple heads
alembic heads

# Merge if needed
alembic merge -m "Merge conflicting migrations" <rev1> <rev2>
```

## Integration with reset_database_clean.py

The reset script is still useful for local development. After running it:

```bash
# Reset database
python backend/scripts/reset_database_clean.py

# Mark as migrated (skip running migrations)
cd backend
alembic stamp head
```

This tells Alembic the database is up-to-date without running migrations.

## Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)

## Support

For questions or issues with migrations:
1. Check this README
2. Review existing migrations in `versions/`
3. Consult Alembic documentation
4. Test changes locally before deploying to production
