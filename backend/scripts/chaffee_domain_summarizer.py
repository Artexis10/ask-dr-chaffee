#!/usr/bin/env python3
"""
Dr. Chaffee Domain-Aware Summarizer
Specialized AI summarization for carnivore diet and metabolic health content
"""

import os
import sys
import logging
import json
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

# Add parent directories to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SummaryConfig:
    """Configuration for domain-aware summarization"""
    openai_api_key: str
    model: str = "gpt-4-turbo"
    max_tokens_output: int = 2000
    temperature: float = 0.1  # Low temperature for medical accuracy
    focus_areas: List[str] = None
    include_citations: bool = True
    medical_accuracy_mode: bool = True

class ChaffeeDomainSummarizer:
    """Domain-aware summarizer specialized for Dr. Chaffee's medical content"""
    
    def __init__(self, config: SummaryConfig):
        self.config = config
        
        # Dr. Chaffee-specific terminology corrections
        self.terminology_corrections = {
            "carnival diet": "carnivore diet",
            "auto immune": "autoimmune",
            "key toe sis": "ketosis",
            "electric tights": "electrolytes",
            "fits states": "phytates",
            "lecture tins": "lectins",
            "metta bolic": "metabolic",
            "new road": "neuro",
            "in slim": "insulin",
            "car know vore": "carnivore"
        }
        
        # Domain-specific focus areas
        self.default_focus_areas = [
            "Medical claims and supporting evidence",
            "Practical dietary recommendations", 
            "Carnivore diet benefits and mechanisms",
            "Autoimmune condition treatments",
            "Metabolic health insights",
            "Plant toxin discussions (lectins, phytates, etc.)",
            "Patient case studies and examples",
            "Contrarian viewpoints to mainstream medicine",
            "Scientific studies and references mentioned"
        ]
    
    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 0.75 words)"""
        return int(len(text.split()) * 1.33)
    
    def create_domain_prompt(self, transcript: str, summary_type: str = "comprehensive") -> str:
        """Create domain-aware prompt for Dr. Chaffee content"""
        
        focus_areas = self.config.focus_areas or self.default_focus_areas
        focus_list = "\n".join([f"  {i+1}. {area}" for i, area in enumerate(focus_areas)])
        
        if summary_type == "comprehensive":
            prompt = f"""You are a medical content analyst specializing in carnivore diet, metabolic health, and evidence-based medicine. You are analyzing content from Dr. Anthony Chaffee, a neurosurgeon who advocates for carnivore diet based on evolutionary biology and clinical experience.

MEDICAL ACCURACY REQUIREMENTS:
- Use precise medical terminology
- Distinguish between anecdotal evidence and clinical studies
- Note when claims need further research
- Highlight any safety considerations or contraindications

DOMAIN EXPERTISE CONTEXT:
- Dr. Chaffee is a practicing neurosurgeon and carnivore diet advocate
- Focus on evolutionary biology rationale for human diet
- Emphasis on eliminating plant toxins (lectins, phytates, oxalates)
- Autoimmune conditions as central focus area
- Metabolic flexibility and ketosis as health optimization tools

TERMINOLOGY CORRECTIONS (fix common transcription errors):
- "carnival diet" → "carnivore diet"
- "auto immune" → "autoimmune" 
- "key toe sis" → "ketosis"
- "electric tights" → "electrolytes"
- "fits states" → "phytates"
- "lecture tins" → "lectins"

SUMMARIZATION FOCUS AREAS:
{focus_list}

OUTPUT REQUIREMENTS:
- Comprehensive summary (1500-2000 words)
- Clear section headers for each focus area
- Bullet points for key takeaways
- Include specific timestamps if mentioned
- Note any scientific studies referenced
- Highlight practical actionable advice
- Flag any controversial or contrarian claims

TRANSCRIPT TO ANALYZE:
{transcript}

Please provide a detailed, medically-accurate summary following the structure above."""

        elif summary_type == "focused":
            prompt = f"""You are analyzing Dr. Anthony Chaffee content with focus on specific areas. Dr. Chaffee is a neurosurgeon who advocates carnivore diet for health optimization.

SPECIFIC FOCUS: {', '.join(focus_areas)}

Extract and summarize ONLY information related to the focus areas above. Be concise but thorough.

TRANSCRIPT EXCERPT:
{transcript}

