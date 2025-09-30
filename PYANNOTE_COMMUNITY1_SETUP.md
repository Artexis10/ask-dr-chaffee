# Upgrading to Pyannote Community-1

## Overview
The system now supports Pyannote Community-1, the latest open-source speaker diarization model released in 2025.

## Setup Instructions

### 1. Install Required Dependencies
```bash
pip install pyannote.audio
```

### 2. Get Hugging Face Access
1. Visit [pyannote/Community-1](https://huggingface.co/pyannote/Community-1)
2. Log in to your Hugging Face account
3. Accept the terms to gain access to the model

### 3. Configure Authentication
Generate a Hugging Face access token:
1. Go to [Settings > Access Tokens](https://huggingface.co/settings/tokens)
2. Create a new token with at least "read" permissions
3. Add to your `.env`:
```bash
HUGGINGFACE_HUB_TOKEN=your_token_here
```

Or login via CLI:
```bash
huggingface-cli login
```

### 4. Enable in Configuration
The system is already configured to use Pyannote Community-1. To enable:

```bash
# In .env
DIARIZE=true
DIARIZATION_MODEL=pyannote/Community-1  # Default is now Community-1
MIN_SPEAKERS=2  # Optional: minimum speakers
MAX_SPEAKERS=5  # Optional: maximum speakers
```

### 5. Benefits of Community-1
- **Better accuracy**: Improved speaker separation vs older models
- **Open source**: No licensing restrictions
- **Latest architecture**: Uses state-of-the-art segmentation + embedding
- **Active development**: Community-maintained and updated

### 6. Fallback Behavior
If Community-1 fails to load:
- System falls back to single-speaker diarization
- Logs clear error messages
- Processing continues without diarization

## Speaker Labels
The system now uses "Chaffee" instead of "CH" for better readability in database and UI.

## Testing
Test with a sample video:
```powershell
python backend/scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 1 --enable-speaker-id --voices-dir .\voices
```

Check logs for:
```
Loading pyannote diarization pipeline: pyannote/Community-1
Successfully loaded pyannote diarization pipeline
```

