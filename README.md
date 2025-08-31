# Ask Dr. Chaffee

**Ask Dr. Chaffee** is an AI-powered transcript search app for Dr. Anthony Chaffee’s content.  
It indexes transcripts from his **YouTube channel** and optional **Zoom recordings**, then makes them searchable with semantic embeddings and full-text queries.  
Instead of digging through hundreds of hours of video, you can jump straight to the exact clip where a topic is discussed.

---

## ✨ Features

- 🔎 Semantic & keyword search across Dr. Chaffee’s talks  
- ⏱ Timestamped results with direct links to YouTube or Zoom  
- 🎥 Unified database for both YouTube uploads and Zoom recordings  
- ⚡ Powered by Postgres + pgvector for fast similarity search  
- 🧩 Modular ingestion scripts for YouTube and Zoom (with Whisper fallback)  

---

## 📂 Project Structure

```
ask-dr-chaffee/
├── frontend/ # Next.js frontend
│ ├── src/
│ │ ├── pages/ # Search page + API endpoint
│ │ └── components/ # UI components
│ ├── package.json
│ └── next.config.js
├── backend/ # Python ingestion pipeline
│ ├── scripts/
│ │ ├── ingest_youtube.py # YouTube transcript ingestion
│ │ ├── ingest_zoom.py # Zoom VTT ingestion
│ │ └── common/ # Shared utilities
│ └── requirements.txt
├── db/
│ └── schema.sql # Postgres + pgvector schema
├── docker-compose.yml # Database setup
├── Makefile # Dev & ingestion commands
├── .env.example # Environment template
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
