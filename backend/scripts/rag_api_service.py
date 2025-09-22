#!/usr/bin/env python3
"""
RAG API Service for Frontend Search
Optimized for real-time question answering with Dr. Chaffee content
"""

import os
import sys
import logging
import time
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from flask import Flask, request, jsonify
from flask_cors import CORS

# Add parent directories to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from chaffee_domain_summarizer import ChaffeeDomainSummarizer, SummaryConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass 
class SearchResult:
    """Structured search result for frontend"""
    answer: str
    confidence: str  # "high", "medium", "low"
    sources: List[Dict[str, Any]]
    processing_time: float
    cost_usd: float
    
class RAGAPIService:
    """Flask API service for RAG-based search"""
    
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for frontend
        
        # Initialize summarizer
        config = SummaryConfig(
            openai_api_key=os.getenv('OPENAI_API_KEY'),
            model="gpt-4-turbo",
            temperature=0.1,  # Low for medical accuracy
            medical_accuracy_mode=True
        )
        
        self.summarizer = ChaffeeDomainSummarizer(config)
        self.setup_routes()
        
        # Cache for common queries (optional optimization)
        self.query_cache = {}
        self.cache_expiry = 3600  # 1 hour
    
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            return jsonify({"status": "healthy", "service": "rag-api"})
        
        @self.app.route('/search', methods=['POST'])
        def search_endpoint():
            return self.handle_search()
        
        @self.app.route('/search', methods=['GET'])
        def search_get_endpoint():
            # Support GET requests with query parameter
            query = request.args.get('q', '').strip()
            if not query:
                return jsonify({"error": "Query parameter 'q' is required"}), 400
            
            return self.handle_search(query)
    
    def handle_search(self, query: str = None) -> Dict[str, Any]:
        """Handle search requests from frontend"""
        start_time = time.time()
        
        try:
            # Get query from request body or parameter
            if query is None:
                data = request.get_json()
                if not data or 'query' not in data:
                    return jsonify({"error": "Query is required"}), 400
                query = data['query'].strip()
            
            if not query:
                return jsonify({"error": "Query cannot be empty"}), 400
            
            if len(query) < 3:
                return jsonify({"error": "Query must be at least 3 characters"}), 400
            
            logger.info(f"🔍 Frontend search: {query}")
            
            # Check cache first (optional optimization)
            cache_key = query.lower()
            if cache_key in self.query_cache:
                cached_result = self.query_cache[cache_key]
                if time.time() - cached_result['timestamp'] < self.cache_expiry:
                    logger.info(f"📋 Cache hit for: {query}")
                    cached_result['cached'] = True
                    return jsonify(cached_result)
            
            # Perform RAG search
            rag_result = self.summarizer.rag_query(query, max_chunks=8)
            
            if 'error' in rag_result:
                logger.error(f"❌ RAG error: {rag_result['error']}")
                return jsonify({"error": rag_result['error']}), 500
            
            # Process result for frontend
            search_result = self.process_rag_result(rag_result, start_time)
            
            # Cache result (optional)
            search_result_dict = asdict(search_result)
            search_result_dict['timestamp'] = time.time()
            self.query_cache[cache_key] = search_result_dict
            
            logger.info(f"✅ Search complete: {search_result.processing_time:.2f}s, ${search_result.cost_usd:.4f}")
            
            return jsonify(asdict(search_result))
            
        except Exception as e:
            logger.error(f"💥 Search failed: {e}")
            return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    
    def process_rag_result(self, rag_result: Dict[str, Any], start_time: float) -> SearchResult:
        """Process RAG result into frontend-friendly format"""
        
        # Determine confidence based on source similarity and count
        citations = rag_result.get('citations', [])
        avg_similarity = sum(c['similarity'] for c in citations) / len(citations) if citations else 0
        
        if avg_similarity > 0.85 and len(citations) >= 5:
            confidence = "high"
        elif avg_similarity > 0.75 and len(citations) >= 3:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Format sources for frontend
        sources = []
        for citation in citations:
            # Extract video ID and create YouTube URL
            video_id = citation['video_id']
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            
            # Parse timestamp for direct linking
            timestamp_str = citation.get('timestamp', '').strip('[]')
            youtube_timestamp = None
            if timestamp_str and ':' in timestamp_str:
                try:
                    parts = timestamp_str.split(':')
                    if len(parts) == 2:
                        minutes, seconds = map(int, parts)
                        total_seconds = minutes * 60 + seconds
                        youtube_url += f"&t={total_seconds}s"
                        youtube_timestamp = total_seconds
                except:
                    pass
            
            source = {
                "video_id": video_id,
                "title": citation['title'],
                "url": youtube_url,
                "timestamp": timestamp_str,
                "timestamp_seconds": youtube_timestamp,
                "similarity": round(citation['similarity'], 3)
            }
            sources.append(source)
        
        return SearchResult(
            answer=rag_result['answer'],
            confidence=confidence,
            sources=sources,
            processing_time=time.time() - start_time,
            cost_usd=rag_result.get('cost_usd', 0.0)
        )
    
    def run(self, host='0.0.0.0', port=5001, debug=False):
        """Run the Flask API service"""
        logger.info(f"🚀 Starting RAG API service on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG API Service")
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5001, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Validate environment
    if not os.getenv('OPENAI_API_KEY'):
        logger.error("❌ OPENAI_API_KEY environment variable required")
        sys.exit(1)
    
    if not os.getenv('DATABASE_URL'):
        logger.error("❌ DATABASE_URL environment variable required")
        sys.exit(1)
    
    # Start service
    service = RAGAPIService()
    service.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == "__main__":
    main()
