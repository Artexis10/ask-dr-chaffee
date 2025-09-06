# Ask Dr. Chaffee - PowerShell Scripts for Windows 11
# This script provides PowerShell equivalents for all Makefile commands

# Helper function to ensure .env file exists
function Ensure-EnvFile {
    if (-not (Test-Path .env)) {
        Write-Host "Creating .env file from .env.example..."
        Copy-Item .env.example .env
        Write-Host "Please edit .env with your configuration"
    }
}

# Development commands
function Start-Development {
    Ensure-EnvFile
    Write-Host "Starting development environment..."
    docker-compose up -d
    Write-Host "Database is starting up..."
    Write-Host "Frontend: cd frontend; npm run dev"
    Write-Host "Backend ready for ingestion scripts"
}

# Database management
function Start-Database {
    Write-Host "Starting PostgreSQL database..."
    docker-compose up -d postgres
}

function Stop-Database {
    Write-Host "Stopping PostgreSQL database..."
    docker-compose down
}

function Reset-Database {
    Write-Host "Resetting database (this will delete all data)..."
    docker-compose down -v
    docker-compose up -d postgres
}

# Installation commands
function Install-Frontend {
    Write-Host "Installing frontend dependencies..."
    Set-Location frontend
    npm install
    Set-Location ..
}

function Install-Backend {
    Write-Host "Installing backend dependencies..."
    Set-Location backend
    pip install -r requirements.txt
    Set-Location ..
}

function Install-All {
    Install-Frontend
    Install-Backend
}

# YouTube ingestion commands
function Start-YouTubeIngestion {
    param (
        [int]$Limit = 0,
        [switch]$Newest = $true,
        [switch]$SkipShorts = $true,
        [int]$Concurrency = 4,
        [string]$Source = "api"
    )

    $limitArg = if ($Limit -gt 0) { "--limit $Limit" } else { "" }
    $newestArg = if ($Newest) { "--newest-first" } else { "" }
    $shortsArg = if ($SkipShorts) { "--skip-shorts" } else { "" }

    Write-Host "Starting YouTube ingestion using $Source source..."
    Set-Location backend
    python scripts/ingest_youtube_enhanced.py --source $Source --concurrency $Concurrency $newestArg $shortsArg $limitArg
    Set-Location ..
}

function Start-YouTubeSeed {
    Write-Host "Seeding with 10 recent videos..."
    Start-YouTubeIngestion -Limit 10 -Newest -SkipShorts -Source "api"
}

function Start-YouTubeSync {
    Write-Host "Syncing 25 recent YouTube videos..."
    Start-YouTubeIngestion -Limit 25 -Newest -SkipShorts -Source "api" -Concurrency 3
}

function Start-YouTubeBackfill {
    Write-Host "Starting full YouTube channel backfill using API..."
    Start-YouTubeIngestion -Newest -SkipShorts -Source "api" -Concurrency 4
}

function Start-YouTubeBackfillFallback {
    Write-Host "Backfilling using yt-dlp fallback..."
    
    # Create data directory if it doesn't exist
    if (-not (Test-Path backend\data)) {
        New-Item -ItemType Directory -Path backend\data | Out-Null
    }
    
    # Get channel URL from env or use default
    $channelUrl = $env:YOUTUBE_CHANNEL_URL
    if (-not $channelUrl) {
        $channelUrl = "https://www.youtube.com/@anthonychaffeemd"
    }
    
    # Dump video list to JSON
    yt-dlp --flat-playlist -J "$channelUrl/videos" > backend\data\videos.json
    
    # Process videos from JSON
    Set-Location backend
    python scripts/ingest_youtube_enhanced.py --source yt-dlp --from-json data/videos.json --concurrency 4 --newest-first --skip-shorts
    Set-Location ..
}

# Batch processing commands
function Start-BatchIngestion {
    param (
        [int]$BatchSize = 50,
        [int]$BatchDelay = 60,
        [int]$Concurrency = 4,
        [switch]$SkipShorts = $true
    )

    $shortsArg = if ($SkipShorts) { "--skip-shorts" } else { "" }
    
    Write-Host "Starting batch ingestion of all videos..."
    Set-Location backend
    python scripts/batch_ingestion.py --batch-size $BatchSize --batch-delay $BatchDelay --concurrency $Concurrency $shortsArg
    Set-Location ..
}

function Resume-BatchIngestion {
    param (
        [int]$BatchSize = 50,
        [int]$BatchDelay = 60,
        [int]$Concurrency = 4,
        [switch]$SkipShorts = $true
    )

    $shortsArg = if ($SkipShorts) { "--skip-shorts" } else { "" }
    
    Write-Host "Resuming batch ingestion with retry of failed videos..."
    Set-Location backend
    python scripts/batch_ingestion.py --retry-failed --batch-size $BatchSize --batch-delay $BatchDelay --concurrency $Concurrency $shortsArg
    Set-Location ..
}

