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
   make ingest-youtube-seed  # First 10 videos only
   # OR for full ingestion:
   # make ingest-youtube
   ```

5. **Start Frontend**
   ```bash
   make dev-frontend
   # OR: cd frontend && npm run dev
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

# Features
RERANK_ENABLED=true  # Enable cross-encoder reranking
SEED=1               # Enable seed mode (10 videos max)

# Optional
CHUNK_DURATION_SECONDS=45  # Transcript chunk size
```

### Available Commands
```bash
# Development
make help                 # Show all available commands
make setup               # Initial project setup
make dev-frontend        # Start Next.js dev server

# Database
make db-up              # Start PostgreSQL
make db-down            # Stop PostgreSQL  
make db-reset           # Reset database (deletes data)

# Ingestion
make ingest-youtube     # Full YouTube channel ingestion
make ingest-youtube-seed # Development mode (10 videos)
make ingest-zoom        # Zoom recordings ingestion

# Development Tools
pre-commit install      # Set up code quality hooks
nvm use                # Use Node.js version from .nvmrc
```

## 🔍 Search Tips

- **Exact Phrases**: Use quotes for exact matches: `"carnivore diet"`
- **Multiple Topics**: Search for related terms: `thyroid autoimmune inflammation`
- **Filter by Source**: Use source pills to focus on YouTube or Zoom content
- **Filter by Year**: Use year dropdown to find recent or historical content
- **Copy Links**: Use "Copy Link" to share specific moments with others

## ⚠️ Important Notes

- **Educational Content**: All content is for educational purposes only
- **Medical Disclaimer**: Always consult healthcare providers for medical advice
- **Official Channel**: Visit [Dr. Chaffee's YouTube](https://www.youtube.com/@anthonychaffeemd) for latest content
- **Development Mode**: Use seed mode for faster testing with limited content
