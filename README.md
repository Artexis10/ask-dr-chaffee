# Ask Dr. Chaffee

**Ask Dr. Chaffee** is an AI-powered transcript search app for Dr. Anthony Chaffee’s content.  
It indexes transcripts from his **YouTube channel** and optional **Zoom recordings**, then makes them searchable with semantic embeddings and full-text queries.  
Instead of digging through hundreds of hours of video, you can jump straight to the exact clip where a topic is discussed.

---

## ✨ Features

### 🔍 Enhanced Search Experience
- **Multi-term highlighting** with intelligent query parsing
- **Source filtering** with pills (All | YouTube | Zoom)
- **Year filtering** by publication date
- **Keyboard navigation** (↑↓ arrows, Enter to play, Shift+Enter for YouTube)
- **Loading skeleton states** for better UX
- **Cross-encoder reranking** for improved relevance (toggleable)

### 🎥 Video Integration
- **Embedded YouTube players** grouped by video
- **"Play Here" button** to seek to exact timestamps
- **Copy timestamp links** to clipboard for sharing
- **Segment clustering** merges clips within ±120 seconds
- **Source badges** distinguish YouTube vs Zoom content

### 🔧 Technical Features
- **Semantic & keyword search** with pgvector embeddings
- **Real-time transcript highlighting** of search terms
- **Mobile-responsive design** with optimized layouts
- **Accessibility support** (ARIA labels, focus states, keyboard nav)
- **Analytics events** for user interaction tracking

### 🛠 Developer Experience
- **Seed mode ingestion** (limited to 10 videos for development)
- **Pre-commit hooks** for code quality (Black, Ruff, Prettier, ESLint)
- **Node.js version pinning** with .nvmrc
- **Environment toggles** for features like reranking  

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

## 🚀 Quick Start

### **Linux/macOS (with make)**

1. **Clone & Setup**
   ```bash
   git clone <repository-url>
   cd ask-dr-chaffee
   cp .env.example .env
   # Edit .env with your database URL and feature toggles
   ```

2. **Install Dependencies**
   ```bash
   make install
   # OR manually:
   cd frontend && npm install
   cd ../backend && pip install -r requirements.txt
   ```

3. **Start Database**
   ```bash
   make db-up
   # Database will be available at localhost:5432
   ```

4. **Ingest Content (Development Mode)**
   ```bash
   make ingest-youtube-seed  # First 20 videos only
   # OR for full ingestion:
   # make ingest-youtube
   ```

5. **Start Frontend**
   ```bash
   make dev-frontend
   # OR: cd frontend && npm run dev
   # Available at http://localhost:3001
   ```

### **Windows 11 (PowerShell)**

1. **Clone & Setup**
   ```powershell
   git clone <repository-url>
   Set-Location ask-dr-chaffee
   copy .env.example .env
   # Edit .env with your database URL and feature toggles
   ```

2. **Install Dependencies**
   ```powershell
   # Frontend
   Set-Location frontend
   npm install
   
   # Backend
   Set-Location ..\backend
   pip install -r requirements.txt
   Set-Location ..
   ```

3. **Start Database**
   ```powershell
   docker-compose up -d
   # Database will be available at localhost:5432
   ```

4. **Ingest Content (Development Mode)**
   ```powershell
   Set-Location backend
   python scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 20 --newest-first
   ```

5. **Start Frontend**
   ```powershell
   Set-Location ..\frontend
   npm run dev
   # Available at http://localhost:3001
   ```

## 📋 Requirements

- **OS**: Windows 11 (or macOS/Linux)
- **Docker**: Docker Desktop for PostgreSQL
- **Python**: 3.8+ with pip
- **Node.js**: 20.x (see .nvmrc)
- **Git**: For pre-commit hooks (optional)

## 🏗 Architecture