function Get-BatchStatus {
    Write-Host "=== BATCH INGESTION STATUS ==="
    if (Test-Path backend\ingestion_checkpoint.json) {
        Get-Content backend\ingestion_checkpoint.json
    } else {
        Write-Host "No checkpoint file found"
    }
}

# Status monitoring and debugging
function Get-IngestionStatus {
    Write-Host "=== INGESTION STATUS REPORT ==="
    Set-Location backend
    python -c "from scripts.common.database_upsert import DatabaseUpserter; import os; db = DatabaseUpserter(os.getenv('DATABASE_URL')); stats = db.get_ingestion_stats(); print(f""Total videos: {stats['total_videos']}""); print(f""Total sources: {stats['total_sources']}""); print(f""Total chunks: {stats['total_chunks']}""); print(f""\nStatus breakdown:""); [print(f""  {k}: {v}"") for k, v in stats['status_counts'].items()]; print(f""\nTop errors:"") if stats['error_summary'] else None; [print(f""  {k}: {v}"") for k, v in stats['error_summary'].items()]"
    Set-Location ..
}

function Get-IngestionErrors {
    Write-Host "=== INGESTION ERRORS ==="
    Set-Location backend
    python -c "from scripts.common.database_upsert import DatabaseUpserter; import os; db = DatabaseUpserter(os.getenv('DATABASE_URL')); errors = db.get_videos_by_status('error', limit=20); [print(f""{video['video_id']}: {video.get('last_error', 'Unknown error')[:100]}..."") for video in errors]; print(f""\nShowing first 20 of {len(db.get_videos_by_status('error'))} total errors"")"
    Set-Location ..
}

function Get-IngestionQueue {
    Write-Host "=== PENDING QUEUE STATUS ==="
    Set-Location backend
    python -c "from scripts.common.database_upsert import DatabaseUpserter; import os; db = DatabaseUpserter(os.getenv('DATABASE_URL')); pending = len(db.get_videos_by_status('pending')); errors = len([v for v in db.get_videos_by_status('error') if v.get('retries', 0) < 3]); print(f""Pending: {pending}""); print(f""Retryable errors: {errors}""); print(f""Total in queue: {pending + errors}"")"
    Set-Location ..
}

# Database optimization commands
function Optimize-Database {
    Write-Host "=== OPTIMIZING DATABASE FOR PRODUCTION ==="
    Set-Location backend
    python scripts/common/db_optimization.py --all
    Set-Location ..
}

function Vacuum-Database {
    Write-Host "=== VACUUMING DATABASE TABLES ==="
    Set-Location backend
    python scripts/common/db_optimization.py --vacuum
    Set-Location ..
}

function Reindex-Database {
    Write-Host "=== REBUILDING DATABASE INDEXES ==="
    Set-Location backend
    python scripts/common/db_optimization.py --reindex --rebuild-vector-index
    Set-Location ..
}

# Monitoring commands
function Get-DatabaseHealth {
    Write-Host "=== CHECKING DATABASE HEALTH ==="
    Set-Location backend
    python scripts/common/monitoring.py --health-check
    Set-Location ..
}

function Get-IngestionMetrics {
    Write-Host "=== INGESTION METRICS ==="
    Set-Location backend
    python scripts/common/monitoring.py --metrics
    Set-Location ..
}

function Get-ApiQuota {
    Write-Host "=== CHECKING API QUOTA ==="
    Set-Location backend
    python scripts/common/monitoring.py --quota
    Set-Location ..
}

function Get-MonitoringReport {
    Write-Host "=== GENERATING FULL MONITORING REPORT ==="
    Set-Location backend
    python scripts/common/monitoring.py --report
    Set-Location ..
}

function Get-MonitoringAlerts {
    Write-Host "=== CHECKING FOR ALERT CONDITIONS ==="
    Set-Location backend
    python scripts/common/monitoring.py --alerts
    Set-Location ..
}

# Video listing commands
function Get-YouTubeVideos {
    Write-Host "Dumping YouTube channel video list to JSON..."
    
    # Create data directory if it doesn't exist
    if (-not (Test-Path backend\data)) {
        New-Item -ItemType Directory -Path backend\data | Out-Null
    }
    
    # Get channel URL from env or use default
    $channelUrl = $env:YOUTUBE_CHANNEL_URL
    if (-not $channelUrl) {
        $channelUrl = "https://www.youtube.com/@anthonychaffeemd"
    }
    
    yt-dlp --flat-playlist -J "$channelUrl/videos" > backend\data\videos.json
    Write-Host "Video list saved to backend/data/videos.json"
}

