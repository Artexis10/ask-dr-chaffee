import { NextApiRequest, NextApiResponse } from 'next';
import { Pool } from 'pg';
import crypto from 'crypto';

// Database connection
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
});

// Configuration
const ANSWER_ENABLED = process.env.ANSWER_ENABLED === 'true';
const ANSWER_TOPK = parseInt(process.env.ANSWER_TOPK || '40');
const ANSWER_TTL_HOURS = parseInt(process.env.ANSWER_TTL_HOURS || '336'); // 14 days
const SUMMARIZER_MODEL = process.env.SUMMARIZER_MODEL || 'gpt-3.5-turbo';
const ANSWER_STYLE_DEFAULT = process.env.ANSWER_STYLE_DEFAULT || 'concise';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;

interface AnswerParams {
  q: string;
  max_context?: number;
  max_bullets?: number;
  style?: 'concise' | 'detailed';
  refresh?: boolean;
}

interface ChunkResult {
  id: number;
  source_id: number;
  video_id: string;
  title: string;
  text: string;
  start_time_seconds: number;
  end_time_seconds: number;
  published_at: string;
  source_type: string;
  similarity: number;
}

interface Citation {
  video_id: string;
  t_start_s: number;
  published_at: string;
}

interface AnswerResponse {
  answer_md: string;
  citations: Citation[];
  confidence: number;
  notes?: string;
  used_chunk_ids: string[];
}

interface LLMResponse {
  answer: string;
  citations: Array<{
    video_id: string;
    timestamp: string;
    date: string;
  }>;
  confidence: number;
  notes?: string;
}

// Utility functions
function normalizeQuery(query: string): string {
  return query.toLowerCase().trim().replace(/\s+/g, ' ');
}

function generateCacheKey(queryNorm: string, chunkIds: string[], modelVersion: string): string {
  const content = queryNorm + chunkIds.sort().join(',') + modelVersion;
  return crypto.createHash('sha256').update(content).digest('hex');
}

