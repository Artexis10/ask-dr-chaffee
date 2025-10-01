"""Update embedding dimensions to support configurable models

Revision ID: 003
Revises: 002
Create Date: 2025-10-01 14:04:00

This migration updates the embedding column to support the dimensions
specified in EMBEDDING_DIMENSIONS env var (default: 1536 for GTE-Qwen2-1.5B-instruct).

The migration reads from .env to determine the target dimensions, allowing
flexibility for different embedding models:
- 384 dims: all-MiniLM-L6-v2, gte-small
- 768 dims: gte-base
- 1024 dims: gte-large
- 1536 dims: gte-Qwen2-1.5B-instruct (default)

"""
from alembic import op
import sqlalchemy as sa
import os
from dotenv import load_dotenv

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Load .env to get target dimensions
    load_dotenv()
    target_dims = int(os.getenv('EMBEDDING_DIMENSIONS', 1536))
    
    print(f"Updating embedding dimensions to {target_dims} (from EMBEDDING_DIMENSIONS env var)")
    
    # Drop the old index
    op.execute("DROP INDEX IF EXISTS segments_embedding_idx")
    
    # Alter the column type to new dimensions
    op.execute(f"ALTER TABLE segments ALTER COLUMN embedding TYPE vector({target_dims})")
    
    # Recreate the index with correct dimensions
    # Lists parameter scales with expected dataset size
    lists = max(100, min(1000, target_dims // 10))
    op.execute(f"""
        CREATE INDEX segments_embedding_idx 
        ON segments USING ivfflat (embedding vector_l2_ops) 
        WITH (lists = {lists})
    """)
    
    # Update column comment
    op.execute(f"""
        COMMENT ON COLUMN segments.embedding IS 
        'Text embedding vector for semantic search ({target_dims}-dim, from EMBEDDING_DIMENSIONS env var)'
    """)
    
    print(f"[OK] Embedding dimensions updated to {target_dims}")
    print(f"[OK] Index recreated with lists={lists}")


def downgrade() -> None:
    # Downgrade to 384 dimensions (original default)
    print("Downgrading embedding dimensions to 384")
    
    # Drop index
    op.execute("DROP INDEX IF EXISTS segments_embedding_idx")
    
    # Alter column back to 384
    op.execute("ALTER TABLE segments ALTER COLUMN embedding TYPE vector(384)")
    
    # Recreate index
    op.execute("""
        CREATE INDEX segments_embedding_idx 
        ON segments USING ivfflat (embedding vector_l2_ops) 
        WITH (lists = 100)
    """)
    
    # Update comment
    op.execute("""
        COMMENT ON COLUMN segments.embedding IS 
        'Text embedding vector for semantic search (384-dim)'
    """)
    
    print("[OK] Downgraded to 384 dimensions")
