#!/usr/bin/env python3

import os
import json
import requests
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/askdrchaffee')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

def format_timestamp(seconds):
    seconds = int(seconds)  # Convert to int to handle float values
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"

def test_synthesis():
    try:
        # Get some carnivore-related chunks
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        query = """
            SELECT 
              c.id,
              c.source_id,
              s.source_id as video_id,
              s.title,
              c.text,
              c.start_time_seconds,
              c.end_time_seconds,
              s.published_at,
              s.source_type
            FROM chunks c
            JOIN sources s ON c.source_id = s.id
            WHERE c.text ILIKE %s
            ORDER BY s.published_at DESC, c.start_time_seconds ASC
            LIMIT 8
        """
        
        cur.execute(query, ['%carnivore%'])
        results = cur.fetchall()
        conn.close()
        
        if not results:
            print("No chunks found")
            return
            
        print(f"Found {len(results)} chunks for synthesis")
        
        # Format excerpts like the API does
        excerpts = []
        for row in results:
            video_id, title, text, start_time, end_time, published_at = row[2], row[3], row[4], row[5], row[6], row[7]
            excerpts.append({
                'id': f"{video_id}@{format_timestamp(start_time)}",
                'date': published_at.strftime('%Y-%m-%d'),
                'text': text[:200] + ('...' if len(text) > 200 else '')  # Truncate to save tokens
            })
        
        excerpt_text = '\n\n'.join([
            f"- id: {exc['id']}\n  date: {exc['date']}\n  text: \"{exc['text']}\""
            for exc in excerpts
        ])
        
        system_prompt = """You are compiling a long-form synthesis of Dr. Anthony Chaffee's views. Ground EVERYTHING strictly in the provided transcript excerpts. Do NOT use outside knowledge or speculation. Write a cohesive, well-structured markdown answer that synthesizes across clips. Use ## section headers for organization. Cite with inline timestamps like [video_id@mm:ss] at the END of sentences/clauses they support. Prefer newer material when consolidating conflicting statements. If views evolved, state the nuance and cite both. Tone: neutral narrator summarizing Chaffee's position; do not speak as him."""
        
        user_prompt = f"""You are compiling a long-form synthesis of Dr. Anthony Chaffee's views.

Query: "carnivore diet approach"

Context Excerpts (use only these):
{excerpt_text}

Instructions:
- Ground EVERYTHING strictly in the provided transcript excerpts. Do NOT use outside knowledge or speculation.
- Write a cohesive, well-structured markdown answer (use ## section headers) that synthesizes across clips.
- Length target: 400-800 words (ok to be shorter if context is thin).
- Use inline timestamp citations like [video_id@mm:ss] at the END of the sentences/clauses they support.
- Cite whenever a claim depends on a specific excerpt; don't over-cite trivial transitions.
- Prefer newer material when consolidating conflicting statements; if views evolved, state the nuance and cite both.
- If a point is unclear or missing in the excerpts, say so briefly (e.g., "not addressed in provided excerpts").
- Tone: neutral narrator summarizing Chaffee's position; do not speak as him.

Output MUST be valid JSON with this schema:
{{
  "answer": "Markdown with sections and inline citations like [abc123@12:34]. 400-800 words if context supports it.",
  "citations": [
    {{ "video_id": "abc123", "timestamp": "12:34", "date": "2024-06-18" }}
  ],
  "confidence": 0.85,
  "notes": "Optional brief notes: conflicts seen, gaps, or scope limits."
}}

Validation requirements:
- Every [video_id@mm:ss] that appears in answer MUST also appear once in citations[].
- Every citation MUST correspond to an excerpt listed above (exact match or within ±5s).
- Do NOT include citations to sources not present in the excerpts.
- Keep formatting clean: no stray backslashes, no code fences in answer, no HTML.
- If context is too sparse, create a short answer and explain the limitation in notes."""

        # Call OpenAI API
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'gpt-3.5-turbo',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                'temperature': 0.1,
                'max_tokens': 1500,
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            content = data['choices'][0]['message']['content']
            
            print("=== RAW OPENAI RESPONSE ===")
            print(content)
            print("\n=== PARSED JSON ===")
            
            try:
                parsed = json.loads(content)
                print(json.dumps(parsed, indent=2))
                
                print(f"\n=== ANALYSIS ===")
                print(f"Answer length: {len(parsed.get('answer', ''))} chars")
                print(f"Citations count: {len(parsed.get('citations', []))}")
                print(f"Confidence: {parsed.get('confidence', 'N/A')}")
                print(f"Notes: {parsed.get('notes', 'None')}")
                
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {e}")
                
        else:
            print(f"OpenAI API error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_synthesis()
