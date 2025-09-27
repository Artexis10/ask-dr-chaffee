#!/usr/bin/env python3
"""
Enhanced RAG Service for Ask Dr. Chaffee MVP
Uses the new Emulated Dr. Chaffee prompt engineering system
"""

import os
import json
import logging
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# Web framework
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Database
import psycopg2
from psycopg2.extras import RealDictCursor

# AI/ML
import openai

# Import our new prompt loader
sys.path.append(str(Path(__file__).parent))
from shared.prompts.prompt_loader import ChaffeePromptLoader

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DATABASE_URL = os.getenv('DATABASE_URL')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('SUMMARIZER_MODEL', 'gpt-4-turbo-preview')  # Better model for structured output
SEARCH_LIMIT = int(os.getenv('ANSWER_TOPK', '20'))

# Initialize OpenAI
if OPENAI_API_KEY and not OPENAI_API_KEY.startswith('your_'):
    openai.api_key = OPENAI_API_KEY
    AI_ENABLED = True
else:
    AI_ENABLED = False
    logger.warning("OpenAI API key not configured - using mock responses")

# Initialize prompt loader
try:
    prompt_loader = ChaffeePromptLoader()
    logger.info("✅ Prompt loader initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to load prompts: {e}")
    prompt_loader = None

# FastAPI app
app = FastAPI(
    title="Ask Dr. Chaffee Enhanced RAG Service",
    description="Enhanced RAG service with Emulated Dr. Chaffee AI",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class EnhancedSearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 20
    answer_mode: Optional[str] = "expanded"  # concise, expanded, deep_dive
    include_primary_studies: Optional[bool] = False

class ChaffeeQuote(BaseModel):
    quote: str
    video_id: str
    timestamp: str
    context: Optional[str] = None

class EvidenceAssessment(BaseModel):
    chaffee_content_available: bool
    primary_studies_cited: int
    evidence_strength: str
    uncertainties: List[str]

class VideoClip(BaseModel):
    video_id: str
    title: str
    start_time: str
    duration: Optional[str] = None
    relevance_score: float

class EnhancedRAGResponse(BaseModel):
    role_label: str
    answer_mode: str
    summary_short: str
    summary_long: Optional[str] = None
    key_points: List[str]
    chaffee_quotes: List[ChaffeeQuote]
    evidence: EvidenceAssessment
    clips: List[VideoClip]
    disclaimers: List[str]
    # Metadata
    query: str
    cost_usd: float
    timestamp: int

def get_db_connection():
    """Get database connection"""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

def search_chaffee_chunks(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search for relevant chunks specifically attributed to Dr. Chaffee"""
    conn = get_db_connection()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Enhanced search that prioritizes Dr. Chaffee content
            search_sql = """
            SELECT DISTINCT
                c.id,
                c.text,
                c.start_time_seconds,
                c.speaker_metadata,
                s.source_id as video_id,
                s.title,
                s.published_at,
                s.metadata
            FROM chunks c
            JOIN sources s ON c.source_id = s.id
            WHERE c.text ILIKE %s
            AND s.source_type IN ('youtube', 'youtube_api')
            AND (
                c.speaker_metadata IS NULL OR
                c.speaker_metadata->>'primary_speaker' = 'Chaffee' OR
                c.speaker_metadata->>'chaffee_percentage' > '50'
            )
            ORDER BY 
                CASE 
                    WHEN c.text ILIKE %s THEN 1
                    WHEN c.text ILIKE %s THEN 2
                    WHEN c.speaker_metadata->>'chaffee_percentage' > '80' THEN 3
                    ELSE 4
                END,
                s.published_at DESC,
                c.start_time_seconds ASC
            LIMIT %s
            """
            
            search_term = f"%{query}%"
            exact_term = f"%{query.lower()}%"
            word_term = f"% {query.lower()} %"
            
            cur.execute(search_sql, (search_term, exact_term, word_term, limit))
            results = cur.fetchall()
            
            return [dict(row) for row in results]
    
    finally:
        conn.close()

def format_timestamp(seconds: int) -> str:
    """Convert seconds to MM:SS or HH:MM:SS format"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"

def generate_enhanced_answer(query: str, context_chunks: List[Dict[str, Any]], answer_mode: str = "expanded") -> Dict[str, Any]:
    """Generate enhanced AI answer using the new prompt system"""
    if not AI_ENABLED or not prompt_loader:
        # Enhanced mock response that follows the schema
        return {
            "role_label": "Emulated Dr. Anthony Chaffee (AI)",
            "answer_mode": answer_mode,
            "summary_short": f"Based on my content analysis, here's what I'd say about '{query}' - this is important for optimal human health.",
            "summary_long": "This is a comprehensive mock response. In production, this would contain detailed analysis based on Dr. Chaffee's actual content." if answer_mode != "concise" else None,
            "key_points": [
                "Mock key point based on carnivore diet principles",
                "Mock evidence-based recommendation",
                "Mock health optimization insight"
            ],
            "chaffee_quotes": [
                {
                    "quote": "Mock quote from Dr. Chaffee's content",
                    "video_id": "mock123",
                    "timestamp": "12:34"
                }
            ],
            "evidence": {
                "chaffee_content_available": len(context_chunks) > 0,
                "primary_studies_cited": 0,
                "evidence_strength": "limited",
                "uncertainties": ["This is a mock response for development"]
            },
            "clips": [],
            "disclaimers": [
                "This is an AI emulation, not medical advice",
                "Mock response for development purposes"
            ]
        }
    
    try:
        # Format context chunks for the prompt
        chaffee_snippets = []
        for chunk in context_chunks:
            snippet = {
                "text": chunk['text'][:500] + "..." if len(chunk['text']) > 500 else chunk['text'],
                "video_id": chunk['video_id'],
                "timestamp": format_timestamp(chunk['start_time_seconds']),
                "title": chunk['title']
            }
            chaffee_snippets.append(snippet)
        
        # Create the full prompt using our system
        messages = prompt_loader.create_full_prompt(
            user_input=query,
            chaffee_snippets=chaffee_snippets,
            answer_mode=answer_mode
        )
        
        # Call OpenAI with structured output
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=2000,
            temperature=0.2,
            response_format={"type": "json_object"}  # Force JSON output
        )
        
        # Parse and validate the response
        response_text = response.choices[0].message.content.strip()
        parsed_response = json.loads(response_text)
        
        # Validate required fields
        schema = prompt_loader.load_response_schema()
        required_fields = schema['required']
        
        for field in required_fields:
            if field not in parsed_response:
                logger.warning(f"Missing required field: {field}")
                # Add default values for missing fields
                if field == "role_label":
                    parsed_response[field] = "Emulated Dr. Anthony Chaffee (AI)"
                elif field == "disclaimers":
                    parsed_response[field] = ["This is an AI emulation, not medical advice"]
                # Add other defaults as needed
        
        return parsed_response
    
    except Exception as e:
        logger.error(f"Enhanced AI answer generation failed: {e}")
        # Fallback to mock response
        return generate_enhanced_answer(query, context_chunks, answer_mode)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Ask Dr. Chaffee Enhanced RAG",
        "version": "2.0.0",
        "ai_enabled": AI_ENABLED,
        "prompts_loaded": prompt_loader is not None,
        "database": "connected" if DATABASE_URL else "not configured"
    }

