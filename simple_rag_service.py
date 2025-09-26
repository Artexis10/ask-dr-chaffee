#!/usr/bin/env python3
"""
Simplified RAG Service for Ask Dr. Chaffee MVP
Provides search functionality for the frontend
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
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

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DATABASE_URL = os.getenv('DATABASE_URL')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('SUMMARIZER_MODEL', 'gpt-3.5-turbo')
SEARCH_LIMIT = int(os.getenv('ANSWER_TOPK', '20'))

# Initialize OpenAI
if OPENAI_API_KEY and not OPENAI_API_KEY.startswith('your_'):
    openai.api_key = OPENAI_API_KEY
    AI_ENABLED = True
else:
    AI_ENABLED = False
    logger.warning("OpenAI API key not configured - using mock responses")

# FastAPI app
app = FastAPI(
    title="Ask Dr. Chaffee RAG Service",
    description="Simplified RAG service for MVP",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class SearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 20

class SearchResult(BaseModel):
    video_id: str
    title: str
    text: str
    timestamp: str
    similarity: float
    start_time_seconds: int

class RAGResponse(BaseModel):
    question: str
    answer: str
    sources: List[SearchResult]
    cost_usd: float
    timestamp: int

def get_db_connection():
    """Get database connection"""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

def search_chunks(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search for relevant chunks in the database"""
    conn = get_db_connection()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Simple text search for now (can be enhanced with vector search later)
            search_sql = """
            SELECT 
                c.id,
                c.text,
                c.start_time_seconds,
                s.source_id as video_id,
                s.title,
                s.published_at
            FROM chunks c
            JOIN sources s ON c.source_id = s.id
            WHERE c.text ILIKE %s
            AND s.source_type = 'youtube'
            ORDER BY 
                CASE 
                    WHEN c.text ILIKE %s THEN 1
                    WHEN c.text ILIKE %s THEN 2
                    ELSE 3 
                END,
                s.published_at DESC
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

def generate_answer(query: str, context_chunks: List[Dict[str, Any]]) -> str:
    """Generate AI answer using OpenAI"""
    if not AI_ENABLED:
        # Mock response for development
        return f"This is a mock answer for: '{query}'. Dr. Chaffee would say this is important for your health."
    
    try:
        # Prepare context
        context_text = "\n\n".join([
            f"[{chunk['title']} - {chunk['start_time_seconds']}s]: {chunk['text']}"
            for chunk in context_chunks[:10]  # Limit context size
        ])
        
        # Create prompt
        prompt = f"""You are Dr. Anthony Chaffee, a carnivore diet advocate and medical doctor. Based on the following context from your videos, please answer the user's question in your characteristic style - direct, evidence-based, and focused on optimal human health.

Context:
{context_text}

Question: {query}

Please provide a comprehensive answer based on the context provided. If the context doesn't contain enough information, say so clearly."""

        # Call OpenAI
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are Dr. Anthony Chaffee, answering questions based on provided video transcripts."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.3
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        logger.error(f"AI answer generation failed: {e}")
        return f"I found relevant information about '{query}' in my videos, but I'm having trouble generating a detailed response right now. Please check the sources below for the specific information."

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Ask Dr. Chaffee RAG",
        "ai_enabled": AI_ENABLED,
        "database": "connected" if DATABASE_URL else "not configured"
    }

@app.post("/search", response_model=RAGResponse)
async def search_and_answer(request: SearchRequest):
    """Main RAG endpoint - search and generate answer"""
    try:
        logger.info(f"Processing query: {request.query}")
        
        # Search for relevant chunks
        chunks = search_chunks(request.query, request.max_results)
        
        if not chunks:
            raise HTTPException(
                status_code=404, 
                detail="No relevant content found for your query"
            )
        
        # Generate AI answer
        answer = generate_answer(request.query, chunks)
        
        # Format sources
        sources = []
        for chunk in chunks:
            # Convert seconds to timestamp format
            minutes = chunk['start_time_seconds'] // 60
            seconds = chunk['start_time_seconds'] % 60
            timestamp = f"{minutes}:{seconds:02d}"
            
            source = SearchResult(
                video_id=chunk['video_id'],
                title=chunk['title'],
                text=chunk['text'][:300] + "..." if len(chunk['text']) > 300 else chunk['text'],
                timestamp=timestamp,
                similarity=0.85,  # Mock similarity for now
                start_time_seconds=chunk['start_time_seconds']
            )
            sources.append(source)
        
        response = RAGResponse(
            question=request.query,
            answer=answer,
            sources=sources,
            cost_usd=0.01 if AI_ENABLED else 0.0,  # Estimated cost
            timestamp=int(datetime.now().timestamp())
        )
        
        logger.info(f"Successfully processed query: {request.query}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query '{request.query}': {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/stats")
async def get_stats():
    """Get database statistics"""
    conn = get_db_connection()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get total chunks and sources
            cur.execute("SELECT COUNT(*) as chunk_count FROM chunks")
            chunk_count = cur.fetchone()['chunk_count']
            
            cur.execute("SELECT COUNT(*) as source_count FROM sources WHERE source_type = 'youtube'")
            source_count = cur.fetchone()['source_count']
            
            return {
                "total_chunks": chunk_count,
                "total_sources": source_count,
                "ai_enabled": AI_ENABLED,
                "service_status": "operational"
            }
    finally:
        conn.close()

if __name__ == "__main__":
    logger.info("🚀 Starting Ask Dr. Chaffee RAG Service")
    logger.info(f"Database: {'✅ Connected' if DATABASE_URL else '❌ Not configured'}")
    logger.info(f"AI: {'✅ Enabled' if AI_ENABLED else '⚠️ Mock mode'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=5001,
        log_level="info"
    )
