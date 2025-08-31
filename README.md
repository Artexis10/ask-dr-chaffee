# Ask Dr. Chaffee

A searchable transcript app for Dr. Anthony Chaffee's YouTube and Zoom recordings.

## Project Structure

```
ask-dr-chaffee/
├── frontend/                 # Next.js frontend
│   ├── src/
│   │   ├── pages/
│   │   └── components/
│   ├── package.json
│   └── next.config.js
├── backend/                  # Python backend
│   ├── scripts/
│   │   ├── ingest_youtube.py
│   │   ├── ingest_zoom.py
│   │   └── common/
│   └── requirements.txt
├── db/
│   └── schema.sql           # Database schema
├── docker-compose.yml       # Postgres + pgvector
├── Makefile                # Development commands
├── .env.example            # Environment template
└── README.md
```

## Quick Start

1. **Setup Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Start Database**
   ```bash
   make dev
   ```

3. **Run Ingestion**
   ```bash
   make ingest-youtube
   ```

4. **Start Frontend**
   ```bash
   cd frontend && npm run dev
   ```

## Requirements

- Windows 11
- Docker Desktop
- Python 3.8+
- Node.js 18+

## Architecture

- **Frontend**: Next.js with search interface
- **Backend**: Python scripts for transcript ingestion
- **Database**: Postgres with pgvector for embeddings
- **Embeddings**: sentence-transformers/all-MiniLM-L6-v2
- **Transcripts**: youtube-transcript-api + faster-whisper fallback