### Frontend (Next.js)
- **Search Interface**: React components with TypeScript
- **Video Players**: Embedded YouTube iframes with seek controls
- **Filtering**: Source and year filters with URL state management
- **Accessibility**: ARIA labels, keyboard navigation, focus management

### Backend (Python)
- **Ingestion Pipeline**: Modular scripts for YouTube and Zoom
- **Reranking**: Cross-encoder model for relevance improvement
- **Embeddings**: sentence-transformers/all-MiniLM-L6-v2
- **Transcripts**: youtube-transcript-api with Whisper fallback

### Database (PostgreSQL + pgvector)
- **Sources Table**: Video metadata with publication dates
- **Chunks Table**: Transcript segments with timestamps
- **Vector Search**: Semantic similarity with pgvector extension
- **Text Search**: Full-text search with PostgreSQL's built-in capabilities

## 🎯 Usage Guide

### Ingestion Strategies

**yt-dlp Method (Default)**
- ✅ No API key required
- ✅ Works with any YouTube channel
- ✅ Robust scraping approach
- ❌ Slower metadata collection
- ❌ Limited to public data

**YouTube Data API Method**
- ✅ Rich metadata (view counts, exact timestamps)
- ✅ Faster bulk operations
- ✅ Official Google API
- ❌ Requires API key setup
- ❌ API quota limitations

### Search Features
- **Basic Search**: Type any query to find relevant transcript segments
- **Multi-term Queries**: Search for multiple terms, all highlighted in results
- **Filters**: Use source pills (All/YouTube/Zoom) and year dropdown
- **Keyboard Shortcuts**:
  - `↑/↓` arrows: Navigate between results
  - `Enter`: Play in embedded player
  - `Shift+Enter`: Open in YouTube

### Video Controls
- **"Play Here" Button**: Seeks embedded player to exact timestamp
- **"Copy Link" Button**: Copies timestamped YouTube URL to clipboard
- **"Watch on YouTube" Link**: Opens video in new tab

## ⚙️ Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/ask_dr_chaffee

# YouTube Configuration
YOUTUBE_CHANNEL_URL=https://www.youtube.com/@anthonychaffeemd
YOUTUBE_API_KEY=your_api_key_here  # Optional: for YouTube Data API

# Features
RERANK_ENABLED=true  # Enable cross-encoder reranking
SEED=false           # Enable seed mode for development

# Whisper Configuration
WHISPER_MODEL=small.en      # Model size for audio transcription
MAX_AUDIO_DURATION=3600     # Skip very long videos for Whisper

# Processing
CHUNK_DURATION_SECONDS=45   # Transcript chunk size
DEFAULT_CONCURRENCY=4       # Concurrent workers
SKIP_SHORTS=true            # Skip videos < 120 seconds
NEWEST_FIRST=true           # Process newest videos first
```

### Available Commands

#### **Linux/macOS (make)**
```bash
# Development
make help                 # Show all available commands
make setup               # Initial project setup
make dev-frontend        # Start Next.js dev server

# Database
make db-up              # Start PostgreSQL
make db-down            # Stop PostgreSQL  
make db-reset           # Reset database (deletes data)

# Ingestion (Enhanced Pipeline)
make ingest-youtube         # Full channel ingestion (yt-dlp)
make ingest-youtube-seed    # Development mode (20 videos)
make ingest-youtube-api     # Full ingestion using YouTube Data API
make ingest-youtube-api-seed # API development mode (20 videos)

# Video Discovery
make list-youtube          # Dump channel videos to JSON
make list-youtube-api      # List videos using API

# Backfill Operations
make backfill-youtube      # Process from pre-dumped JSON
make backfill-youtube-api  # Full API backfill

# Testing & Validation
make test-ingestion        # Dry run (no database writes)
make validate-transcripts  # Test transcript fetching
make ingestion-stats       # Show processing statistics

# Legacy
make ingest-zoom           # Zoom recordings ingestion

