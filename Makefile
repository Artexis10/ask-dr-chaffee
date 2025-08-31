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

# Ingestion commands
ingest-youtube:
	cd backend && python scripts/ingest_youtube.py

ingest-youtube-seed:
	@echo "Running YouTube ingestion in seed mode (first 10 videos)..."
	cd backend && SEED=1 python scripts/ingest_youtube.py

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
