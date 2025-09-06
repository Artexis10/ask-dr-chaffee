# Hybrid Update System: Historical + Live Data

## Problem
Google Takeout gives all historical captions but won't capture new videos automatically.

## Solution: Hybrid Approach

### Phase 1: Bulk Historical Data (One-time)
**Dr. Chaffee:** Google Takeout export (all existing videos)
**Result:** 500+ historical videos processed in hosted system

### Phase 2: Automated Updates (Ongoing)
**System:** Automated detection and processing of new videos
**Frequency:** Daily/weekly checks

## Architecture

```
┌─────────────────┐    ┌──────────────────────┐
│  Google Takeout │───▶│   Historical Data    │
│  (One-time)     │    │   500+ videos       │
└─────────────────┘    └──────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────┐
│              HOSTED SYSTEM                      │
│  PostgreSQL with all historical transcripts     │
└─────────────────────────────────────────────────┘
                                  ▲
                                  │
┌─────────────────┐    ┌──────────────────────┐
│  YouTube Data   │───▶│   New Video Updates  │
│  API (Daily)    │    │   Incremental sync   │
└─────────────────┘    └──────────────────────┘
```

## Implementation Options

### Option 1: Automated Daily Sync (Recommended)
```python
# Scheduled job runs daily on hosted system
@app.on_event("startup")
async def schedule_daily_sync():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        sync_new_videos,
        trigger="cron", 
        hour=6,  # 6 AM daily
        id="daily_video_sync"
    )
    scheduler.start()

async def sync_new_videos():
    """Check for new videos and process transcripts"""
    # 1. Use YouTube Data API to get latest videos
    # 2. Check which ones we don't have in DB
    # 3. Process new videos using existing pipeline:
    #    - YouTube Transcript API + Whisper fallback
    #    - Or budget proxy ($5/month NordVPN)
    # 4. Add to database with embeddings
```

### Option 2: Manual Update Interface
```python
@app.post("/admin/sync-new-videos")
async def manual_sync(admin_key: str):
    """Manual trigger for syncing new videos"""
    # Same logic as automated, but triggered manually
    # Add to admin interface: "Sync New Videos" button
```

### Option 3: Dr. Chaffee Periodic Upload
```python
@app.post("/upload/new-captions")
async def upload_new_captions(files: List[UploadFile]):
    """Upload individual SRT files for new videos"""
    # Dr. Chaffee occasionally uploads new SRT files
    # System merges with existing data
```

## Update Strategies

### Strategy A: YouTube Data API + Transcript Fallbacks (Best)
```python
async def process_new_video(video_id: str):
    """Process a single new video"""
    
    # 1. Get video metadata (YouTube Data API - reliable)
    video_info = await get_video_info(video_id)
    
    # 2. Try transcript methods in order:
    transcript = None
    
    # Try YouTube Transcript API first
    try:
        transcript = await get_youtube_transcript(video_id)
    except IPBlocked:
        # Fallback to Whisper transcription
        transcript = await transcribe_with_whisper(video_id)
    
    # 3. Process and store
    if transcript:
        chunks = process_transcript(transcript, video_id)
        embeddings = generate_embeddings(chunks)
        store_in_database(video_info, chunks, embeddings)
```

### Strategy B: Proxy-Assisted Updates
```python
# For reliable transcript access
NORDVPN_PROXY = "socks5://user:pass@nordvpn-server:1080"

async def get_transcript_with_proxy(video_id: str):
    """Use budget proxy for transcript access"""
    async with aiohttp.ClientSession(
        connector=aiohttp_proxy.ProxyConnector.from_url(NORDVPN_PROXY)
    ) as session:
        # Use YouTube Transcript API through proxy
        return await fetch_transcript(video_id, session)
```

## Deployment Configuration

### Environment Variables
```env
# Existing
DATABASE_URL=postgresql://...
YOUTUBE_API_KEY=your_key_here

# New for updates
SYNC_ENABLED=true
SYNC_SCHEDULE=daily  # daily, weekly, manual
NORDVPN_USER=your_user
NORDVPN_PASS=your_pass
ADMIN_API_KEY=secret_key_for_manual_triggers
```

### Scheduled Jobs (Railway/Heroku)
```python
# Use APScheduler for in-process scheduling
# Or external cron job hitting /admin/sync-new-videos endpoint

# Railway: Built-in cron jobs
# Heroku: Heroku Scheduler add-on
# Vercel: Vercel Cron
```

## Data Freshness Timeline

### Historical Data: Immediate
- Google Takeout: All existing videos (~500)
- Processing time: 1-2 hours
- Available in LLM search immediately

### New Videos: 1-7 days delay
- **Daily sync**: New videos appear next day
- **Weekly sync**: New videos appear within 7 days  
- **Manual sync**: Immediate when triggered

### Cost Analysis
| Approach | Monthly Cost | Data Freshness |
|----------|-------------|----------------|
| Takeout only | $5 (hosting) | Historical only |
| + Daily sync | $10 ($5 proxy) | 1 day delay |
| + Manual uploads | $5 | When Dr. Chaffee uploads |

## Recommended Implementation

### Phase 1: Historical Foundation (Week 1)
1. Get Google Takeout from Dr. Chaffee
2. Deploy hosted system with SRT processor
3. Process all historical videos
4. Launch LLM search interface

### Phase 2: Auto-Updates (Week 2)  
1. Add YouTube Data API integration for new video detection
2. Implement daily sync with transcript fallbacks
3. Add NordVPN proxy support ($5/month)
4. Admin interface for manual syncing

### Phase 3: Monitoring (Week 3)
1. Email notifications for sync status
2. Admin dashboard showing:
   - Last sync time
   - New videos processed
   - Any failures requiring attention

## User Experience

**Dr. Chaffee:**
- One-time Google Takeout (5 minutes)
- Optionally: Periodic SRT uploads for new videos

**End Users:**
- Search all historical content immediately  
- New videos appear automatically (1-day delay)
- No interruption in service

**You:**
- Monitor sync status via admin dashboard
- Manual trigger if needed
- $10/month total cost for fully automated system

This gives you the best of both worlds: comprehensive historical data + automated updates for new content.
