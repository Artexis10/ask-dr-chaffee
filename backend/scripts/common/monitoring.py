#!/usr/bin/env python3
"""
Monitoring and logging utilities for production-scale ingestion.

This module provides tools for:
- Structured logging with rotation
- Performance metrics collection
- Health checks
- Alerting capabilities
"""

import os
import sys
import time
import json
import logging
import logging.handlers
import smtplib
import socket
import traceback
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from email.message import EmailMessage
from pathlib import Path
from functools import wraps

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure base logger
logger = logging.getLogger("ingestion_monitor")

class IngestionMonitor:
    """Monitor ingestion pipeline health and performance"""
    
    def __init__(
        self, 
        db_url: str,
        log_dir: str = "logs",
        log_level: int = logging.INFO,
        enable_email_alerts: bool = False,
        email_config: Optional[Dict[str, str]] = None
    ):
        self.db_url = db_url
        self.log_dir = log_dir
        self.log_level = log_level
        self.enable_email_alerts = enable_email_alerts
        self.email_config = email_config or {}
        self._connection = None
        
        # Set up logging
        self.setup_logging()
    
    def setup_logging(self):
        """Configure structured logging with rotation"""
        # Create logs directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_format = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        console_handler.setFormatter(console_format)
        root_logger.addHandler(console_handler)
        
        # File handler with rotation (10 MB per file, keep 10 files)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(self.log_dir, "ingestion.log"),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=10,
            encoding="utf-8"
        )
        file_handler.setLevel(self.log_level)
        file_format = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)
        
        # JSON structured log for machine parsing
        json_handler = logging.handlers.RotatingFileHandler(
            os.path.join(self.log_dir, "ingestion_structured.json"),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=10,
            encoding="utf-8"
        )
        json_handler.setLevel(self.log_level)
        
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                    "process": record.process,
                    "thread": record.thread,
                    "hostname": socket.gethostname()
                }
                
                # Add exception info if available
                if record.exc_info:
                    log_data["exception"] = {
                        "type": record.exc_info[0].__name__,
                        "message": str(record.exc_info[1]),
                        "traceback": traceback.format_exception(*record.exc_info)
                    }
                
                # Add extra attributes
                if hasattr(record, "extra"):
                    log_data.update(record.extra)
                
                return json.dumps(log_data)
        
        json_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(json_handler)
        
        logger.info(f"Logging configured: console, file rotation, and JSON structured logs in {self.log_dir}")
    
    def get_connection(self):
        """Get database connection with lazy initialization"""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(self.db_url)
            self._connection.autocommit = True  # For monitoring queries
        return self._connection
    
    def close_connection(self):
        """Close database connection"""
        if self._connection and not self._connection.closed:
            self._connection.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection()
    
    def log_with_context(self, level: int, message: str, **context):
        """Log message with additional context data"""
        extra = {"extra": context}
        logger.log(level, message, extra=extra)
    
    def send_alert(self, subject: str, message: str) -> bool:
        """Send email alert if configured"""
        if not self.enable_email_alerts:
            logger.info(f"Email alerts disabled. Would have sent: {subject}")
            return False
        
        if not all(k in self.email_config for k in ["smtp_server", "smtp_port", "from_email", "to_email"]):
            logger.error("Email configuration incomplete, cannot send alert")
            return False
        
        try:
            msg = EmailMessage()
            msg.set_content(message)
            msg["Subject"] = f"[Ask Dr. Chaffee] {subject}"
            msg["From"] = self.email_config["from_email"]
            msg["To"] = self.email_config["to_email"]
            
            with smtplib.SMTP(self.email_config["smtp_server"], int(self.email_config["smtp_port"])) as server:
                if self.email_config.get("use_tls", False):
                    server.starttls()
                
                if "smtp_user" in self.email_config and "smtp_password" in self.email_config:
                    server.login(self.email_config["smtp_user"], self.email_config["smtp_password"])
                
                server.send_message(msg)
            
            logger.info(f"Alert email sent: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False
    
    def check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and health"""
        start_time = time.time()
        result = {
            "status": "unknown",
            "response_time_ms": 0,
            "details": {}
        }
        
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                # Check basic connectivity
                cur.execute("SELECT 1")
                
                # Check PostgreSQL version
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
                
                # Check pgvector extension
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                pgvector_version = cur.fetchone()[0] if cur.rowcount > 0 else "not installed"
                
                # Check table counts
                cur.execute("SELECT COUNT(*) FROM sources")
                sources_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM chunks")
                chunks_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM ingest_state")
                ingest_state_count = cur.fetchone()[0]
                
                # Check recent errors
                cur.execute(
                    "SELECT COUNT(*) FROM ingest_state WHERE status = 'error' AND updated_at > NOW() - INTERVAL '24 hours'"
                )
                recent_errors = cur.fetchone()[0]
                
                # Check database size
                cur.execute("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as db_size,
                           pg_database_size(current_database()) as db_size_bytes
                """)
                db_size_info = cur.fetchone()
                
                result["status"] = "healthy"
                result["details"] = {
                    "version": version,
                    "pgvector_version": pgvector_version,
                    "sources_count": sources_count,
                    "chunks_count": chunks_count,
                    "ingest_state_count": ingest_state_count,
                    "recent_errors_24h": recent_errors,
                    "database_size": db_size_info[0],
                    "database_size_bytes": db_size_info[1]
                }
                
        except Exception as e:
            result["status"] = "unhealthy"
            result["details"] = {
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            logger.error(f"Database health check failed: {e}")
        
        result["response_time_ms"] = int((time.time() - start_time) * 1000)
        return result
    
    def get_ingestion_metrics(self) -> Dict[str, Any]:
        """Get detailed ingestion pipeline metrics"""
        try:
            conn = self.get_connection()
            metrics = {}
            
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Status breakdown
                cur.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM ingest_state 
                    GROUP BY status 
                    ORDER BY count DESC
                """)
                metrics["status_counts"] = {row["status"]: row["count"] for row in cur.fetchall()}
                
                # Processing rates
                cur.execute("""
                    SELECT 
                        COUNT(*) as videos_processed,
                        SUM(chunk_count) as chunks_created,
                        MIN(updated_at) as first_video,
                        MAX(updated_at) as last_video
                    FROM ingest_state 
                    WHERE status = 'done'
                """)
                processing_stats = cur.fetchone()
                
                if processing_stats and processing_stats["first_video"] and processing_stats["last_video"]:
                    first_video = processing_stats["first_video"]
                    last_video = processing_stats["last_video"]
                    duration_hours = (last_video - first_video).total_seconds() / 3600
                    
                    if duration_hours > 0:
                        videos_per_hour = processing_stats["videos_processed"] / duration_hours
                        chunks_per_hour = processing_stats["chunks_created"] / duration_hours if processing_stats["chunks_created"] else 0
                        
                        metrics["processing_rates"] = {
                            "videos_per_hour": round(videos_per_hour, 2),
                            "chunks_per_hour": round(chunks_per_hour, 2),
                            "duration_hours": round(duration_hours, 2)
                        }
                
                # Recent processing (last 24 hours)
                cur.execute("""
                    SELECT 
                        COUNT(*) as videos_processed_24h,
                        SUM(chunk_count) as chunks_created_24h
                    FROM ingest_state 
                    WHERE status = 'done' AND updated_at > NOW() - INTERVAL '24 hours'
                """)
                recent_stats = cur.fetchone()
                metrics["recent_24h"] = {
                    "videos_processed": recent_stats["videos_processed_24h"],
                    "chunks_created": recent_stats["chunks_created_24h"] or 0
                }
                
                # Error analysis
                cur.execute("""
                    SELECT last_error, COUNT(*) as count
                    FROM ingest_state 
                    WHERE status = 'error' AND last_error IS NOT NULL
                    GROUP BY last_error
                    ORDER BY count DESC
                    LIMIT 5
                """)
                metrics["top_errors"] = {row["last_error"]: row["count"] for row in cur.fetchall()}
                
                # Transcript source breakdown
                cur.execute("""
                    SELECT 
                        SUM(CASE WHEN has_yt_transcript THEN 1 ELSE 0 END) as youtube_transcripts,
                        SUM(CASE WHEN has_whisper THEN 1 ELSE 0 END) as whisper_transcripts,
                        COUNT(*) as total
                    FROM ingest_state 
                    WHERE status = 'done'
                """)
                transcript_stats = cur.fetchone()
                if transcript_stats and transcript_stats["total"] > 0:
                    metrics["transcript_sources"] = {
                        "youtube_transcripts": transcript_stats["youtube_transcripts"],
                        "whisper_transcripts": transcript_stats["whisper_transcripts"],
                        "youtube_percent": round(100 * transcript_stats["youtube_transcripts"] / transcript_stats["total"], 1),
                        "whisper_percent": round(100 * transcript_stats["whisper_transcripts"] / transcript_stats["total"], 1)
                    }
                
                # Video duration statistics
                cur.execute("""
                    SELECT 
                        MIN(duration_s) as min_duration,
                        MAX(duration_s) as max_duration,
                        AVG(duration_s) as avg_duration,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_s) as median_duration
                    FROM ingest_state 
                    WHERE status = 'done' AND duration_s IS NOT NULL
                """)
                duration_stats = cur.fetchone()
                if duration_stats and duration_stats["avg_duration"]:
                    metrics["duration_stats"] = {
                        "min_duration_s": duration_stats["min_duration"],
                        "max_duration_s": duration_stats["max_duration"],
                        "avg_duration_s": round(duration_stats["avg_duration"], 1),
                        "median_duration_s": round(duration_stats["median_duration"], 1),
                        "min_duration_formatted": self._format_duration(duration_stats["min_duration"]),
                        "max_duration_formatted": self._format_duration(duration_stats["max_duration"]),
                        "avg_duration_formatted": self._format_duration(duration_stats["avg_duration"]),
                        "median_duration_formatted": self._format_duration(duration_stats["median_duration"])
                    }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get ingestion metrics: {e}")
            return {"error": str(e)}
    
    def _format_duration(self, seconds: Optional[float]) -> str:
        """Format seconds as HH:MM:SS"""
        if seconds is None:
            return "00:00:00"
        
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def check_api_quota(self) -> Dict[str, Any]:
        """Check YouTube API quota usage based on recent activity"""
        try:
            # Estimate quota usage based on recent API calls
            # This is an approximation since we don't have direct access to quota usage
            conn = self.get_connection()
            
            with conn.cursor() as cur:
                # Count videos processed in last 24 hours
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM ingest_state 
                    WHERE updated_at > NOW() - INTERVAL '24 hours'
                """)
                videos_24h = cur.fetchone()[0]
                
                # Estimate quota usage
                # List operation: ~1 unit per video
                # Video details: ~1 unit per video
                # Caption download: ~50 units per video (if available)
                # Assume 80% of videos have captions
                list_quota = videos_24h * 1
                details_quota = videos_24h * 1
                captions_quota = videos_24h * 0.8 * 50
                
                total_estimated = list_quota + details_quota + captions_quota
                
                # YouTube quota is 10,000 units per day by default
                quota_limit = 10000
                quota_percent = (total_estimated / quota_limit) * 100
                
                return {
                    "estimated_usage_24h": round(total_estimated),
                    "quota_limit": quota_limit,
                    "quota_percent": round(quota_percent, 1),
                    "videos_processed_24h": videos_24h,
                    "status": "warning" if quota_percent > 80 else "ok"
                }
                
        except Exception as e:
            logger.error(f"Failed to check API quota: {e}")
            return {"error": str(e), "status": "error"}
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive monitoring report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "hostname": socket.gethostname(),
            "database_health": self.check_database_health(),
            "ingestion_metrics": self.get_ingestion_metrics(),
            "api_quota": self.check_api_quota()
        }
        
        # Add overall status
        if report["database_health"]["status"] == "healthy" and report["api_quota"]["status"] != "error":
            report["status"] = "healthy"
        else:
            report["status"] = "unhealthy"
            
        return report
    
    def save_report(self, report: Dict[str, Any], filename: Optional[str] = None):
        """Save monitoring report to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.log_dir, f"report_{timestamp}.json")
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Monitoring report saved to {filename}")
        return filename
    
    def check_for_alerts(self, report: Dict[str, Any]):
        """Check monitoring report for conditions that require alerts"""
        alerts = []
        
        # Check database health
        if report["database_health"]["status"] != "healthy":
            alerts.append({
                "level": "critical",
                "subject": "Database Health Check Failed",
                "message": f"Database is unhealthy: {report['database_health']['details'].get('error', 'Unknown error')}"
            })
        
        # Check API quota
        if report["api_quota"]["status"] == "warning":
            quota_percent = report["api_quota"]["quota_percent"]
            alerts.append({
                "level": "warning",
                "subject": f"YouTube API Quota at {quota_percent}%",
                "message": f"YouTube API quota usage is high ({quota_percent}% of daily limit). Consider reducing ingestion rate."
            })
        elif report["api_quota"]["status"] == "error":
            alerts.append({
                "level": "critical",
                "subject": "YouTube API Quota Check Failed",
                "message": f"Failed to check API quota: {report['api_quota'].get('error', 'Unknown error')}"
            })
        
        # Check error rate
        if "recent_24h" in report["ingestion_metrics"]:
            recent_errors = report["ingestion_metrics"].get("status_counts", {}).get("error", 0)
            recent_total = sum(report["ingestion_metrics"].get("status_counts", {}).values())
            
            if recent_total > 0 and recent_errors / recent_total > 0.2:  # More than 20% errors
                alerts.append({
                    "level": "warning",
                    "subject": "High Ingestion Error Rate",
                    "message": f"Ingestion error rate is {round(100 * recent_errors / recent_total, 1)}% ({recent_errors}/{recent_total} videos)"
                })
        
        # Send alerts
        for alert in alerts:
            if alert["level"] == "critical" or self.enable_email_alerts:
                self.send_alert(alert["subject"], alert["message"])
            
            self.log_with_context(
                logging.ERROR if alert["level"] == "critical" else logging.WARNING,
                f"ALERT: {alert['subject']} - {alert['message']}",
                alert_level=alert["level"]
            )
        
        return alerts

def timing_decorator(func):
    """Decorator to measure and log function execution time"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        
        logger.debug(f"Function {func.__name__} took {duration_ms:.2f}ms to execute")
        return result
    return wrapper

