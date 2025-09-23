import { NextApiRequest, NextApiResponse } from 'next';
import { Pool } from 'pg';
import crypto from 'crypto';

// Import our RAG functionality
type RAGResponse = {
  question: string;
  answer: string;
  citations: Array<{
    video_id: string;
    title: string;
    timestamp: string;
    similarity: number;
  }>;
  chunks_used: number;
  cost_usd: number;
  timestamp: number;
};

// Database connection
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
});

// Configuration
const ANSWER_ENABLED = process.env.ANSWER_ENABLED !== 'false'; // Default to enabled
const ANSWER_TOPK = parseInt(process.env.ANSWER_TOPK || '40');
const ANSWER_TTL_HOURS = parseInt(process.env.ANSWER_TTL_HOURS || '336'); // 14 days
const SUMMARIZER_MODEL = process.env.SUMMARIZER_MODEL || 'gpt-3.5-turbo';
const ANSWER_STYLE_DEFAULT = process.env.ANSWER_STYLE_DEFAULT || 'concise';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const USE_MOCK_MODE = !OPENAI_API_KEY || OPENAI_API_KEY.includes('your_') || process.env.USE_MOCK_MODE === 'true';

console.log('ANSWER_ENABLED:', ANSWER_ENABLED);
console.log('USE_MOCK_MODE:', USE_MOCK_MODE);

// RAG Service Integration
const RAG_SERVICE_URL = process.env.RAG_SERVICE_URL || 'http://localhost:5001';