Provide a focused summary (500-800 words) covering only the specified focus areas."""
        
        return prompt
    
    def correct_terminology(self, text: str) -> str:
        """Apply terminology corrections to fix transcription errors"""
        corrected_text = text
        for incorrect, correct in self.terminology_corrections.items():
            corrected_text = corrected_text.replace(incorrect, correct)
        return corrected_text
    
    def get_video_transcript(self, video_id: str) -> Optional[str]:
        """Retrieve full transcript from database"""
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            cursor = conn.cursor()
            
            # Get all chunks for the video, ordered by chunk ID (approximates timestamp order)
            cursor.execute("""
                SELECT c.text, s.metadata
                FROM chunks c
                JOIN sources s ON c.source_id = s.id  
                WHERE s.url LIKE %s
                ORDER BY c.id
            """, (f'%{video_id}%',))
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if not results:
                logger.warning(f"No transcript found for video {video_id}")
                return None
            
            # Combine chunks into full transcript
            transcript_parts = []
            for i, (text, metadata) in enumerate(results):
                # Simple chunk numbering since we don't have individual timestamps
                transcript_parts.append(f"[Segment {i+1}] {text}")
            
            full_transcript = "\n".join(transcript_parts)
            return self.correct_terminology(full_transcript)
            
        except Exception as e:
            logger.error(f"Error retrieving transcript for {video_id}: {e}")
            return None
    
    def summarize_full_video(self, video_id: str, custom_focus: List[str] = None) -> Dict[str, Any]:
        """Create comprehensive summary of entire video"""
        logger.info(f"📝 Creating comprehensive summary for video {video_id}")
        
        # Override focus areas if provided
        if custom_focus:
            self.config.focus_areas = custom_focus
        
        transcript = self.get_video_transcript(video_id)
        if not transcript:
            return {"error": f"No transcript found for video {video_id}"}
        
        # Check token limits
        estimated_tokens = self.estimate_tokens(transcript)
        logger.info(f"📊 Estimated tokens: {estimated_tokens:,}")
        
        if estimated_tokens > 120000:  # Close to GPT-4-turbo limit
            logger.warning(f"⚠️ Large transcript ({estimated_tokens:,} tokens) - may need chunking")
            return self.chunked_summarization(transcript, video_id)
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.config.openai_api_key)
            
            prompt = self.create_domain_prompt(transcript, "comprehensive")
            
            start_time = time.time()
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.config.max_tokens_output,
                temperature=self.config.temperature
            )
            
            processing_time = time.time() - start_time
            
            # Calculate costs
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            
            # GPT-4-turbo pricing
            input_cost = input_tokens * 0.01 / 1000
            output_cost = output_tokens * 0.03 / 1000
            total_cost = input_cost + output_cost
            
            summary = response.choices[0].message.content
            
            logger.info(f"✅ Summary complete: {input_tokens:,} input tokens, "
                       f"{output_tokens:,} output tokens, ${total_cost:.4f}")
            
            return {
                "video_id": video_id,
                "summary": summary,
                "model": self.config.model,
                "processing_time": processing_time,
                "token_usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens
                },
                "cost_usd": total_cost,
                "focus_areas": self.config.focus_areas or self.default_focus_areas,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"❌ Summarization failed: {e}")
            return {"error": str(e)}
    
    def chunked_summarization(self, transcript: str, video_id: str) -> Dict[str, Any]:
        """Handle very large transcripts by chunking"""
        logger.info(f"🔄 Using chunked summarization for large transcript")
        
        # Split transcript into manageable chunks (50k tokens each)
        words = transcript.split()
        chunk_size = 37500  # ~50k tokens
        chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
        
        chunk_summaries = []
        total_cost = 0.0
        
        for i, chunk in enumerate(chunks):
            logger.info(f"📝 Processing chunk {i+1}/{len(chunks)}")
            
            prompt = self.create_domain_prompt(chunk, "focused")
            
            try:
                import openai
                response = openai.ChatCompletion.create(
                    model=self.config.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1000,  # Shorter summaries for chunks
                    temperature=self.config.temperature
                )
                
                chunk_summary = response['choices'][0]['message']['content']
                chunk_summaries.append(f"PART {i+1}: {chunk_summary}")
                
                # Calculate cost
                input_tokens = response['usage']['prompt_tokens']
                output_tokens = response['usage']['completion_tokens']
                chunk_cost = (input_tokens * 0.01 + output_tokens * 0.03) / 1000
                total_cost += chunk_cost
                
            except Exception as e:
                logger.error(f"❌ Chunk {i+1} failed: {e}")
                chunk_summaries.append(f"PART {i+1}: [ERROR - {str(e)}]")
        
        # Synthesize final summary from chunks
        combined_chunks = "\n\n".join(chunk_summaries)
        synthesis_prompt = f"""
        The following are summaries of different parts of a Dr. Anthony Chaffee video. 
        Create a comprehensive, cohesive final summary that integrates all parts:
        
        {combined_chunks}
        
        Provide a unified summary (1500-2000 words) that flows naturally and eliminates redundancy.
        """
        
        try:
            import openai
            final_response = openai.ChatCompletion.create(
                model=self.config.model,
                messages=[{"role": "user", "content": synthesis_prompt}],
                max_tokens=self.config.max_tokens_output,
                temperature=self.config.temperature
            )
            
            final_summary = final_response['choices'][0]['message']['content']
            
            # Add synthesis cost
            synthesis_cost = (final_response['usage']['prompt_tokens'] * 0.01 + 
                            final_response['usage']['completion_tokens'] * 0.03) / 1000
            total_cost += synthesis_cost
            
            logger.info(f"✅ Chunked summarization complete: ${total_cost:.4f}")
            
            return {
                "video_id": video_id,
                "summary": final_summary,
                "model": self.config.model,
                "method": "chunked",
                "chunks_processed": len(chunks),
                "cost_usd": total_cost,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"❌ Final synthesis failed: {e}")
            return {"error": f"Synthesis failed: {e}"}
    
    def rag_query(self, question: str, max_chunks: int = 10) -> Dict[str, Any]:
        """Answer specific questions using RAG approach"""
        logger.info(f"🔍 RAG query: {question}")
        
        try:
            from scripts.common.embeddings import EmbeddingGenerator
            
            embedder = EmbeddingGenerator()
            
            # Search for relevant chunks
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            cursor = conn.cursor()
            
            # Generate query embedding
            query_embedding = embedder.generate_embeddings([question])[0]
            
            # Semantic search for relevant chunks
            cursor.execute("""
                SELECT c.text, s.metadata, s.title, s.url,
                       1 - (c.embedding <=> %s::vector) as similarity
                FROM chunks c
                JOIN sources s ON c.source_id = s.id
                WHERE s.source_type = 'youtube'
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
            """, (query_embedding, query_embedding, max_chunks))
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if not results:
                return {"error": "No relevant content found"}
            
            # Build RAG context
            context_parts = []
            citations = []
            
            for text, metadata, title, url, similarity in results:
                # Extract video ID from URL
                video_id = url.split('v=')[-1].split('&')[0] if 'v=' in url else url.split('/')[-1]
                
                # Simple context without timestamp for now
                context_parts.append(f"[{title}]: {text}")
                citations.append({
                    "video_id": video_id,
                    "title": title,
                    "timestamp": "",  # No timestamp available in current schema
                    "similarity": round(similarity, 3)
                })
            
            context = "\n\n".join(context_parts)
            
            # Create RAG prompt
            prompt = f"""You are answering a question about Dr. Anthony Chaffee's content. Dr. Chaffee is a neurosurgeon who advocates carnivore diet for health optimization.