function Get-YouTubeVideosApi {
    param (
        [int]$Limit = 50
    )
    
    Write-Host "Listing videos using YouTube Data API..."
    
    # Get channel URL from env or use default
    $channelUrl = $env:YOUTUBE_CHANNEL_URL
    if (-not $channelUrl) {
        $channelUrl = "https://www.youtube.com/@anthonychaffeemd"
    }
    
    Set-Location backend
    python scripts/common/list_videos_api.py "$channelUrl" --limit $Limit
    Set-Location ..
}

# Test and validation commands
function Test-Ingestion {
    Write-Host "Testing ingestion pipeline (dry run)..."
    Set-Location backend
    python scripts/ingest_youtube_enhanced.py --source api --limit 5 --dry-run
    Set-Location ..
}

function Test-LargeBatch {
    Write-Host "Testing large-scale batch ingestion..."
    Set-Location backend
    python scripts/test_large_batch.py --test-size 20 --batch-size 5 --concurrency 4 --skip-shorts
    Set-Location ..
}

function Test-FullBatch {
    Write-Host "Testing full production-scale batch ingestion..."
    Set-Location backend
    python scripts/test_large_batch.py --test-size 100 --batch-size 20 --concurrency 4 --skip-shorts
    Set-Location ..
}

function Test-Transcripts {
    Write-Host "Validating transcript fetching..."
    Set-Location backend
    python scripts/common/transcript_fetch.py dQw4w9WgXcQ
    Set-Location ..
}

# Frontend development
function Start-Frontend {
    Write-Host "Starting Next.js frontend development server..."
    Set-Location frontend
    npm run dev
    Set-Location ..
}

# Utility commands
function Stop-Services {
    Write-Host "Stopping all services..."
    docker-compose down
}

function Clean-Environment {
    Write-Host "Cleaning up containers and volumes..."
    docker-compose down -v
    docker system prune -f
}

function Show-Logs {
    Write-Host "Showing container logs..."
    docker-compose logs -f
}

# Help function
function Show-Help {
    Write-Host @"
Available commands:

Development:
  Start-Development       - Start development environment
  Start-Frontend          - Start Next.js dev server

Database:
  Start-Database          - Start PostgreSQL
  Stop-Database           - Stop PostgreSQL
  Reset-Database          - Reset database (deletes data)

Installation:
  Install-All             - Install all dependencies
  Install-Frontend        - Install frontend dependencies
  Install-Backend         - Install backend dependencies

YouTube Ingestion:
  Start-YouTubeIngestion  - Run YouTube transcript ingestion (API default)
  Start-YouTubeSeed       - Quick seed with 10 videos
  Start-YouTubeSync       - Sync recent videos (25 latest)
  Start-YouTubeBackfill   - Full channel backfill using API

Batch Processing:
  Start-BatchIngestion    - Production batch ingestion of all videos
  Resume-BatchIngestion   - Resume batch ingestion with retry of failed videos
  Get-BatchStatus         - Show batch ingestion checkpoint status

Monitoring:
  Get-IngestionStatus     - Show ingestion statistics
  Get-IngestionErrors     - Show ingestion errors
  Get-IngestionQueue      - Check pending queue size
  Get-DatabaseHealth      - Check database health status
  Get-IngestionMetrics    - Show ingestion pipeline metrics
  Get-ApiQuota            - Check YouTube API quota usage
  Get-MonitoringReport    - Generate full monitoring report
  Get-MonitoringAlerts    - Check for alert conditions

Database Optimization:
  Optimize-Database       - Run all database optimizations for production
  Vacuum-Database         - Vacuum database tables to reclaim space
  Reindex-Database        - Rebuild database indexes for performance

Testing:
  Test-Ingestion          - Test ingestion pipeline (dry run)
  Test-LargeBatch         - Test ingestion with 20 videos
  Test-FullBatch          - Test ingestion with 100 videos
  Test-Transcripts        - Test transcript fetching

Utility:
  Stop-Services           - Stop all services
  Clean-Environment       - Clean up containers and volumes
  Show-Logs               - Show container logs
  Show-Help               - Show this help message

Example usage:
  . .\scripts.ps1         # Load all functions
  Start-Database          # Start the database
  Start-YouTubeSeed       # Ingest 10 videos
  Get-IngestionStatus     # Check status
"@
}

# Export all functions
Export-ModuleMember -Function *

# Instructions for use
Write-Host @"
Ask Dr. Chaffee - PowerShell Scripts

To use these functions, first load the script:
  . .\scripts.ps1

Then call any function, for example:
  Start-Database
  Start-YouTubeSeed
  Get-IngestionStatus

For a list of all available commands:
  Show-Help
"@