# Development Tools
pre-commit install      # Set up code quality hooks
nvm use                # Use Node.js version from .nvmrc
```

#### **Windows 11 (PowerShell)**
```powershell
# Setup
copy .env.example .env                          # Create environment file
Set-Location frontend; npm install; Set-Location ..\backend; pip install -r requirements.txt; Set-Location ..

# Database
docker-compose up -d                           # Start PostgreSQL
docker-compose down                            # Stop PostgreSQL
docker-compose down -v; docker-compose up -d  # Reset database

# Ingestion (Enhanced Pipeline)
Set-Location backend
python scripts/ingest_youtube_enhanced.py --source yt-dlp --concurrency 4 --newest-first              # Full channel
python scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 20 --newest-first                   # Development mode
python scripts/ingest_youtube_enhanced.py --source api --concurrency 4 --newest-first                 # Full API
python scripts/ingest_youtube_enhanced.py --source api --limit 20 --newest-first                      # API development

# Testing & Validation  
python scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 5 --dry-run                         # Dry run
python scripts/common/transcript_fetch.py dQw4w9WgXcQ                                                 # Test transcript
python scripts/common/database_upsert.py --stats                                                      # Show statistics

# Frontend Development
Set-Location ..\frontend; npm run dev         # Start Next.js dev server

# Video Discovery
python scripts/common/list_videos_yt_dlp.py "https://www.youtube.com/@anthonychaffeemd" --output data/videos.json
python scripts/common/list_videos_api.py "https://www.youtube.com/@anthonychaffeemd" --limit 50
```

## 🔍 Search Tips

- **Exact Phrases**: Use quotes for exact matches: `"carnivore diet"`
- **Multiple Topics**: Search for related terms: `thyroid autoimmune inflammation`
- **Filter by Source**: Use source pills to focus on YouTube or Zoom content
- **Filter by Year**: Use year dropdown to find recent or historical content
- **Copy Links**: Use "Copy Link" to share specific moments with others

## 🔧 Advanced Usage

### CLI Examples
```bash
# Basic ingestion with yt-dlp
python backend/scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 50

# Use YouTube Data API with concurrency
python backend/scripts/ingest_youtube_enhanced.py --source api --concurrency 8 --newest-first

# Process from pre-dumped JSON
python backend/scripts/ingest_youtube_enhanced.py --from-json backend/data/videos.json

# Force Whisper transcription with larger model
python backend/scripts/ingest_youtube_enhanced.py --force-whisper --whisper-model medium.en

# Dry run to preview processing
python backend/scripts/ingest_youtube_enhanced.py --dry-run --limit 10

# Skip very long videos for Whisper fallback
python backend/scripts/ingest_youtube_enhanced.py --max-duration 1800 --skip-shorts
```

### Pipeline Stages
1. **Video Discovery**: List all videos from channel
2. **Transcript Fetching**: Try YouTube captions → fallback to Whisper
3. **Text Processing**: Chunk into ~45-second segments
4. **Embedding Generation**: Create 384-dimensional vectors
5. **Database Storage**: Upsert sources and chunks
6. **State Tracking**: Monitor progress with ingest_state table

### Error Recovery
- **Automatic Retries**: Failed videos retry up to 3 times
- **Resume Capability**: Restart ingestion without losing progress
- **Status Tracking**: Monitor pipeline with `make ingestion-stats`
- **Selective Processing**: Skip completed videos automatically

## ⚠️ Important Notes

- **Educational Content**: All content is for educational purposes only
- **Medical Disclaimer**: Always consult healthcare providers for medical advice
- **Official Channel**: Visit [Dr. Chaffee's YouTube](https://www.youtube.com/@anthonychaffeemd) for latest content
- **API Quotas**: YouTube Data API has daily quotas - monitor usage
- **Storage Requirements**: ~1GB per 1000 videos (including embeddings)
- **Processing Time**: Allow 2-5 minutes per video for full pipeline
