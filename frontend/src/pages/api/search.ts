import { NextApiRequest, NextApiResponse } from 'next';
import { Pool } from 'pg';

// Database connection
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
});

interface SearchResult {
  id: number;
  title: string;
  text: string;
  url: string;
  start_time_seconds: number;
  end_time_seconds: number;
  similarity: number;
  source_type: string;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'POST' && req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { query } = req.method === 'POST' ? req.body : req.query;

  if (!query || typeof query !== 'string' || query.trim().length === 0) {
    return res.status(400).json({ error: 'Query is required' });
  }

  try {
    // For now, we'll use a simple text search until embeddings are set up
    // In production, this should use vector similarity search with embeddings
    const searchQuery = `
      SELECT 
        c.id,
        s.title,
        c.text,
        s.url,
        c.start_time_seconds,
        c.end_time_seconds,
        s.source_type,
        0.5 as similarity -- Placeholder similarity score
      FROM chunks c
      JOIN sources s ON c.source_id = s.id
      WHERE 
        c.text ILIKE $1
        OR s.title ILIKE $1
        OR s.description ILIKE $1
      ORDER BY 
        CASE 
          WHEN c.text ILIKE $2 THEN 1
          WHEN s.title ILIKE $2 THEN 2
          ELSE 3
        END,
        c.start_time_seconds ASC
      LIMIT 20
    `;

    const searchParam = `%${query.trim()}%`;
    const exactParam = `%${query.trim()}%`;

    const result = await pool.query(searchQuery, [searchParam, exactParam]);
    
    const results: SearchResult[] = result.rows.map(row => ({
      id: row.id,
      title: row.title,
      text: row.text,
      url: row.url,
      start_time_seconds: row.start_time_seconds,
      end_time_seconds: row.end_time_seconds,
      similarity: row.similarity,
      source_type: row.source_type,
    }));

    res.status(200).json({ 
      results,
      total: results.length,
      query: query.trim()
    });

  } catch (error) {
    console.error('Search error:', error);
    res.status(500).json({ 
      error: 'Internal server error',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
}

// TODO: Implement semantic search with embeddings
// This would replace the text search above with:
// SELECT 
//   s.title, s.url, c.text, c.start_time_seconds, c.end_time_seconds,
//   (c.embedding <=> $1::vector) as similarity
// FROM chunks c
// JOIN sources s ON c.source_id = s.id
// ORDER BY c.embedding <=> $1::vector
// LIMIT 20