function formatTimestamp(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function timestampToSeconds(timestamp: string): number {
  const [minutes, seconds] = timestamp.split(':').map(Number);
  return minutes * 60 + seconds;
}

// Cluster chunks within ±90-120s window to reduce redundancy
function clusterChunks(chunks: ChunkResult[]): ChunkResult[] {
  if (chunks.length === 0) return chunks;
  
  const grouped: { [key: string]: ChunkResult[] } = {};
  
  // Group by video_id
  chunks.forEach(chunk => {
    if (!grouped[chunk.video_id]) {
      grouped[chunk.video_id] = [];
    }
    grouped[chunk.video_id].push(chunk);
  });
  
  const clustered: ChunkResult[] = [];
  
  Object.values(grouped).forEach(videoChunks => {
    videoChunks.sort((a, b) => a.start_time_seconds - b.start_time_seconds);
    
    let currentCluster: ChunkResult[] = [];
    
    videoChunks.forEach(chunk => {
      if (currentCluster.length === 0) {
        currentCluster.push(chunk);
      } else {
        const lastChunk = currentCluster[currentCluster.length - 1];
        const timeDiff = Math.abs(chunk.start_time_seconds - lastChunk.end_time_seconds);
        
        if (timeDiff <= 120) { // Within 120 seconds
          currentCluster.push(chunk);
        } else {
          // Finalize current cluster - select best chunk
          const bestChunk = currentCluster.reduce((best, current) => 
            current.similarity > best.similarity ? current : best
          );
          clustered.push(bestChunk);
          
          // Start new cluster
          currentCluster = [chunk];
        }
      }
    });
    
    // Handle final cluster
    if (currentCluster.length > 0) {
      const bestChunk = currentCluster.reduce((best, current) => 
        current.similarity > best.similarity ? current : best
      );
      clustered.push(bestChunk);
    }
  });
  
  return clustered;
}

// Generate embeddings for the query
async function generateQueryEmbedding(query: string): Promise<number[]> {
  // This would typically call your embedding service
  // For now, return a placeholder - you'll need to implement this based on your embedding model
  // This should match how you generate embeddings in your ingestion pipeline
  
  try {
    // You might call a Python service here or use a JavaScript embedding library
    // For now, returning null to indicate we need semantic search implementation
    return [];
  } catch (error) {
    console.error('Failed to generate embedding:', error);
    return [];
  }
}

// Call LLM to generate answer
async function callSummarizer(query: string, excerpts: ChunkResult[], style: string): Promise<LLMResponse> {
  if (!OPENAI_API_KEY) {
    throw new Error('OpenAI API key not configured');
  }

  const excerptText = excerpts.map((chunk, i) => 
    `- id: ${chunk.video_id}@${formatTimestamp(chunk.start_time_seconds)}\n  date: ${chunk.published_at.split('T')[0]}\n  text: "${chunk.text}"`
  ).join('\n\n');

  const maxWords = style === 'detailed' ? 320 : 180;
  
  const systemPrompt = `You are compiling Dr. Anthony Chaffee's on-record answer using ONLY the provided excerpts. Do not invent facts or rely on outside knowledge. If excerpts conflict, acknowledge the conflict. Prefer newer material when summarizing. Every sentence must cite ≥1 excerpt as [video_id@mm:ss]. Output strictly as JSON matching the schema.`;
  
  const userPrompt = `Query: "${query}"

Excerpts:
${excerptText}

Output JSON schema:
{
  "answer": "2–5 sentences of clear prose with inline citations like [yt123@12:15]. Keep under ${maxWords} words (${style}).",
  "citations": [
    { "video_id": "yt123", "timestamp": "12:15", "date": "2024-06-10" }
  ],
  "confidence": 0.0-1.0,
  "notes": "optional: conflicts, missing info, scope limits"
}`;

  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${OPENAI_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: SUMMARIZER_MODEL,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt }
      ],
      temperature: 0.1,
      max_tokens: 1000,
      timeout: 8000, // 8 second timeout
    }),
  });

  if (!response.ok) {
    throw new Error(`LLM API failed: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  const content = data.choices[0]?.message?.content;
  
  if (!content) {
    throw new Error('Empty response from LLM');
  }

  try {
    return JSON.parse(content);
  } catch (error) {
    throw new Error('Invalid JSON response from LLM');
  }
}

// Validate citations and compute confidence
function validateAndProcessResponse(llmResponse: LLMResponse, chunks: ChunkResult[]): AnswerResponse {
  const chunkMap = new Map<string, ChunkResult>();
  chunks.forEach(chunk => {
    const key = `${chunk.video_id}@${formatTimestamp(chunk.start_time_seconds)}`;
    chunkMap.set(key, chunk);
  });

  // Validate citations
  const validCitations: Citation[] = [];
  const usedChunkIds: string[] = [];
  
  llmResponse.citations.forEach(citation => {
    const key = `${citation.video_id}@${citation.timestamp}`;
    const chunk = chunkMap.get(key);
    
    if (chunk) {
      validCitations.push({
        video_id: citation.video_id,
        t_start_s: chunk.start_time_seconds,
        published_at: citation.date,
      });
      usedChunkIds.push(`${chunk.video_id}:${chunk.start_time_seconds}`);
    }
  });

  // Compute confidence heuristic
  let confidence = llmResponse.confidence;
  
  // Adjust based on citation coverage
  const citationCoverage = validCitations.length / llmResponse.citations.length;
  confidence *= citationCoverage;
  
  // Adjust based on chunk quality (average similarity)
  const avgSimilarity = chunks.reduce((sum, chunk) => sum + chunk.similarity, 0) / chunks.length;
  confidence *= Math.min(1.0, avgSimilarity * 2); // Scale similarity to confidence
  
  // Adjust based on recency (boost for newer content within last 2 years)
  const now = new Date();
  const recentBonus = chunks.some(chunk => {
    const publishedDate = new Date(chunk.published_at);
    const yearsDiff = (now.getTime() - publishedDate.getTime()) / (1000 * 60 * 60 * 24 * 365);
    return yearsDiff <= 2;
  }) ? 1.1 : 1.0;
  
  confidence = Math.min(1.0, confidence * recentBonus);

  return {
    answer_md: llmResponse.answer,
    citations: validCitations,
    confidence: Math.round(confidence * 100) / 100,
    notes: llmResponse.notes,
    used_chunk_ids: usedChunkIds,
  };
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'POST' && req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  if (!ANSWER_ENABLED) {
    return res.status(503).json({ error: 'Answer endpoint is disabled' });
  }

  // Parse parameters
  const params = req.method === 'POST' ? req.body : req.query;
  const query = params.q || params.query;
  const maxContext = parseInt(params.max_context as string) || ANSWER_TOPK;
  const maxBullets = parseInt(params.max_bullets as string) || 6;
  const style = (params.style as string) || ANSWER_STYLE_DEFAULT;
  const refresh = params.refresh === '1' || params.refresh === 'true';

  if (!query || typeof query !== 'string' || query.trim().length === 0) {
    return res.status(400).json({ error: 'Query parameter "q" is required' });
  }

  if (!['concise', 'detailed'].includes(style)) {
    return res.status(400).json({ error: 'Style must be "concise" or "detailed"' });
  }

  try {
    const queryNorm = normalizeQuery(query);
    
    // Step 1: Check cache first (unless refresh requested)
    if (!refresh) {
      const cacheQuery = `
        SELECT answer_md, citations, confidence, notes, used_chunk_ids, created_at
        FROM summaries 
        WHERE cache_key = $1 AND type = 'answer' AND expires_at > NOW()
        ORDER BY created_at DESC 
        LIMIT 1
      `;
      
      // Generate a preliminary cache key for lookup (we'll update with actual chunks later)
      const preliminaryCacheKey = generateCacheKey(queryNorm, [], SUMMARIZER_MODEL);
      const cacheResult = await pool.query(cacheQuery, [preliminaryCacheKey]);
      
      if (cacheResult.rows.length > 0) {
        const cached = cacheResult.rows[0];
        return res.status(200).json({
          ...cached,
          cached: true,
          cache_date: cached.created_at,
        });
      }
    }

    // Step 2: Embed query and retrieve relevant chunks
    const queryEmbedding = await generateQueryEmbedding(query);
    
    let searchQuery: string;
    let queryParams: any[];
    
    if (queryEmbedding.length > 0) {
      // Semantic search with pgvector
      searchQuery = `
        SELECT 
          c.id,
          c.source_id,
          s.source_id as video_id,
          s.title,
          c.text,
          c.start_time_seconds,
          c.end_time_seconds,
          s.published_at,
          s.source_type,
          (c.embedding <=> $1::vector) as similarity
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> $1::vector
        LIMIT $2
      `;
      queryParams = [JSON.stringify(queryEmbedding), maxContext];
    } else {
      // Fallback to text search
      searchQuery = `
        SELECT 
          c.id,
          c.source_id,
          s.source_id as video_id,
          s.title,
          c.text,
          c.start_time_seconds,
          c.end_time_seconds,
          s.published_at,
          s.source_type,
          0.5 as similarity
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        WHERE c.text ILIKE $1
        ORDER BY 
          CASE WHEN c.text ILIKE $1 THEN 1 ELSE 2 END,
          s.published_at DESC,
          c.start_time_seconds ASC
        LIMIT $2
      `;
      queryParams = [`%${query}%`, maxContext];
    }

    const searchResult = await pool.query(searchQuery, queryParams);
    let chunks: ChunkResult[] = searchResult.rows;
    
    if (chunks.length < 8) {
      return res.status(200).json({ 
        error: 'Not enough on-record context yet',
        available_chunks: chunks.length,
        minimum_required: 8 
      });
    }

    // Step 3: Apply ranking preferences and cluster/dedupe
    chunks = chunks.map(chunk => ({
      ...chunk,
      similarity: Math.abs(chunk.similarity) // Ensure positive similarity scores
    }));

    // Boost newer content and better provenance
    chunks = chunks.map(chunk => {
      let boost = 1.0;
      
      // Recency boost (newer = better)
      const publishedDate = new Date(chunk.published_at);
      const now = new Date();
      const yearsDiff = (now.getTime() - publishedDate.getTime()) / (1000 * 60 * 60 * 24 * 365);
      if (yearsDiff <= 1) boost += 0.1;
      else if (yearsDiff <= 2) boost += 0.05;
      
      // Provenance boost (owner > yt_caption > whisper)
      if (chunk.source_type === 'youtube') boost += 0.05;
      
      return {
        ...chunk,
        similarity: Math.min(1.0, chunk.similarity * boost)
      };
    });

    // Sort by boosted similarity and cluster
    chunks.sort((a, b) => b.similarity - a.similarity);
    const clusteredChunks = clusterChunks(chunks.slice(0, maxContext));
    
    if (clusteredChunks.length === 0) {
      return res.status(200).json({ 
        error: 'No relevant content found after clustering' 
      });
    }

    // Step 4: Generate cache key with actual chunks
    const chunkIds = clusteredChunks.map(c => `${c.video_id}:${c.start_time_seconds}`);
    const cacheKey = generateCacheKey(queryNorm, chunkIds, SUMMARIZER_MODEL);
    
    // Check cache again with real cache key
    if (!refresh) {
      const cacheQuery = `
        SELECT answer_md, citations, confidence, notes, used_chunk_ids, created_at
        FROM summaries 
        WHERE cache_key = $1 AND type = 'answer' AND expires_at > NOW()
        ORDER BY created_at DESC 
        LIMIT 1
      `;
      
      const cacheResult = await pool.query(cacheQuery, [cacheKey]);
      
      if (cacheResult.rows.length > 0) {
        const cached = cacheResult.rows[0];
        return res.status(200).json({
          ...cached,
          cached: true,
          cache_date: cached.created_at,
        });
      }
    }

    // Step 5: Call LLM to generate answer
    const llmResponse = await callSummarizer(query, clusteredChunks, style);
    
    // Step 6: Validate and process response
    const validatedResponse = validateAndProcessResponse(llmResponse, clusteredChunks);
    
    // Step 7: Cache the result
    const expiresAt = new Date();
    expiresAt.setHours(expiresAt.getHours() + ANSWER_TTL_HOURS);
    
    const insertQuery = `
      INSERT INTO summaries (
        cache_key, type, query_text, chunk_ids, model_version,
        answer_md, citations, confidence, notes, used_chunk_ids, expires_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
      ON CONFLICT (cache_key) DO UPDATE SET
        answer_md = EXCLUDED.answer_md,
        citations = EXCLUDED.citations,
        confidence = EXCLUDED.confidence,
        notes = EXCLUDED.notes,
        used_chunk_ids = EXCLUDED.used_chunk_ids,
        expires_at = EXCLUDED.expires_at,
        updated_at = NOW()
    `;
    
    await pool.query(insertQuery, [
      cacheKey,
      'answer',
      query,
      chunkIds,
      SUMMARIZER_MODEL,
      validatedResponse.answer_md,
      JSON.stringify(validatedResponse.citations),
      validatedResponse.confidence,
      validatedResponse.notes,
      validatedResponse.used_chunk_ids,
      expiresAt
    ]);

    // Step 8: Return response
    res.status(200).json({
      ...validatedResponse,
      cached: false,
      total_chunks_considered: chunks.length,
      chunks_after_clustering: clusteredChunks.length,
    });

  } catch (error) {
    console.error('Answer generation error:', error);
    res.status(500).json({ 
      error: `Answer generation failed: ${error instanceof Error ? error.message : 'Unknown error'}`
    });
  }
}
