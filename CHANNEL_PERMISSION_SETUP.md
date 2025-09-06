# YouTube Channel Permission Setup for Captions API

This guide explains how Dr. Chaffee can grant permission to access his YouTube channel's captions via the official YouTube Data API, eliminating IP blocking issues.

## Why This Approach Works

**Problem with current methods:**
- YouTube Transcript API (third-party) gets IP blocked frequently
- Whisper requires audio download via yt-dlp, which can also be blocked
- Proxies are expensive ($12-15/GB) and unreliable

**Solution with channel permissions:**
- Official YouTube Data API access to captions
- No IP blocking issues
- Reliable and scalable
- Free within API quotas (10,000 units/day = ~50 videos)

## For Dr. Chaffee: Adding a Collaborator

### Step 1: YouTube Studio Access

1. Go to [YouTube Studio](https://studio.youtube.com)
2. Click on **Settings** (gear icon) in the left sidebar
3. Select **Permissions**

### Step 2: Add Collaborator

1. Click **Invite** in the top right
2. Enter the email address of the person who needs access
3. Choose the role: **Editor** (minimum needed for captions API)
4. Click **Save**

### Step 3: Confirm Access

The collaborator will receive an email invitation and must:
1. Accept the invitation
2. Have access to the channel in their YouTube Studio

## For Developer: Setting Up OAuth2

### Step 1: Get Collaborator Access

1. Dr. Chaffee adds your Google account as Editor
2. Accept the invitation in your email
3. Verify you can see the channel in YouTube Studio

### Step 2: Create OAuth2 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable **YouTube Data API v3**
4. Go to **Credentials** → **Create Credentials** → **OAuth client ID**
5. Choose **Desktop application**
6. Download the JSON file

### Step 3: Configure Environment

1. Save the credentials file:
   ```
   backend/credentials/client-secrets.json
   ```

2. Update `.env` file:
   ```env
   YOUTUBE_API_KEY=your_existing_api_key
   YOUTUBE_CREDENTIALS_PATH=backend/credentials/client-secrets.json
   ```

### Step 4: Enable Captions API in Code

Update `transcript_fetch.py` to enable the captions API:

```python
# Change this line:
# Skip YouTube Data API for now due to ownership requirement

# To:
# Use YouTube Data API with channel permissions
if self.credentials_path or self.api_key:
    api_client = self._get_api_client()
    # ... rest of the code
```

## Testing the Setup

1. **Test channel access:**
   ```bash
   cd backend
   python scripts/test_transcript_api.py 1-Jhm9njwKA --verbose
   ```

2. **Run ingestion:**
   ```bash
   python scripts/ingest_youtube_enhanced.py --source api --limit 10 --skip-shorts
   ```

You should see:
- "Using OAuth2 installed app authentication"
- Successful caption track listing
- No IP blocking errors

## Production Usage

Once set up, you can process hundreds of videos reliably:

```bash
# Process all videos with official API access
python backend/scripts/batch_ingestion.py --limit 500 --batch-size 20 --concurrency 4 --skip-shorts
```

**Benefits:**
- No IP blocking
- Reliable caption access
- Fast processing
- Official API compliance

## API Quotas and Limits

**YouTube Data API v3 quotas:**
- 10,000 units per day (free tier)
- Caption operations: ~200 units per video
- Video listing: ~3 units per video
- **Total capacity: ~50 videos per day**

For higher volumes:
- Request quota increase in Google Cloud Console
- Or process in batches over multiple days

## Troubleshooting

### "Login Required" Error
- Ensure you're added as Editor on the channel
- Check OAuth2 credentials are correct
- Verify YouTube Data API is enabled

### "Video not found" Error
- Confirm you have Editor access to the specific channel
- Check the video ID is correct

### Quota Exceeded
- Monitor usage in Google Cloud Console
- Request quota increase if needed
- Process videos in smaller batches

## Security Notes

1. **Limit OAuth2 scope** to YouTube only
2. **Protect credentials** - never commit to version control
3. **Monitor API usage** regularly
4. **Rotate credentials** periodically

## Alternative: Service Account (Advanced)

For fully automated access without browser interaction:
1. Create service account in Google Cloud Console
2. Dr. Chaffee adds the service account email as Editor
3. Use service account credentials instead of OAuth2

This requires more setup but enables fully automated processing.
