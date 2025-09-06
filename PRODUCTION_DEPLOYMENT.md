# Production Deployment Guide

This guide provides step-by-step instructions for deploying the Ask Dr. Chaffee application to production with hundreds of videos.

> **Note for Windows 11 Users**: This guide includes both Makefile commands (for Linux/macOS) and PowerShell commands (for Windows 11). Look for the **Windows 11** sections for PowerShell-specific instructions.

## Table of Contents
- [Prerequisites](#prerequisites)
- [System Requirements](#system-requirements)
- [Database Setup](#database-setup)
- [Environment Configuration](#environment-configuration)
- [Large-Scale Ingestion](#large-scale-ingestion)
- [Monitoring and Maintenance](#monitoring-and-maintenance)
- [Frontend Deployment](#frontend-deployment)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before deploying to production, ensure you have:

1. **YouTube Data API Key**: Get one from [Google Cloud Console](https://console.cloud.google.com/)
2. **PostgreSQL Database**: Version 15+ with pgvector extension
3. **FFmpeg**: Installed for audio processing (required for Whisper transcription)
4. **Python 3.8+**: For backend ingestion scripts
5. **Node.js 20.x**: For frontend application

## System Requirements

For processing hundreds of videos, we recommend:

- **CPU**: 4+ cores
- **RAM**: 8GB+ (16GB recommended)
- **Storage**: 10GB base + ~1GB per 1000 videos
- **Database**: PostgreSQL 15+ with pgvector
- **Network**: Stable internet connection

## Database Setup

### Option 1: Self-hosted PostgreSQL

#### Linux/macOS

1. Install PostgreSQL 15+ with pgvector extension:

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql-15 postgresql-contrib-15

# Install pgvector
sudo apt install postgresql-server-dev-15 build-essential git
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

#### Windows 11

1. Install PostgreSQL 15+ using the installer from [postgresql.org](https://www.postgresql.org/download/windows/)

2. Install pgvector extension:

```powershell
# Download and extract pgvector
Invoke-WebRequest -Uri "https://github.com/pgvector/pgvector/archive/refs/tags/v0.5.0.zip" -OutFile "pgvector.zip"
Expand-Archive -Path "pgvector.zip" -DestinationPath "."
cd pgvector-0.5.0

# Build with Visual Studio Developer Command Prompt (requires Visual Studio installation)
# Run these commands in the Developer Command Prompt
# nmake /f Makefile.win
# nmake /f Makefile.win install

# Alternatively, use pre-built binaries from https://github.com/pgvector/pgvector/releases
```

2. Create database and user:

```sql
CREATE DATABASE askdrchaffee;
CREATE USER askdrchaffee WITH PASSWORD 'strong-password';
GRANT ALL PRIVILEGES ON DATABASE askdrchaffee TO askdrchaffee;
```

3. Enable pgvector extension:

```sql
\c askdrchaffee
CREATE EXTENSION vector;
```

4. Apply schema:

```bash
psql -U askdrchaffee -d askdrchaffee -f db/schema.sql
```

### Option 2: Managed PostgreSQL (Recommended)

1. Create a PostgreSQL 15+ instance on:
   - [Supabase](https://supabase.com/) (includes pgvector)
   - [Neon](https://neon.tech/) (supports pgvector)
   - [AWS RDS](https://aws.amazon.com/rds/postgresql/) (requires manual pgvector setup)

2. Enable pgvector extension through your provider's interface

3. Apply schema:

```bash
psql -U your_user -h your_host -d your_database -f db/schema.sql
```

## Environment Configuration

1. Create production `.env` file:

```bash
cp .env.example .env.production
```

2. Configure the following variables:

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/askdrchaffee

# YouTube Configuration (REQUIRED)
YOUTUBE_CHANNEL_URL=https://www.youtube.com/@anthonychaffeemd
YOUTUBE_API_KEY=your_api_key_here

# Features
RERANK_ENABLED=true
SEED=false

# Whisper Configuration
WHISPER_MODEL=small.en
MAX_AUDIO_DURATION=3600

# Processing
CHUNK_DURATION_SECONDS=45
DEFAULT_CONCURRENCY=4
SKIP_SHORTS=true
NEWEST_FIRST=true

# Monitoring (Optional)
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=your_smtp_password
ALERT_FROM_EMAIL=alerts@example.com
ALERT_TO_EMAIL=your@email.com
```

## Large-Scale Ingestion

### Step 1: Optimize Database

Before starting large-scale ingestion, optimize the database:

#### Linux/macOS
```bash
make db-optimize
```

#### Windows 11
```powershell
# First load the PowerShell functions
. .\scripts.ps1

# Then run the optimization
Optimize-Database
```

### Step 2: Test with a Small Batch

Run a test with a small batch to verify everything works:

#### Linux/macOS
```bash
make test-large-batch
```

#### Windows 11
```powershell
# Load the PowerShell functions if not already loaded
. .\scripts.ps1

# Run the test batch
Test-LargeBatch
```

Review the test results to ensure:
- Successful video processing
- Good transcript availability
- Acceptable processing speed

### Step 3: Run Full Batch Ingestion

For production ingestion of hundreds of videos:

#### Linux/macOS
```bash
make batch-ingest
```

#### Windows 11
```powershell
# Load the PowerShell functions if not already loaded
. .\scripts.ps1

# Start batch ingestion
Start-BatchIngestion -BatchSize 50 -BatchDelay 60 -Concurrency 4 -SkipShorts
```

This will:
- Process videos in batches of 50
- Automatically handle errors and retries
- Create checkpoints for resumability
- Respect YouTube API quotas

To monitor progress:

#### Linux/macOS
```bash
make batch-status
make ingest-status
```

#### Windows 11
```powershell
# Check batch status
Get-BatchStatus

# Check overall ingestion status
Get-IngestionStatus
```

If the process is interrupted, resume with:

#### Linux/macOS
```bash
make batch-resume
```

#### Windows 11
```powershell
Resume-BatchIngestion -BatchSize 50 -BatchDelay 60 -Concurrency 4 -SkipShorts
```

### Step 4: Monitor Ingestion

During the ingestion process, monitor:

#### Linux/macOS
```bash
# Check overall status
make monitor-report

# Check API quota usage
make monitor-quota

# View detailed metrics
make monitor-metrics
```

#### Windows 11
```powershell
# Check overall status
Get-MonitoringReport

# Check API quota usage
Get-ApiQuota

# View detailed metrics
Get-IngestionMetrics
```

## Monitoring and Maintenance

### Regular Maintenance

Schedule these tasks to run regularly:

1. **Database Optimization** (weekly):

#### Linux/macOS
```bash
make db-vacuum
make db-reindex
```

#### Windows 11
```powershell
Vacuum-Database
Reindex-Database
```

2. **Incremental Updates** (daily):

#### Linux/macOS
```bash
make sync-youtube
```

#### Windows 11
```powershell
Start-YouTubeSync
```

3. **Health Checks** (daily):

#### Linux/macOS
```bash
make monitor-health
make monitor-alerts
```

#### Windows 11
```powershell
Get-DatabaseHealth
Get-MonitoringAlerts
```

### Monitoring Dashboard

For a comprehensive monitoring dashboard, run:

#### Linux/macOS
```bash
make monitor-report
```

#### Windows 11
```powershell
Get-MonitoringReport
```

This generates a detailed report with:
- Database health
- Ingestion metrics
- API quota usage
- Error patterns

## Frontend Deployment

### Option 1: Vercel (Recommended)

1. Connect your GitHub repository to Vercel
2. Set environment variables:
   - `DATABASE_URL`: Your production database URL
   - `RERANK_ENABLED`: Set to `true` for better search results
3. Deploy from the Vercel dashboard

### Option 2: Self-hosted

1. Build the frontend:

```bash
cd frontend
npm install
npm run build
```

2. Serve with a production-ready server:

```bash
# Using PM2
npm install -g pm2
pm2 start npm --name "ask-dr-chaffee" -- start
```

## Troubleshooting

### Common Issues

#### 1. YouTube API Quota Exceeded

**Symptoms**: Errors with "quota exceeded" messages

**Solution**:
- Reduce batch size and concurrency
- Add delay between batches
- Consider using multiple API keys

#### 2. Slow Processing

**Symptoms**: Processing fewer than 10 videos per hour

**Solution**:
- Increase concurrency (up to 8)
- Optimize database with `make db-optimize`
- Use a more powerful server

#### 3. High Error Rate

**Symptoms**: More than 10% of videos failing

**Solution**:
- Check error patterns with `make ingest-errors`
- Ensure FFmpeg is properly installed
- Verify YouTube API key permissions

#### 4. Database Performance Issues

**Symptoms**: Slow queries, high CPU usage

**Solution**:
- Run `make db-vacuum` and `make db-reindex`
- Increase database resources
- Optimize indexes for your query patterns

## Production Checklist

Before going live:

- [ ] Database is properly configured with pgvector
- [ ] Environment variables are set correctly
- [ ] Full batch ingestion has completed successfully
- [ ] Frontend is deployed and connected to the database
- [ ] Monitoring is set up
- [ ] Regular maintenance tasks are scheduled

## Windows 11 Quick Reference

To use the PowerShell functions:

1. Load the functions:
```powershell
. .\scripts.ps1
```

2. Start the database:
```powershell
Start-Database
```

3. Run batch ingestion:
```powershell
Start-BatchIngestion
```

4. Monitor progress:
```powershell
Get-BatchStatus
Get-IngestionStatus
Get-MonitoringReport
```

5. For a list of all available commands:
```powershell
Show-Help
```

## Support

For issues or questions, please open an issue on the GitHub repository.
