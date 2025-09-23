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
  similarity: string; // Now a percentage string like "56.7"
  source_type: string;
  published_at?: string;
  rerank_score?: number;
}

interface SearchParams {
  query: string;
  source_filter?: 'all' | 'youtube' | 'zoom';
  year_filter?: string;
  limit?: number;
}

interface ClusteredResult {
  id: number;
  title: string;
  url: string;
  source_type: string;
  published_at?: string;
  segments: SearchResult[];
}

// Cluster segments within ±120 seconds of each other
function clusterSegments(results: SearchResult[]): SearchResult[] {
  if (results.length === 0) return results;
  
  const grouped: { [key: string]: SearchResult[] } = {};
  
  // Group by source URL (without timestamp)
  results.forEach(result => {
    const baseUrl = result.url.split('&t=')[0];
    if (!grouped[baseUrl]) {
      grouped[baseUrl] = [];
    }
    grouped[baseUrl].push(result);
  });
  
  const clustered: SearchResult[] = [];
  
  Object.values(grouped).forEach(sourceResults => {
    sourceResults.sort((a, b) => a.start_time_seconds - b.start_time_seconds);
    
    let currentCluster: SearchResult[] = [];
    
    sourceResults.forEach(result => {
      if (currentCluster.length === 0) {
        currentCluster.push(result);
      } else {
        const lastResult = currentCluster[currentCluster.length - 1];
        const timeDiff = Math.abs(result.start_time_seconds - lastResult.end_time_seconds);
        
        if (timeDiff <= 120) { // Within 120 seconds
          currentCluster.push(result);
        } else {
          // Finalize current cluster
          if (currentCluster.length > 1) {
            // Create merged segment
            const firstSegment = currentCluster[0];
            const lastSegment = currentCluster[currentCluster.length - 1];
            
            clustered.push({
              ...firstSegment,
              text: currentCluster.map(s => s.text).join(' ... '),
              end_time_seconds: lastSegment.end_time_seconds,
              similarity: Math.max(...currentCluster.map(s => parseFloat(s.similarity))).toFixed(1)
            });
          } else {
            clustered.push(currentCluster[0]);
          }
          
          // Start new cluster
          currentCluster = [result];
        }
      }
    });
    
    // Handle final cluster
    if (currentCluster.length > 1) {
      const firstSegment = currentCluster[0];
      const lastSegment = currentCluster[currentCluster.length - 1];
      
      clustered.push({
        ...firstSegment,
        text: currentCluster.map(s => s.text).join(' ... '),
        end_time_seconds: lastSegment.end_time_seconds,
        similarity: Math.max(...currentCluster.map(s => parseFloat(s.similarity))).toFixed(1)
      });
    } else if (currentCluster.length === 1) {
      clustered.push(currentCluster[0]);
    }
  });
  
  return clustered;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'POST' && req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // Handle both GET and POST requests
  const params = req.method === 'POST' ? req.body : req.query;
  const query = params.q || params.query;
  const source_filter = params.source_filter || 'all';
  const year_filter = params.year_filter;
  const limit = parseInt(params.limit as string) || 30;

  if (!query || typeof query !== 'string' || query.trim().length === 0) {
    return res.status(400).json({ error: 'Query is required' });
  }

  try {
    // Build dynamic WHERE clause for filters
    let whereConditions = ['(c.text ILIKE $1 OR s.title ILIKE $1)'];
    let queryParams: any[] = [`%${query}%`];
    let paramCount = 1;

    // Source filter
    if (source_filter !== 'all') {
      paramCount++;
      whereConditions.push(`s.source_type = $${paramCount}`);
      queryParams.push(source_filter);
    }

    // Year filter
    if (year_filter) {
      paramCount++;
      whereConditions.push(`EXTRACT(YEAR FROM s.published_at) = $${paramCount}`);
      queryParams.push(parseInt(year_filter));
    }

    const searchQuery = `
      SELECT 
        c.id,
        s.title,
        c.text,
        s.url,
        c.start_time_seconds,
        c.end_time_seconds,
        s.source_type,
        s.published_at,
        COALESCE(s.provenance, 'yt_caption') as provenance,
        0.5 as similarity -- Initial similarity score
      FROM chunks c
      JOIN sources s ON c.source_id = s.id
      WHERE ${whereConditions.join(' AND ')}
      ORDER BY 
        -- Primary: Text relevance
        CASE 
          WHEN c.text ILIKE $1 THEN 1
          WHEN s.title ILIKE $1 THEN 2
          ELSE 3
        END,
        -- Secondary: Provenance preference (owner > yt_caption > yt_dlp > whisper)
        CASE COALESCE(s.provenance, 'yt_caption') 
          WHEN 'owner' THEN 1
          WHEN 'yt_caption' THEN 2
          WHEN 'yt_dlp' THEN 3
          WHEN 'whisper' THEN 4
          ELSE 5
        END,
        -- Tertiary: Recency boost for recent content
        s.published_at DESC NULLS LAST,
        -- Final: Temporal order within content
        c.start_time_seconds ASC
      LIMIT $${paramCount + 1}
    `;

    queryParams.push(limit);
    const result = await pool.query(searchQuery, queryParams);

    // Process initial results
    let searchResults = result.rows.map(row => {
      let urlWithTimestamp = row.url;
      if (row.source_type === 'youtube' && row.start_time_seconds) {
        const timestampSeconds = Math.floor(row.start_time_seconds);
        urlWithTimestamp = `${row.url}&t=${timestampSeconds}s`;
      }
      return {
        id: row.id,
        title: row.title,
        text: row.text,
        url: urlWithTimestamp,
        start_time_seconds: row.start_time_seconds,
        end_time_seconds: row.end_time_seconds,
        similarity: Math.abs(row.similarity * 100).toFixed(1),
        source_type: row.source_type,
        published_at: row.published_at,
      };
    });

    // Apply reranking if enabled (placeholder for now - will implement with Python service)
    const isRerankEnabled = process.env.RERANK_ENABLED === 'true';
    if (isRerankEnabled && searchResults.length > 5) {
      // TODO: Call Python reranker service
      // For now, just take top 5
      searchResults = searchResults.slice(0, 5);
    }

    // Cluster segments within ±120s
    const clusteredResults = clusterSegments(searchResults);

    res.status(200).json({ 
      results: clusteredResults, 
      total: clusteredResults.length, 
      query: query.trim(),
      filters: {
        source_filter,
        year_filter
      }
    });

  } catch (error) {
    console.error('Search error:', error);
    
    // Handle different types of errors
    if (error instanceof Error) {
      // Database connection errors
      if (error.message.includes('connect') || 
          error.message.includes('ECONNREFUSED') || 
          error.message.includes('database') ||
          error.message.includes('Connection') ||
          error.message.includes('pool')) {
        return res.status(503).json({
          error: 'Database service unavailable',
          message: 'The database service is currently unavailable. Please try again later.',
          code: 'SERVICE_UNAVAILABLE'
        });
      }
      
      // Generic error with message
      res.status(500).json({ 
        error: 'Search service error',
        message: `The search service encountered an error: ${error.message}`,
        code: 'SEARCH_ERROR'
      });
    } else {
      // Unknown error type
      res.status(500).json({ 
        error: 'Search service error',
        message: 'The search service encountered an unknown error.',
        code: 'UNKNOWN_ERROR'
      });
    }
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
