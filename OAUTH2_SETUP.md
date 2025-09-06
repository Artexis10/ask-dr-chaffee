# YouTube Data API OAuth2 Setup Guide

This guide explains how to set up OAuth2 authentication for the YouTube Data API to access captions/transcripts.

## Option 1: Service Account (Recommended for Production)

Service accounts are ideal for server-to-server authentication without user interaction.

### Step 1: Create a Service Account

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project or create a new one
3. Navigate to **IAM & Admin** → **Service Accounts**
4. Click **Create Service Account**
5. Fill in the service account details:
   - **Name**: `youtube-transcript-service`
   - **Description**: `Service account for YouTube transcript access`
6. Click **Create and Continue**
7. Skip role assignment (click **Continue**)
8. Click **Done**

### Step 2: Create Service Account Key

1. Click on the newly created service account
2. Go to the **Keys** tab
3. Click **Add Key** → **Create new key**
4. Select **JSON** format
5. Click **Create**
6. The JSON file will be downloaded automatically

### Step 3: Enable YouTube Data API

1. Go to **APIs & Services** → **Library**
2. Search for "YouTube Data API v3"
3. Click on it and click **Enable**

### Step 4: Configure Environment

1. Move the downloaded JSON file to your project directory:
   ```bash
   cp ~/Downloads/youtube-transcript-service-xxxxx.json backend/credentials/service-account.json
   ```

2. Add to your `.env` file:
   ```env
   YOUTUBE_CREDENTIALS_PATH=backend/credentials/service-account.json
   YOUTUBE_API_KEY=your_existing_api_key_here
   ```

## Option 2: OAuth2 Client Secrets (Interactive)

Use this for development or when you need user consent.

### Step 1: Create OAuth2 Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** → **Credentials**
3. Click **Create Credentials** → **OAuth client ID**
4. If prompted, configure the OAuth consent screen:
   - Choose **External** user type
   - Fill in required fields (App name, User support email, etc.)
   - Add your email to Test users
5. For Application type, select **Desktop application**
6. Give it a name: `YouTube Transcript Client`
7. Click **Create**
8. Download the JSON file

### Step 2: Configure Environment

1. Move the downloaded JSON file to your project directory:
   ```bash
   cp ~/Downloads/client_secret_xxxxx.json backend/credentials/client-secrets.json
   ```

2. Add to your `.env` file:
   ```env
   YOUTUBE_CREDENTIALS_PATH=backend/credentials/client-secrets.json
   YOUTUBE_API_KEY=your_existing_api_key_here
   ```

### Step 3: First-time Authentication

When you run the ingestion script for the first time, it will:
1. Open a browser window
2. Ask you to sign in to Google
3. Request permission to access YouTube data
4. Save the token for future use

## Environment Variables

Add these to your `.env` file:

```env
# YouTube Data API (for video listing)
YOUTUBE_API_KEY=your_youtube_api_key_here

# YouTube OAuth2 (for captions/transcripts)
YOUTUBE_CREDENTIALS_PATH=backend/credentials/service-account.json
# OR
# YOUTUBE_CREDENTIALS_PATH=backend/credentials/client-secrets.json

# Other existing variables...
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ask_dr_chaffee
DB_USER=postgres
DB_PASSWORD=postgres
```

## Directory Structure

Create the credentials directory:

```bash
mkdir -p backend/credentials
```

Your project structure should look like:

```
ask-dr-chaffee/
├── backend/
│   ├── credentials/
│   │   ├── service-account.json      # Service account key
│   │   ├── client-secrets.json       # OAuth2 client secrets
│   │   └── client-secrets_token.json # Auto-generated token (OAuth2 only)
│   └── scripts/
├── .env
└── .gitignore
```

**Important**: Make sure `backend/credentials/` is in your `.gitignore` file to avoid committing secrets!

## Testing the Setup

Test your OAuth2 setup:

```bash
cd backend
python scripts/test_transcript_api.py 1-Jhm9njwKA --verbose
```

If successful, you should see:
- "Using service account authentication" or "Using OAuth2 installed app authentication"
- Caption tracks listed for the video
- Transcript segments displayed

## Usage in Production

Once configured, run ingestion with full OAuth2 support:

```bash
# Basic ingestion with OAuth2 captions
python backend/scripts/ingest_youtube_enhanced.py --source api --limit 50 --skip-shorts

# Batch processing
python backend/scripts/batch_ingestion.py --limit 100 --batch-size 10 --concurrency 4 --skip-shorts
```

## Troubleshooting

### "Login Required" Error
- Ensure your credentials file path is correct
- Check that the credentials file is valid JSON
- Verify the YouTube Data API is enabled in your project

### "API keys are not supported" Error
- This means OAuth2 is not being used for captions
- Check your `YOUTUBE_CREDENTIALS_PATH` environment variable
- Verify the credentials file exists and is readable

### Permission Denied
- For service accounts: Ensure the service account has proper permissions
- For OAuth2: Make sure you've completed the consent flow

### Browser Not Opening (OAuth2)
- Check if you're running on a server without a display
- Consider using service account authentication instead

## Security Best Practices

1. **Never commit credentials** to version control
2. **Restrict API key usage** in Google Cloud Console
3. **Use service accounts** for production environments
4. **Regularly rotate** service account keys
5. **Monitor API usage** in Google Cloud Console

## API Quotas

The YouTube Data API has the following quotas:
- **10,000 units per day** (free tier)
- **Captions operations**: ~200 units per video
- **Video listing**: ~1-3 units per video

With OAuth2 captions, you can process approximately **50 videos per day** within the free quota.
