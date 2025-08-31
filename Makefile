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

# Enhanced ingestion commands
ingest-youtube:
	cd backend && python scripts/ingest_youtube_enhanced.py --source yt-dlp --concurrency 4 --newest-first

ingest-youtube-seed:
	@echo "Running YouTube ingestion in seed mode (first 20 videos)..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 20 --newest-first

ingest-youtube-api:
	@echo "Running YouTube ingestion using Data API..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --concurrency 4 --newest-first

ingest-youtube-api-seed:
	@echo "Running YouTube API ingestion in seed mode (first 20 videos)..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --limit 20 --newest-first

# Video listing commands
list-youtube:
	@echo "Dumping YouTube channel video list to JSON..."
	cd backend && python -c "from scripts.common.list_videos_yt_dlp import YtDlpVideoLister; from pathlib import Path; lister = YtDlpVideoLister(); lister.dump_channel_json('$(or $(YOUTUBE_CHANNEL_URL),https://www.youtube.com/@anthonychaffeemd)', Path('data/videos.json'))"

list-youtube-api:
	@echo "Listing videos using YouTube Data API..."
	cd backend && python scripts/common/list_videos_api.py "$(or $(YOUTUBE_CHANNEL_URL),https://www.youtube.com/@anthonychaffeemd)" --limit 50

# Backfill commands
backfill-youtube:
	@echo "Backfilling from pre-dumped JSON..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source yt-dlp --from-json data/videos.json --concurrency 4 --newest-first

backfill-youtube-api:
	@echo "Backfilling using YouTube Data API..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source api --concurrency 4 --newest-first

# Test and validation commands
test-ingestion:
	@echo "Testing ingestion pipeline (dry run)..."
	cd backend && python scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 5 --dry-run

validate-transcripts:
	@echo "Validating transcript fetching..."
	cd backend && python scripts/common/transcript_fetch.py dQw4w9WgXcQ

ingestion-stats:
	@echo "Showing ingestion statistics..."
	cd backend && python scripts/common/database_upsert.py --stats

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
	@echo "  ingest-youtube   - Run YouTube transcript ingestion"
	@echo "  ingest-zoom      - Run Zoom transcript ingestion"
	@echo "  db-up           - Start database only"
	@echo "  db-down         - Stop database"
	@echo "  db-reset        - Reset database (delete all data)"
	@echo "  stop            - Stop all services"
	@echo "  clean           - Clean up containers and volumes"
	@echo "  logs            - Show container logs"
	@echo "  help            - Show this help message"
