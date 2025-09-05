.PHONY: dev setup ingest-youtube ingest-zoom stop clean install-frontend install-backend

# Development commands
dev: setup
	docker-compose up -d
	@echo "Database is starting up..."
	@echo "Frontend: cd frontend && npm run dev"
	@echo "Backend ready for ingestion scripts"

setup:
	@echo "Setting up Ask Dr. Chaffee development environment..."
	@if not exist .env (copy .env.example .env && echo "Created .env file - please edit with your configuration")

# Database management
db-up:
	docker-compose up -d postgres

db-down:
	docker-compose down

db-reset:
	docker-compose down -v
	docker-compose up -d postgres

# Installation commands
install-frontend:
	cd frontend && npm install

install-backend:
	cd backend && pip install -r requirements.txt

install: install-frontend install-backend

# Enhanced ingestion commands (API is now default)
ingest-youtube:
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --concurrency 4 --newest-first --skip-shorts

ingest-youtube-seed:
	@echo "Running YouTube ingestion in seed mode (first 20 videos)..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --limit 20 --newest-first --skip-shorts

ingest-youtube-fallback:
	@echo "Running YouTube ingestion using yt-dlp fallback..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source yt-dlp --concurrency 4 --newest-first --skip-shorts

# Production-ready backfill commands (API is now default)
backfill-youtube:
	@echo "Starting full YouTube channel backfill using API..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --newest-first --concurrency 4 --skip-shorts

sync-youtube:
	@echo "Syncing recent YouTube videos..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --newest-first --limit 25 --concurrency 3 --skip-shorts

seed-youtube:
	@echo "Seeding with recent videos..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --limit 10 --newest-first --skip-shorts

backfill-youtube-fallback:
	@echo "Backfilling using yt-dlp fallback..."
	@if not exist backend\data mkdir backend\data
	yt-dlp --flat-playlist -J "$(or $(YOUTUBE_CHANNEL_URL),https://www.youtube.com/@anthonychaffeemd)/videos" > backend\data\videos.json
	cd backend && python scripts/ingest_youtube_enhanced.py --source yt-dlp --from-json data/videos.json --concurrency 4 --newest-first --skip-shorts

# Status monitoring and debugging
ingest-status:
	@echo "=== INGESTION STATUS REPORT ==="
	@cd backend && python -c "from scripts.common.database_upsert import DatabaseUpserter; import os; db = DatabaseUpserter(os.getenv('DATABASE_URL')); stats = db.get_ingestion_stats(); print(f\"Total videos: {stats['total_videos']}\"); print(f\"Total sources: {stats['total_sources']}\"); print(f\"Total chunks: {stats['total_chunks']}\"); print(f\"\\nStatus breakdown:\"); [print(f\"  {k}: {v}\") for k, v in stats['status_counts'].items()]; print(f\"\\nTop errors:\") if stats['error_summary'] else None; [print(f\"  {k}: {v}\") for k, v in stats['error_summary'].items()]"

ingest-errors:
	@echo "=== INGESTION ERRORS ==="
	@cd backend && python -c "from scripts.common.database_upsert import DatabaseUpserter; import os; db = DatabaseUpserter(os.getenv('DATABASE_URL')); errors = db.get_videos_by_status('error', limit=20); [print(f\"{video['video_id']}: {video.get('last_error', 'Unknown error')[:100]}...\") for video in errors]; print(f\"\\nShowing first 20 of {len(db.get_videos_by_status('error'))} total errors\")"

ingest-queue:
	@echo "=== PENDING QUEUE STATUS ==="
	@cd backend && python -c "from scripts.common.database_upsert import DatabaseUpserter; import os; db = DatabaseUpserter(os.getenv('DATABASE_URL')); pending = len(db.get_videos_by_status('pending')); errors = len([v for v in db.get_videos_by_status('error') if v.get('retries', 0) < 3]); print(f\"Pending: {pending}\"); print(f\"Retryable errors: {errors}\"); print(f\"Total in queue: {pending + errors}\")"

# Video listing commands  
list-youtube:
	@echo "Dumping YouTube channel video list to JSON..."
	@if not exist backend\data mkdir backend\data
	yt-dlp --flat-playlist -J "$(or $(YOUTUBE_CHANNEL_URL),https://www.youtube.com/@anthonychaffeemd)/videos" > backend\data\videos.json
	@echo "Video list saved to backend/data/videos.json"

list-youtube-api:
	@echo "Listing videos using YouTube Data API..."
	cd backend && python scripts/common/list_videos_api.py "$(or $(YOUTUBE_CHANNEL_URL),https://www.youtube.com/@anthonychaffeemd)" --limit 50

# Test and validation commands
test-ingestion:
	@echo "Testing ingestion pipeline (dry run)..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --limit 5 --dry-run

validate-transcripts:
	@echo "Validating transcript fetching..."
	cd backend && python scripts/common/transcript_fetch.py dQw4w9WgXcQ

# Legacy support
ingestion-stats: ingest-status

ingest-zoom:
	cd backend && python scripts/ingest_zoom.py

# Utility commands
stop:
	docker-compose down

clean:
	docker-compose down -v
	docker system prune -f

logs:
	docker-compose logs -f

# Help
help:
	@echo "Available commands:"
	@echo "  dev              - Start development environment"
	@echo "  setup            - Initial project setup"
	@echo "  install          - Install all dependencies"
	@echo "  install-frontend - Install frontend dependencies"
	@echo "  install-backend  - Install backend dependencies"
	@echo "  ingest-youtube   - Run YouTube transcript ingestion (API default)"
	@echo "  sync-youtube     - Sync recent videos (25 latest)"
	@echo "  seed-youtube     - Quick seed with 10 videos"
	@echo "  backfill-youtube - Full channel backfill using API"
	@echo "  ingest-zoom      - Run Zoom transcript ingestion"
	@echo "  db-up           - Start database only"
	@echo "  db-down         - Stop database"
	@echo "  db-reset        - Reset database (delete all data)"
	@echo "  stop            - Stop all services"
	@echo "  clean           - Clean up containers and volumes"
	@echo "  logs            - Show container logs"
	@echo "  help            - Show this help message"
