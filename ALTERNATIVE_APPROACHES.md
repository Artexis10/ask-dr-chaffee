# Alternative Approaches for Caption Access

## Option 1: Dr. Chaffee Exports Captions Himself (Recommended)

**How it works:**
- Dr. Chaffee uses YouTube Studio to download captions for his videos
- Shares the caption files with you
- You process the files directly without API calls

**Benefits:**
- No trust issues - Dr. Chaffee stays in full control
- No API quotas or rate limits
- No IP blocking issues
- One-time setup

**Steps for Dr. Chaffee:**

### Bulk Caption Export via YouTube Studio

1. Go to [YouTube Studio](https://studio.youtube.com)
2. Click **Content** in left sidebar
3. For each video:
   - Click the video title
   - Go to **Subtitles** tab
   - Click **Download** next to the caption track
   - Choose **SRT** format
4. Share the downloaded `.srt` files

### Alternative: YouTube Takeout (All at once)

1. Go to [Google Takeout](https://takeout.google.com)
2. Select **YouTube and YouTube Music**
3. Click **All YouTube data included** 
4. Uncheck everything except **subtitles**
5. Click **Next step** and **Create export**
6. Download the zip file and share subtitle files

**For you:** Process the SRT files directly:

```bash
# Create a directory for caption files
mkdir backend/data/captions

# Copy SRT files from Dr. Chaffee
cp /path/to/captions/*.srt backend/data/captions/

# Process captions directly
python backend/scripts/process_srt_files.py backend/data/captions/
```

## Option 2: Service Account with Limited Access

**How it works:**
- Create a dedicated service account
- Dr. Chaffee adds the service account (not you personally)
- Service account only has caption access

**Benefits:**
- No personal trust required
- Automated processing
- Revokable access

**Steps:**

1. **Create service account:**
   ```
   Service Account Name: "Caption Extractor Bot"
   Email: caption-bot-xxxxx@project-name.iam.gserviceaccount.com
   ```

2. **Dr. Chaffee adds service account email as Viewer** (minimal permission)
3. **You use service account credentials** for API access

**Trust level:** Lower - it's a bot, not personal access

## Option 3: Residential Proxy (Budget Approach)

**Cheaper proxy options:**

### NordVPN SOCKS5 (Recommended)
- **Cost:** ~$5/month
- **Setup:** Use NordVPN SOCKS5 proxies
- **Reliability:** Good for moderate usage

```bash
# Configure proxy in .env
PROXY_HOST=nordvpn-socks5-server.com
PROXY_PORT=1080
PROXY_USER=your_nordvpn_user
PROXY_PASS=your_nordvpn_pass

# Run with proxy
python backend/scripts/batch_ingestion.py --proxy socks5://user:pass@host:port --limit 100
```

### ProxyMesh (Pay-per-use)
- **Cost:** $10/month for 10 concurrent connections
- **Benefit:** More reliable than free proxies

### Free Proxy Rotation
- **Cost:** Free (unreliable)
- **Use:** Rotate through public proxy lists
- **Risk:** Frequent failures, slower processing

## Option 4: Manual Video Processing

**How it works:**
- Dr. Chaffee provides list of video IDs
- You process videos in small batches during off-peak hours
- Accept some failures and retry later

**Implementation:**
```bash
# Process 10 videos at a time with delays
python backend/scripts/batch_ingestion.py --limit 10 --batch-delay 30 --concurrency 1

# Wait several hours between batches
sleep 3600

# Continue with next batch
python backend/scripts/batch_ingestion.py --limit 10 --skip 10 --batch-delay 30
```

## Recommendation Priority

1. **Caption Export by Dr. Chaffee** - Easiest, most reliable
2. **Service Account** - If he's okay with bot access
3. **NordVPN Proxy** - Budget-friendly technical solution  
4. **Manual Processing** - Last resort

## Implementation for Caption Export Approach

I can create a script to process SRT files directly:

```python
# backend/scripts/process_srt_files.py
def process_srt_directory(caption_dir):
    """Process all SRT files in a directory"""
    for srt_file in Path(caption_dir).glob("*.srt"):
        video_id = extract_video_id_from_filename(srt_file.name)
        segments = parse_srt_file(srt_file)
        # Insert into database same as regular pipeline
```

This would bypass all API issues entirely.

## Next Steps

1. **Ask Dr. Chaffee which approach he prefers**
2. **Caption export** - I'll create the SRT processing script
3. **Service account** - I'll create the bot setup guide
4. **Proxy** - I'll test NordVPN SOCKS5 integration

Which approach would you like to pursue?
