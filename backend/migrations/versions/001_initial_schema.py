"""Initial database schema with pgvector support

Revision ID: 001
Revises: 
Create Date: 2025-10-01 13:10:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create sources table (merged videos + processing state)
    op.create_table('sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.String(255), nullable=False, comment='video_id or unique identifier'),
        sa.Column('source_type', sa.String(50), nullable=False, comment='youtube, zoom, local, etc.'),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('channel_name', sa.String(255), nullable=True),
        sa.Column('channel_url', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('duration_s', sa.Integer(), nullable=True, comment='Duration in seconds'),
        sa.Column('view_count', sa.Integer(), nullable=True),
        sa.Column('like_count', sa.Integer(), nullable=True),
        sa.Column('comment_count', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.JSONB(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True, comment='Processing metadata, model info, etc.'),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending', comment='pending, processing, completed, failed'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_updated', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_type', 'source_id', name='unique_source')
    )
    
    # Create segments table (transcript segments with speaker attribution)
    op.create_table('segments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.String(255), nullable=False, comment='References source_id in sources table'),
        sa.Column('start_sec', sa.Float(), nullable=False),
        sa.Column('end_sec', sa.Float(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('speaker_label', sa.String(50), nullable=True, comment='Chaffee, GUEST, or NULL'),
        sa.Column('speaker_confidence', sa.Float(), nullable=True, comment='Voice verification confidence [0-1]'),
        sa.Column('embedding', postgresql.ARRAY(sa.Float(), dimensions=1), nullable=True, comment='1536-dim vector for semantic search'),
        sa.Column('avg_logprob', sa.Float(), nullable=True, comment='Whisper confidence metric'),
        sa.Column('compression_ratio', sa.Float(), nullable=True, comment='Whisper quality metric'),
        sa.Column('no_speech_prob', sa.Float(), nullable=True, comment='Probability of no speech'),
        sa.Column('temperature_used', sa.Float(), nullable=True, comment='Whisper temperature parameter'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True, comment='Additional segment metadata'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create api_cache table for YouTube Data API caching
    op.create_table('api_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cache_key', sa.String(255), nullable=False),
        sa.Column('etag', sa.String(255), nullable=True),
        sa.Column('data', postgresql.JSONB(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cache_key')
    )
    
    # Create indexes for performance
    op.create_index('idx_segments_video_id', 'segments', ['video_id'])
    op.create_index('idx_segments_speaker', 'segments', ['speaker_label'])
    op.create_index('idx_segments_time', 'segments', ['video_id', 'start_sec'])
    op.create_index('idx_sources_lookup', 'sources', ['source_type', 'source_id'])
    op.create_index('idx_sources_status', 'sources', ['status'])
    op.create_index('idx_sources_updated', 'sources', ['last_updated'])
    
    # Create pgvector index for semantic search
    # Note: This requires data to be present for optimal performance
    # Lists parameter tuned for expected dataset size (~100k segments)
    op.execute("""
        CREATE INDEX segments_embedding_idx 
        ON segments USING ivfflat (embedding vector_l2_ops) 
        WITH (lists = 100)
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('api_cache')
    op.drop_table('segments')
    op.drop_table('sources')
    
    # Drop pgvector extension
    op.execute('DROP EXTENSION IF EXISTS vector CASCADE')
