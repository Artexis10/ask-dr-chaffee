#!/bin/bash
# Cron setup examples for hybrid YouTube ingestion
# Copy to your production server and customize as needed

# ==============================================
# PRODUCTION CRON CONFIGURATION EXAMPLES
# ==============================================

# Daily ingestion using cloud API (cost-optimized)
# Runs at 2 AM every day, processes new videos with $5 cost limit
# 0 2 * * * /path/to/venv/bin/python /path/to/ask-dr-chaffee/backend/scripts/cloud_daily_ingestion.py --max-cost 5.0 --limit 10 >> /var/log/youtube_ingestion.log 2>&1

# Hybrid auto-decision processing (smart routing)
# Runs at 3 AM every day, automatically chooses best processing method
# 0 3 * * * /path/to/venv/bin/python /path/to/ask-dr-chaffee/backend/scripts/hybrid_orchestrator.py --mode auto --limit 15 --max-cost 8.0 >> /var/log/youtube_hybrid.log 2>&1

# Weekly backlog processing notification (if you want reminders)
# Runs every Sunday at 6 AM to check for large backlogs
# 0 6 * * 0 /path/to/venv/bin/python /path/to/ask-dr-chaffee/backend/scripts/hybrid_orchestrator.py --dry-run --limit 100 | mail -s "Weekly Backlog Report" your-email@domain.com

# ==============================================
# ENVIRONMENT SETUP FOR CRON JOBS
# ==============================================

# Create environment file for cron jobs
# /etc/cron.d/youtube-ingestion-env
# DATABASE_URL="postgresql://username:password@localhost:5432/dbname"
# OPENAI_API_KEY="sk-your-api-key-here"
# YOUTUBE_API_KEY="your-youtube-api-key"

# ==============================================
# EXAMPLE PRODUCTION CRONTAB
# ==============================================
cat << 'EOF' > /tmp/youtube_ingestion_crontab
# YouTube Ingestion Cron Jobs
# Environment variables
DATABASE_URL=postgresql://username:password@localhost:5432/askdrchaffee
OPENAI_API_KEY=sk-your-openai-api-key
YOUTUBE_API_KEY=your-youtube-data-api-key
PATH=/usr/local/bin:/usr/bin:/bin

# Daily ingestion at 2 AM (cloud API, cost-effective)
0 2 * * * cd /path/to/ask-dr-chaffee && /path/to/venv/bin/python backend/scripts/cloud_daily_ingestion.py --max-cost 5.0 --limit 10 >> /var/log/youtube_daily.log 2>&1

# Backup hybrid processing at 4 AM (in case daily fails)
0 4 * * * cd /path/to/ask-dr-chaffee && /path/to/venv/bin/python backend/scripts/hybrid_orchestrator.py --mode cloud --limit 5 --max-cost 3.0 >> /var/log/youtube_backup.log 2>&1

# Weekly health check every Sunday at 6 AM
0 6 * * 0 cd /path/to/ask-dr-chaffee && /path/to/venv/bin/python check_ingestion_progress.py | mail -s "Weekly Ingestion Health Report" admin@yourdomain.com

# Log rotation to prevent disk space issues
0 0 * * 0 find /var/log/youtube_*.log -mtime +30 -delete
EOF

# ==============================================
# INSTALLATION COMMANDS
# ==============================================

# Install the crontab (customize paths first!)
# crontab /tmp/youtube_ingestion_crontab

# Create log directory
# sudo mkdir -p /var/log
# sudo chown $USER:$USER /var/log/youtube_*.log

# Test the cron commands manually first:
# cd /path/to/ask-dr-chaffee
# source venv/bin/activate
# python backend/scripts/cloud_daily_ingestion.py --dry-run --max-cost 5.0

# ==============================================
# MONITORING AND ALERTING
# ==============================================

# Example monitoring script to check if processing is working
cat << 'EOF' > /tmp/monitor_ingestion.py
#!/usr/bin/env python3
import os
import psycopg2
from datetime import datetime, timedelta

# Check if any videos were processed in the last 2 days
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cursor = conn.cursor()

cursor.execute("""
    SELECT COUNT(*) 
    FROM ingest_state 
    WHERE updated_at >= NOW() - INTERVAL '2 days' 
    AND status = 'done'
""")

recent_processed = cursor.fetchone()[0]

if recent_processed == 0:
    print("WARNING: No videos processed in the last 2 days!")
    exit(1)
else:
    print(f"OK: {recent_processed} videos processed recently")
    exit(0)
EOF

# Add monitoring to cron (sends email on failure)
# */30 * * * * /path/to/venv/bin/python /tmp/monitor_ingestion.py || echo "YouTube ingestion monitoring failed" | mail -s "ALERT: Ingestion Issue" admin@yourdomain.com

# ==============================================
# COST MONITORING
# ==============================================

# Monthly cost report (runs on 1st of each month)
cat << 'EOF' > /tmp/monthly_cost_report.py
#!/usr/bin/env python3
import os
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cursor = conn.cursor()

# Get last month's costs
cursor.execute("""
    SELECT 
        processing_method,
        COUNT(*) as videos,
        SUM(processing_cost_usd) as total_cost
    FROM ingest_state 
    WHERE updated_at >= DATE_TRUNC('month', NOW() - INTERVAL '1 month')
    AND updated_at < DATE_TRUNC('month', NOW())
    AND processing_cost_usd > 0
    GROUP BY processing_method
""")

results = cursor.fetchall()
total_cost = sum(row[2] for row in results)

print(f"Monthly Processing Cost Report")
print(f"=" * 40)
for method, videos, cost in results:
    print(f"{method}: {videos} videos, ${cost:.4f}")
print(f"Total: ${total_cost:.4f}")

if total_cost > 20.0:
    print("WARNING: Monthly costs exceeded $20!")
EOF

# Add monthly cost report to cron
# 0 9 1 * * /path/to/venv/bin/python /tmp/monthly_cost_report.py | mail -s "Monthly YouTube Processing Costs" admin@yourdomain.com

echo "Cron configuration examples created!"
echo "Customize paths and email addresses before installing."