def main():
    """CLI for monitoring tools"""
    parser = argparse.ArgumentParser(description='Ingestion pipeline monitoring tools')
    parser.add_argument('--db-url', help='Database URL (or use DATABASE_URL env)')
    parser.add_argument('--log-dir', default='logs', help='Log directory (default: logs)')
    parser.add_argument('--report', action='store_true', help='Generate monitoring report')
    parser.add_argument('--health-check', action='store_true', help='Run database health check')
    parser.add_argument('--metrics', action='store_true', help='Show ingestion metrics')
    parser.add_argument('--quota', action='store_true', help='Check API quota usage')
    parser.add_argument('--alerts', action='store_true', help='Check for alert conditions')
    parser.add_argument('--email-alerts', action='store_true', help='Enable email alerts')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.verbose else logging.INFO
    
    db_url = args.db_url or os.getenv('DATABASE_URL')
    if not db_url:
        print("Database URL required (--db-url or DATABASE_URL env)")
        sys.exit(1)
    
    # Email configuration from environment
    email_config = {
        "smtp_server": os.getenv("SMTP_SERVER"),
        "smtp_port": os.getenv("SMTP_PORT", "587"),
        "smtp_user": os.getenv("SMTP_USER"),
        "smtp_password": os.getenv("SMTP_PASSWORD"),
        "from_email": os.getenv("ALERT_FROM_EMAIL"),
        "to_email": os.getenv("ALERT_TO_EMAIL"),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    }
    
    monitor = IngestionMonitor(
        db_url=db_url,
        log_dir=args.log_dir,
        log_level=log_level,
        enable_email_alerts=args.email_alerts,
        email_config=email_config
    )
    
    try:
        if args.health_check:
            health = monitor.check_database_health()
            print(f"Database health: {health['status']}")
            print(f"Response time: {health['response_time_ms']}ms")
            if health['status'] == 'healthy':
                print(f"PostgreSQL version: {health['details']['version']}")
                print(f"pgvector version: {health['details']['pgvector_version']}")
                print(f"Sources: {health['details']['sources_count']}")
                print(f"Chunks: {health['details']['chunks_count']}")
                print(f"Database size: {health['details']['database_size']}")
            else:
                print(f"Error: {health['details'].get('error', 'Unknown error')}")
        
        if args.metrics:
            metrics = monitor.get_ingestion_metrics()
            print("\nIngestion Metrics:")
            
            if "status_counts" in metrics:
                print("\nStatus breakdown:")
                for status, count in metrics["status_counts"].items():
                    print(f"  {status}: {count}")
            
            if "processing_rates" in metrics:
                print("\nProcessing rates:")
                rates = metrics["processing_rates"]
                print(f"  Videos per hour: {rates['videos_per_hour']}")
                print(f"  Chunks per hour: {rates['chunks_per_hour']}")
                print(f"  Total duration: {rates['duration_hours']} hours")
            
            if "recent_24h" in metrics:
                print("\nLast 24 hours:")
                print(f"  Videos processed: {metrics['recent_24h']['videos_processed']}")
                print(f"  Chunks created: {metrics['recent_24h']['chunks_created']}")
            
            if "transcript_sources" in metrics:
                print("\nTranscript sources:")
                ts = metrics["transcript_sources"]
                print(f"  YouTube API: {ts['youtube_transcripts']} ({ts['youtube_percent']}%)")
                print(f"  Whisper: {ts['whisper_transcripts']} ({ts['whisper_percent']}%)")
            
            if "duration_stats" in metrics:
                print("\nVideo durations:")
                ds = metrics["duration_stats"]
                print(f"  Average: {ds['avg_duration_formatted']} ({ds['avg_duration_s']}s)")
                print(f"  Median: {ds['median_duration_formatted']} ({ds['median_duration_s']}s)")
                print(f"  Range: {ds['min_duration_formatted']} - {ds['max_duration_formatted']}")
        
        if args.quota:
            quota = monitor.check_api_quota()
            print("\nYouTube API Quota:")
            if "error" not in quota:
                print(f"  Estimated usage (24h): {quota['estimated_usage_24h']} units")
                print(f"  Quota limit: {quota['quota_limit']} units")
                print(f"  Usage percent: {quota['quota_percent']}%")
                print(f"  Videos processed (24h): {quota['videos_processed_24h']}")
                print(f"  Status: {quota['status']}")
            else:
                print(f"  Error checking quota: {quota['error']}")
        
        if args.report or args.alerts:
            report = monitor.generate_report()
            
            if args.report:
                filename = monitor.save_report(report)
                print(f"\nFull report saved to: {filename}")
            
            if args.alerts:
                alerts = monitor.check_for_alerts(report)
                if alerts:
                    print("\nAlerts detected:")
                    for alert in alerts:
                        print(f"  [{alert['level'].upper()}] {alert['subject']}")
                        print(f"    {alert['message']}")
                else:
                    print("\nNo alerts detected")
        
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)
    finally:
        monitor.close_connection()

if __name__ == '__main__':
    main()
