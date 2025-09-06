# Hosted Deployment Solution

## Google Takeout Process (Super Simple for Dr. Chaffee)

### One-Time Setup (5 minutes)
1. Go to [Google Takeout](https://takeout.google.com)
2. Click **Deselect all**
3. Scroll to **YouTube and YouTube Music** → Check the box
4. Click **All YouTube data included**
5. **Uncheck everything except "subtitles"**
6. Choose format: **ZIP** 
7. Click **Next step** → **Create export**
8. Google emails when ready (usually 1-2 hours)
9. Download ZIP file and share with you

**Result:** All captions for hundreds of videos in SRT format, organized by video ID.

## Hosted Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   Dr. Chaffee   │───▶│  Google Takeout  │───▶│    SRT Files ZIP    │
│                 │    │                  │    │                     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
                                                           │
                                                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        HOSTED SOLUTION                              │
├─────────────────┬─────────────────┬─────────────────┬─────────────────┤
│   File Upload   │  SRT Processor  │   PostgreSQL    │  LLM Frontend   │
│     Service     │                 │    Database     │                 │
│                 │                 │                 │                 │
│ • Web interface │ • Parse SRT     │ • Store chunks  │ • Q&A interface │
│ • Drag & drop   │ • Generate      │ • Embeddings    │ • Search        │
│ • Process ZIP   │   embeddings    │ • Metadata      │ • Chat over     │
│                 │ • Chunk text    │                 │   transcripts   │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
```

## Deployment Stack

### Backend Services
- **FastAPI** - Upload and processing API
- **PostgreSQL** - Caption storage with vector embeddings
- **Redis** - Processing queue and cache
- **Docker** - Containerized deployment

### Frontend  
- **Next.js** - Upload interface and LLM chat
- **Tailwind CSS** - Modern UI
- **WebSocket** - Real-time processing updates

### Hosting Options
- **Railway** - Simple, auto-deploy from Git
- **Vercel + Supabase** - Serverless with managed DB
- **DigitalOcean App Platform** - Full-stack hosting
- **Heroku** - Classic platform (more expensive)

## File Structure for Hosted Solution

```
ask-dr-chaffee/
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI app
│   │   ├── upload_handler.py    # SRT upload processing  
│   │   ├── search_api.py        # LLM search endpoints
│   │   └── database.py          # DB connections
│   ├── workers/
│   │   ├── srt_processor.py     # Background SRT processing
│   │   └── embedding_worker.py  # Generate embeddings
│   └── Dockerfile
├── frontend/
│   ├── pages/
│   │   ├── upload.tsx           # SRT file upload
│   │   ├── search.tsx           # LLM Q&A interface
│   │   └── admin.tsx            # Processing status
│   ├── components/
│   │   ├── FileUpload.tsx       # Drag & drop upload
│   │   └── ChatInterface.tsx    # LLM chat UI
│   └── package.json
├── docker-compose.yml           # Local development
└── railway.json                 # Deployment config
```

## Implementation Plan

### Phase 1: Core Upload & Processing (Week 1)
```python
# backend/api/main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from workers.srt_processor import process_srt_zip

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

@app.post("/upload/srt-zip")
async def upload_srt_zip(file: UploadFile = File(...)):
    """Upload and process SRT ZIP from Google Takeout"""
    # Save uploaded ZIP
    # Extract SRT files
    # Queue for background processing
    # Return job ID for status tracking
    
@app.get("/processing-status/{job_id}")
async def get_processing_status(job_id: str):
    """Get real-time processing status"""
    # Return: processed_count, total_count, current_video, errors
```

### Phase 2: LLM Integration (Week 2)  
```python
@app.post("/search")
async def search_transcripts(query: str):
    """Search transcripts using embeddings + LLM"""
    # 1. Generate query embedding
    # 2. Vector search in PostgreSQL
    # 3. Pass relevant chunks to LLM
    # 4. Return formatted response with sources

@app.post("/chat")
async def chat_with_transcripts(message: str, conversation_id: str = None):
    """Chat interface over all transcripts"""
    # OpenAI/Anthropic API integration
    # Context from vector search
    # Conversation history
```

### Phase 3: Frontend (Week 3)
- File upload interface with progress tracking
- Real-time processing status
- Chat interface for Q&A
- Search with source citations

## Database Schema (Enhanced)

```sql
-- Enhanced for hosted solution
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(20) UNIQUE,
    title TEXT,
    channel_title VARCHAR(255) DEFAULT 'Dr. Anthony Chaffee',
    published_at TIMESTAMP,
    duration_seconds INTEGER,
    source_file VARCHAR(255), -- Original SRT filename
    processed_at TIMESTAMP DEFAULT NOW(),
    source_type VARCHAR(50) DEFAULT 'youtube_takeout'
);

CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status VARCHAR(20) DEFAULT 'pending', -- pending, processing, completed, failed
    total_files INTEGER,
    processed_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);
```

## Deployment Commands

### Railway (Recommended)
```bash
# 1. Connect GitHub repo to Railway
# 2. Add environment variables:
#    - DATABASE_URL (auto-provided)
#    - OPENAI_API_KEY  
#    - ANTHROPIC_API_KEY
# 3. Deploy automatically on Git push

# Environment variables needed:
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=ant-...
REDIS_URL=redis://...
```

### Docker Compose (Local Development)
```bash
# Full stack with one command
docker-compose up

# Services included:
# - PostgreSQL with pgvector
# - Redis for job queue
# - FastAPI backend
# - Next.js frontend
# - Nginx reverse proxy
```

## Cost Estimates (Monthly)

### Railway (Recommended)
- **Hobby Plan**: $5/month
- **Pro Plan**: $20/month (for production)
- Includes: PostgreSQL, Redis, auto-deployments

### Vercel + Supabase  
- **Vercel Pro**: $20/month
- **Supabase Pro**: $25/month
- Total: $45/month

### Self-hosted (DigitalOcean)
- **Droplet**: $12/month (2GB RAM)
- **Managed DB**: $15/month
- Total: $27/month

## Next Steps

1. **Get Google Takeout from Dr. Chaffee** (5 minutes for him)
2. **Deploy basic upload interface** (Railway - 1 day)
3. **Process SRT files into database** (existing code - 1 day)  
4. **Add LLM search interface** (OpenAI API - 2 days)
5. **Polish and launch** (1 week)

**Total timeline: ~2 weeks for full hosted solution**

Would you like me to start with the FastAPI upload handler or the deployment configuration?
