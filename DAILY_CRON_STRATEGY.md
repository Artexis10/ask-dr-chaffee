# 🔄 Daily Cron Job Strategy - Ask Dr. Chaffee Auto-Updates

## 🎯 **Production Goals**
- **Fresh Content**: Daily ingestion of new Dr. Chaffee videos
- **Minimal Resources**: Incremental updates vs full re-processing  
- **Zero Downtime**: Updates without disrupting search functionality
- **Auto Recovery**: Robust error handling and retry logic

## 📅 **Recommended Daily Schedule**

### **Option 1: Early Morning (3:00 AM)**
```bash
# Windows Task Scheduler or Linux cron
0 3 * * * cd C:\Users\hugoa\Desktop\ask-dr-chaffee && python backend\scripts\daily_sync.py
```

### **Option 2: Multiple Small Updates**
```bash
# Every 6 hours - smaller, faster updates
0 */6 * * * cd C:\Users\hugoa\Desktop\ask-dr-chaffee && python backend\scripts\incremental_sync.py
```

## 🔧 **Daily Sync Script Architecture**

Based on your existing robust pipeline, here's the optimal approach:

### **Phase 1: Incremental Discovery**
```python
# Use YouTube Data API with --since-published for efficiency
python backend\scripts\ingest_youtube_robust.py \
    --source api \
    --since-published $(date -d '2 days ago' '+%Y-%m-%d') \
    --limit 50 \
    --concurrency 2 \
    --skip-shorts
```

### **Phase 2: Fallback Processing** 
```python
# Process any videos that failed with yt-dlp + Whisper
python backend\scripts\ingest_youtube_robust.py \
    --source yt-dlp \
    --retry-failed \
    --concurrency 1
```

## ⚡ **Smart Incremental Strategy**

### **YouTube Data API Benefits** (from your existing setup):
- **ETag Caching**: Only fetches new content (quota efficient)
- **`--since-published`**: Process only videos from last N days
- **Rate Limiting**: Built-in exponential backoff
- **Cost Effective**: 10-50 videos/day vs 500+ initial backfill

### **Daily Parameters:**
```bash
# Typical daily run (assuming 1-3 new videos/day)
--limit 25                    # More than enough for daily uploads
--since-published 2025-01-21  # Last 24-48 hours  
--concurrency 2               # Light resource usage
--max-duration 7200          # Skip extra-long streams
```

## 📊 **Resource Management**

### **GPU Usage Optimization:**
```python
# Smart GPU scheduling
if is_business_hours():
    concurrency = 1          # Light usage during day
else:
    concurrency = 3          # Full power at night
```

### **Disk Space Management:**
```bash
# Auto-cleanup in daily script
find /tmp -name "*_raw.webm" -mtime +1 -delete
find /tmp -name "*_processed.wav" -mtime +1 -delete
```

## 🔍 **Monitoring & Alerting**

### **Success Metrics:**
- Videos processed per day
- Processing time per video
- Database growth rate  
- Search quality scores

### **Failure Detection:**
```python
# Daily health check
def daily_health_check():
    new_chunks_today = get_chunks_added_today()
    if new_chunks_today == 0:
        send_alert("No new content processed today")
    
    failed_videos = get_failed_videos_today() 
    if failed_videos > 5:
        send_alert(f"{failed_videos} videos failed processing")
```

## 📝 **Daily Sync Script Template**

```python
#!/usr/bin/env python3
"""
Daily sync script for Ask Dr. Chaffee
Optimized for production deployment
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

def daily_sync():
    """Run daily incremental sync"""
    
    # Setup logging with rotation
    setup_daily_logging()
    
    try:
        # Phase 1: Quick API sync (new videos)
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        result = run_ingestion([
            '--source', 'api',
            '--since-published', yesterday,
            '--limit', '25',
            '--concurrency', '2',
            '--skip-shorts'
        ])
        
        log_results("API Sync", result)
        
        # Phase 2: Retry any failures with yt-dlp
        if result.failed_count > 0:
            result = run_ingestion([
                '--source', 'yt-dlp', 
                '--retry-failed',
                '--concurrency', '1'
            ])
            log_results("Fallback Sync", result)
        
        # Phase 3: Database maintenance
        vacuum_database()
        
        # Phase 4: Health check
        run_health_check()
        
        logging.info("Daily sync completed successfully")
        
    except Exception as e:
        logging.error(f"Daily sync failed: {e}")
        send_alert(f"Daily sync error: {e}")
        
if __name__ == "__main__":
    daily_sync()
```

## 🚀 **Windows Task Scheduler Setup**

### **Task Configuration:**
- **Trigger**: Daily at 3:00 AM
- **Action**: Start program
- **Program**: `python`
- **Arguments**: `backend\scripts\daily_sync.py`
- **Start In**: `C:\Users\hugoa\Desktop\ask-dr-chaffee`

### **Advanced Settings:**
- **Run whether user is logged on or not**: ✅
- **Run with highest privileges**: ✅  
- **Stop if runs longer than**: 2 hours
- **Restart on failure**: 3 times, every 15 minutes

## 📈 **Scaling Considerations**

### **As Channel Grows:**
- **Current**: 1-3 videos/day → 5-10 minutes processing
- **Future**: 5-10 videos/day → 15-30 minutes processing
- **Enterprise**: Multiple channels → Distributed processing

### **Performance Optimization:**
```python
# Adaptive concurrency based on workload
daily_video_count = get_videos_since_yesterday()
if daily_video_count <= 3:
    concurrency = 1        # Light day
elif daily_video_count <= 10:
    concurrency = 2        # Normal day  
else:
    concurrency = 3        # Busy day
```

## 🎯 **Expected Daily Performance**

### **With RTX 5080 + Optimizations:**
- **1-3 new videos**: 5-15 minutes total
- **API quota usage**: 50-100 units/day (well under limit)
- **Database growth**: 50-200 new chunks/day
- **Search freshness**: Content available within 6 hours

## ✅ **Implementation Checklist**

After tonight's test completes:

1. **[ ]** Analyze overnight performance metrics
2. **[ ]** Create production daily sync script
3. **[ ]** Set up Windows Task Scheduler  
4. **[ ]** Configure log rotation and monitoring
5. **[ ]** Test daily sync with recent videos
6. **[ ]** Set up failure alerting (email/SMS)
7. **[ ]** Document production maintenance procedures

---

**This transforms your MVP into a self-updating, production-ready knowledge system that stays current with Dr. Chaffee's latest content automatically!** 🚀