async function callRAGService(question: string): Promise<RAGResponse | null> {
  try {
    // Create timeout promise
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout
    
    const response = await fetch(`${RAG_SERVICE_URL}/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: question }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      console.error('RAG service error:', response.status, response.statusText);
      return null;
    }

    const data = await response.json();
    
    // Transform RAG response to match our format
    return {
      question: data.question || question,
      answer: data.answer || '',
      citations: data.sources?.map((source: any) => ({
        video_id: source.video_id,
        title: source.title,
        timestamp: source.timestamp || '',
        similarity: source.similarity || 0
      })) || [],
      chunks_used: data.sources?.length || 0,
      cost_usd: data.cost_usd || 0,
      timestamp: Date.now()
    };
  } catch (error) {
    console.error('RAG service call failed:', error);
    return null;
  }
}

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
  // Since we don't have a JavaScript embedding service integrated yet,
  // we'll return an empty array to force fallback to text search
  console.log('Using text search fallback for answer generation');
  return [];
}

// Call LLM to generate answer
async function callSummarizer(query: string, excerpts: ChunkResult[], style: string): Promise<LLMResponse> {
  if (USE_MOCK_MODE) {
    throw new Error('OpenAI API key not configured');
  }

  console.log('Using OpenAI API for answer generation');
  
  const excerptText = excerpts.map((chunk, i) => 
    `- id: ${chunk.video_id}@${formatTimestamp(chunk.start_time_seconds)}\n  date: ${new Date(chunk.published_at).toISOString().split('T')[0]}\n  text: "${chunk.text}"`
  ).join('\n\n');

  // Enhanced word limits for long-form synthesis
  const targetWords = style === 'detailed' ? '600–1200' : '300–600';
  const maxTokens = style === 'detailed' ? 2500 : 1500;
  
  const systemPrompt = `You are compiling a long-form synthesis of Dr. Anthony Chaffee's views. Ground EVERYTHING strictly in the provided transcript excerpts. Do NOT use outside knowledge or speculation. Write a cohesive, well-structured markdown answer that synthesizes across clips. Use ## section headers for organization. Cite with inline timestamps like [video_id@mm:ss] at the END of sentences/clauses they support. Prefer newer material when consolidating conflicting statements. If views evolved, state the nuance and cite both. Tone: neutral narrator summarizing Chaffee's position; do not speak as him.`;
  
  const userPrompt = `You are compiling a long-form synthesis of Dr. Anthony Chaffee's views.

Query: "${query}"

Context Excerpts (use only these):
${excerptText}

Instructions:
- Ground EVERYTHING strictly in the provided transcript excerpts. Do NOT use outside knowledge or speculation.
- Write a cohesive, well-structured markdown answer (use ## section headers) that synthesizes across clips.
- Length target: ${targetWords} words (ok to be shorter if context is thin).
- Use inline timestamp citations like [video_id@mm:ss] at the END of the sentences/clauses they support.
- Cite whenever a claim depends on a specific excerpt; don't over-cite trivial transitions.
- Prefer newer material when consolidating conflicting statements; if views evolved, state the nuance and cite both.
- If a point is unclear or missing in the excerpts, say so briefly (e.g., "not addressed in provided excerpts").
- Tone: neutral narrator summarizing Chaffee's position; do not speak as him.

Output MUST be valid JSON with this schema:
{
  "answer": "Markdown with sections and inline citations like [abc123@12:34]. ${targetWords} words if context supports it.",
  "citations": [
    { "video_id": "abc123", "timestamp": "12:34", "date": "2024-06-18" }
  ],
  "confidence": 0.0,
  "notes": "Optional brief notes: conflicts seen, gaps, or scope limits."
}

Validation requirements:
- Every [video_id@mm:ss] that appears in answer MUST also appear once in citations[].
- Every citation MUST correspond to an excerpt listed above (exact match or within ±5s).
- Do NOT include citations to sources not present in the excerpts.
- Keep formatting clean: no stray backslashes, no code fences in answer, no HTML.
- If context is too sparse (<8 useful excerpts), create a short answer and explain the limitation in notes.`;

  try {
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
        max_tokens: maxTokens,
      }),
    });

    if (!response.ok) {
      console.error('OpenAI API error:', response.status, response.statusText);
      throw new Error(`OpenAI API failed: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    const content = data.choices[0]?.message?.content;
    
    if (!content) {
      throw new Error('Empty response from OpenAI API');
    }

    try {
      const parsed = JSON.parse(content);
      console.log('Successfully generated long-form synthesis using OpenAI API');
      return parsed;
    } catch (parseError) {
      console.error('Failed to parse OpenAI response as JSON:', content);
      throw new Error('Invalid JSON response from OpenAI API');
    }
  } catch (error) {
    console.error('OpenAI API call failed:', error);
    throw error;
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
  
  // Check if database connection string is configured
  if (!process.env.DATABASE_URL) {
    return res.status(503).json({
      error: 'Database configuration missing',
      message: 'The database connection string is not configured. Please check your environment variables.',
      code: 'DB_CONFIG_MISSING'
    });
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
    console.log('Processing query:', query);

    // Try RAG service first (preferred method)
    const ragResult = await callRAGService(query);
    
    if (ragResult && ragResult.answer) {
      console.log('Using RAG service response');
      
      // Transform RAG response to match frontend expectations
      const citations = ragResult.citations.map(citation => ({
        video_id: citation.video_id,
        t_start_s: timestampToSeconds(citation.timestamp.replace(/[\[\]]/g, '')), // Remove brackets and parse
        published_at: new Date().toISOString() // RAG doesn't provide published_at, use current time
      }));
      
      return res.status(200).json({
        answer_md: ragResult.answer,
        citations: citations,
        confidence: ragResult.chunks_used >= 5 ? 0.9 : 0.7, // High confidence if many sources
        notes: `Generated using RAG service with ${ragResult.chunks_used} source chunks. Cost: $${ragResult.cost_usd.toFixed(4)}`,
        used_chunk_ids: [], // RAG service doesn't provide chunk IDs
        rag_enabled: true,
        processing_cost: ragResult.cost_usd
      });
    }
    
    // Fallback to original method if RAG service fails
    console.log('RAG service unavailable, falling back to original method');

    if (USE_MOCK_MODE) {
      return res.status(503).json({
        error: 'Answer generation unavailable',
        message: 'OpenAI API key not configured. Please configure OPENAI_API_KEY environment variable.',
        code: 'API_KEY_MISSING'
      });
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
      // Fallback to simple text search for reliability
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
          COALESCE(s.provenance, 'yt_caption') = 'owner' DESC,
          s.published_at DESC,
          c.start_time_seconds ASC
        LIMIT $2
      `;
      queryParams = [`%${query}%`, maxContext];
    }

    const searchResult = await pool.query(searchQuery, queryParams);
    let chunks: ChunkResult[] = searchResult.rows;
    
    if (chunks.length < 1) {
      return res.status(200).json({ 
        error: 'Insufficient content available',
        message: `Only found ${chunks.length} relevant clips. Need at least 1 clip to generate an answer.`,
        available_chunks: chunks.length,
        code: 'INSUFFICIENT_CONTENT'
      });
    }

    // Apply clustering and ranking
    chunks = chunks.map(chunk => ({
      ...chunk,
      similarity: Math.abs(chunk.similarity)
    }));

    chunks = chunks.map(chunk => {
      let boost = 1.0;
      const publishedDate = new Date(chunk.published_at);
      const now = new Date();
      const yearsDiff = (now.getTime() - publishedDate.getTime()) / (1000 * 60 * 60 * 24 * 365);
      if (yearsDiff <= 1) boost += 0.1;
      else if (yearsDiff <= 2) boost += 0.05;
      if (chunk.source_type === 'youtube') boost += 0.05;
      
      return {
        ...chunk,
        similarity: Math.min(1.0, chunk.similarity * boost)
      };
    });

    chunks.sort((a, b) => b.similarity - a.similarity);
    const clusteredChunks = clusterChunks(chunks.slice(0, maxContext));
    
    if (clusteredChunks.length === 0) {
      return res.status(200).json({ 
        error: 'No relevant content found',
        message: 'Could not find any relevant content after processing and clustering.',
        code: 'NO_RELEVANT_CONTENT'
      });
    }

    // Generate and validate answer
    const llmResponse = await callSummarizer(query, clusteredChunks, style);
    const validatedResponse = validateAndProcessResponse(llmResponse, clusteredChunks);

    // Cache the result (implement caching logic here when ready)
    
    // Return response with source clips
    res.status(200).json({
      ...validatedResponse,
      source_clips: clusteredChunks,
      cached: false,
      total_chunks_considered: chunks.length,
      chunks_after_clustering: clusteredChunks.length,
    });

  } catch (error) {
    console.error('Answer generation error:', error);
    
    if (error instanceof Error) {
      // Rate limit errors
      if (error.message.includes('429')) {
        return res.status(429).json({
          error: 'Rate limit exceeded',
          message: 'OpenAI API rate limit reached. Please try again in a few moments.',
          code: 'RATE_LIMIT_EXCEEDED'
        });
      }
      
      // Authentication errors
      if (error.message.includes('401')) {
        return res.status(401).json({
          error: 'API authentication failed',
          message: 'OpenAI API key is invalid or expired.',
          code: 'INVALID_API_KEY'
        });
      }
      
      // Database connection errors
      if (error.message.includes('connect') || 
          error.message.includes('ECONNREFUSED') || 
          error.message.includes('database') ||
          error.message.includes('Connection') ||
          error.message.includes('pool')) {
        return res.status(503).json({
          error: 'Database connection failed',
          message: 'Unable to connect to the database. The service may be temporarily unavailable.',
          code: 'DB_CONNECTION_ERROR'
        });
      }
    }
    
    // Generic error handler
    res.status(500).json({ 
      error: 'Answer generation failed',
      message: error instanceof Error ? error.message : 'An unexpected error occurred.',
      code: 'GENERATION_FAILED'
    });
  }
}