@app.post("/search", response_model=EnhancedRAGResponse)
async def enhanced_search_and_answer(request: EnhancedSearchRequest):
    """Enhanced RAG endpoint with structured Dr. Chaffee responses"""
    try:
        logger.info(f"Processing enhanced query: {request.query} (mode: {request.answer_mode})")
        
        # Validate answer mode
        if request.answer_mode not in ["concise", "expanded", "deep_dive"]:
            request.answer_mode = "expanded"
        
        # Search for relevant Chaffee chunks
        chunks = search_chaffee_chunks(request.query, request.max_results)
        
        if not chunks:
            raise HTTPException(
                status_code=404, 
                detail="No relevant Dr. Chaffee content found for your query"
            )
        
        # Generate enhanced AI answer
        ai_response = generate_enhanced_answer(request.query, chunks, request.answer_mode)
        
        # Create the response
        response = EnhancedRAGResponse(
            **ai_response,
            query=request.query,
            cost_usd=0.02 if AI_ENABLED else 0.0,  # Estimated cost for GPT-4
            timestamp=int(datetime.now().timestamp())
        )
        
        logger.info(f"Successfully processed enhanced query: {request.query}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing enhanced query '{request.query}': {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/prompts/info")
async def get_prompt_info():
    """Get information about the loaded prompts"""
    if not prompt_loader:
        raise HTTPException(status_code=500, detail="Prompts not loaded")
    
    try:
        schema = prompt_loader.load_response_schema()
        return {
            "system_prompt_loaded": True,
            "schema_version": schema.get("title", "Unknown"),
            "required_fields": schema.get("required", []),
            "answer_modes": ["concise", "expanded", "deep_dive"],
            "prompt_directory": str(prompt_loader.prompts_dir)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading prompt info: {e}")

@app.get("/stats")
async def get_enhanced_stats():
    """Get enhanced database statistics"""
    conn = get_db_connection()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get total chunks and sources
            cur.execute("SELECT COUNT(*) as chunk_count FROM chunks")
            chunk_count = cur.fetchone()['chunk_count']
            
            cur.execute("SELECT COUNT(*) as source_count FROM sources WHERE source_type IN ('youtube', 'youtube_api')")
            source_count = cur.fetchone()['source_count']
            
            # Get Chaffee-specific stats
            cur.execute("""
                SELECT COUNT(*) as chaffee_chunks 
                FROM chunks c 
                WHERE c.speaker_metadata->>'primary_speaker' = 'Chaffee' 
                OR c.speaker_metadata->>'chaffee_percentage' > '50'
            """)
            chaffee_chunks = cur.fetchone()['chaffee_chunks']
            
            return {
                "total_chunks": chunk_count,
                "chaffee_attributed_chunks": chaffee_chunks,
                "total_sources": source_count,
                "ai_enabled": AI_ENABLED,
                "prompts_loaded": prompt_loader is not None,
                "service_status": "operational",
                "version": "2.0.0"
            }
    finally:
        conn.close()

if __name__ == "__main__":
    logger.info("🚀 Starting Ask Dr. Chaffee Enhanced RAG Service v2.0")
    logger.info(f"Database: {'✅ Connected' if DATABASE_URL else '❌ Not configured'}")
    logger.info(f"AI: {'✅ Enabled' if AI_ENABLED else '⚠️ Mock mode'}")
    logger.info(f"Prompts: {'✅ Loaded' if prompt_loader else '❌ Failed to load'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=5002,  # Different port to avoid conflicts
        log_level="info"
    )