QUESTION: {question}

RELEVANT CONTENT FROM DR. CHAFFEE'S VIDEOS:
{context}

Based on the provided content, answer the question accurately. Include:
1. Direct answer based on the content
2. Any caveats or nuances mentioned
3. Supporting evidence or examples provided
4. Reference which video(s) the information comes from

If the content doesn't fully answer the question, acknowledge the limitations."""
            
            # Query OpenAI
            from openai import OpenAI
            client = OpenAI(api_key=self.config.openai_api_key)
            
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=self.config.temperature
            )
            
            answer = response.choices[0].message.content
            
            # Calculate cost
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = (input_tokens * 0.01 + output_tokens * 0.03) / 1000
            
            logger.info(f"✅ RAG query complete: ${cost:.4f}")
            
            return {
                "question": question,
                "answer": answer,
                "citations": citations,
                "chunks_used": len(results),
                "cost_usd": cost,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"❌ RAG query failed: {e}")
            return {"error": str(e)}

def main():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Dr. Chaffee Domain-Aware Summarizer")
    parser.add_argument('--video-id', type=str, help='Video ID to summarize')
    parser.add_argument('--query', type=str, help='Question to answer using RAG')
    parser.add_argument('--focus', nargs='+', help='Custom focus areas for summary')
    parser.add_argument('--model', default='gpt-4-turbo', help='OpenAI model to use')
    
    args = parser.parse_args()
    
    # Configure summarizer
    config = SummaryConfig(
        openai_api_key=os.getenv('OPENAI_API_KEY'),
        model=args.model,
        focus_areas=args.focus if args.focus else None
    )
    
    if not config.openai_api_key:
        print("❌ OPENAI_API_KEY environment variable required")
        sys.exit(1)
    
    summarizer = ChaffeeDomainSummarizer(config)
    
    if args.video_id:
        # Video summarization
        result = summarizer.summarize_full_video(args.video_id)
        if 'error' in result:
            print(f"❌ Error: {result['error']}")
        else:
            print(f"✅ Summary for {args.video_id}:")
            print(f"💰 Cost: ${result['cost_usd']:.4f}")
            print(f"📊 Tokens: {result['token_usage']['total_tokens']:,}")
            print("\n" + "="*80)
            print(result['summary'])
    
    elif args.query:
        # RAG query
        result = summarizer.rag_query(args.query)
        if 'error' in result:
            print(f"❌ Error: {result['error']}")
        else:
            print(f"🔍 Question: {result['question']}")
            print(f"💰 Cost: ${result['cost_usd']:.4f}")
            print(f"📚 Sources: {result['chunks_used']} chunks")
            print("\n" + "="*80)
            print(result['answer'])
            print("\n📖 Citations:")
            for citation in result['citations'][:5]:  # Show top 5
                print(f"  - {citation['title']} {citation['timestamp']} (similarity: {citation['similarity']})")
    
    else:
        print("❌ Provide either --video-id for summarization or --query for RAG")

if __name__ == "__main__":
    main()
