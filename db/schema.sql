-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Sources table to track videos/recordings
CREATE TABLE IF NOT EXISTS sources (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('youtube', 'zoom')),
    source_id VARCHAR(255) NOT NULL, -- YouTube video ID or Zoom recording ID
    title TEXT NOT NULL,
    description TEXT,
    duration_seconds INTEGER,
    published_at TIMESTAMP,
    url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(source_type, source_id)
);

-- Chunks table for transcript segments with embeddings
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL, -- Order within the source
    start_time_seconds REAL NOT NULL,
    end_time_seconds REAL NOT NULL,
    text TEXT NOT NULL,
    embedding vector(384), -- all-MiniLM-L6-v2 produces 384-dim vectors
    word_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(source_id, chunk_index)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sources_type_published ON sources(source_type, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_sources_created_at ON sources(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chunks_source_id ON chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_start_time ON chunks(start_time_seconds);

-- pgvector index for similarity search
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for sources updated_at
CREATE OR REPLACE TRIGGER update_sources_updated_at
    BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Example query for semantic search
-- SELECT 
--     s.title, s.url, c.text, c.start_time_seconds, c.end_time_seconds,
--     (c.embedding <=> %s::vector) as similarity
-- FROM chunks c
-- JOIN sources s ON c.source_id = s.id
-- ORDER BY c.embedding <=> %s::vector
-- LIMIT 20;
