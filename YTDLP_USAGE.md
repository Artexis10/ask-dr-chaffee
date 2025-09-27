# yt-dlp Usage Guide for Ask Dr. Chaffee

This document provides comprehensive guidance on using yt-dlp within the Ask Dr. Chaffee ingestion pipeline, including troubleshooting, proxy configuration, and advanced usage patterns.

## Overview

yt-dlp serves as both a fallback method for video discovery and the primary tool for audio extraction when Whisper transcription is needed. The pipeline uses yt-dlp in two main contexts:

1. **Video Discovery Fallback**: When YouTube Data API is unavailable or hits quota limits
2. **Audio Extraction**: For Whisper transcription when official captions aren't available

## Installation & Setup

### Windows 11 (Recommended)

```powershell
# Using winget (recommended)
winget install yt-dlp.yt-dlp

# Or using pip
pip install yt-dlp

# Verify installation
yt-dlp --version
```

### Linux/macOS

```bash
# Using pip
pip install yt-dlp

# Or using package managers
sudo apt install yt-dlp  # Ubuntu/Debian
brew install yt-dlp      # macOS

# Verify installation
yt-dlp --version
```

## Configuration

### Environment Variables

```bash
# Proxy configuration (if needed)
YTDLP_PROXY=socks5://user:pass@proxy.example.com:1080

# Default options for all yt-dlp operations
YTDLP_OPTS=--sleep-requests 1 --max-sleep-interval 3 --retries 10 --fragment-retries 10 --socket-timeout 20

# FFmpeg path (Windows)
FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe
```

### Proxy Configuration

When YouTube blocks your IP, configure proxies:

```bash
# SOCKS5 proxy (recommended)
YTDLP_PROXY=socks5://127.0.0.1:1080

# HTTP proxy
YTDLP_PROXY=http://proxy.example.com:8080

# Authenticated proxy
YTDLP_PROXY=socks5://username:password@proxy.example.com:1080
```

## Usage in Ingestion Pipeline

### Video Discovery Mode

When using yt-dlp for video discovery (fallback from API):

```bash
# Use yt-dlp for video discovery
python scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 50

# With proxy support
python scripts/ingest_youtube_enhanced.py --source yt-dlp --proxy socks5://127.0.0.1:1080

# Process from pre-dumped JSON
python scripts/ingest_youtube_enhanced.py --source yt-dlp --from-json data/videos.json
```

### Audio Extraction Mode

When extracting audio for Whisper transcription:

```bash
# Force Whisper transcription (uses yt-dlp for audio)
python scripts/ingest_youtube_enhanced.py --force-whisper --whisper-model medium.en

# With FFmpeg path specification
python scripts/ingest_youtube_enhanced.py --force-whisper --ffmpeg-path /path/to/ffmpeg
```

## Command Examples

### Basic Video Listing

```bash
# List channel videos to JSON
python scripts/common/list_videos_yt_dlp.py "https://www.youtube.com/@anthonychaffeemd" --output data/videos.json

# Limit results
python scripts/common/list_videos_yt_dlp.py "https://www.youtube.com/@anthonychaffeemd" --limit 100

# With date filtering (yt-dlp format)
python scripts/common/list_videos_yt_dlp.py "https://www.youtube.com/@anthonychaffeemd" --date-after 20240101
```

### Audio Extraction

```bash
# Extract audio for single video
yt-dlp -x --audio-format wav --audio-quality 0 "https://www.youtube.com/watch?v=VIDEO_ID"

# Extract with specific format
yt-dlp -f "bestaudio[ext=m4a]/bestaudio" --extract-audio --audio-format wav "https://www.youtube.com/watch?v=VIDEO_ID"

# With proxy
yt-dlp --proxy socks5://127.0.0.1:1080 -x --audio-format wav "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Subtitle Extraction

```bash
# Extract all available subtitles
yt-dlp --write-subs --write-auto-subs --skip-download "https://www.youtube.com/watch?v=VIDEO_ID"

# Specific language
yt-dlp --write-subs --sub-langs en --skip-download "https://www.youtube.com/watch?v=VIDEO_ID"

# Convert to SRT format
yt-dlp --write-subs --sub-format srt --skip-download "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Troubleshooting

### Common Issues

#### 1. IP Blocking / 403 Errors

**Symptoms:**
```
ERROR: [youtube] Unable to download webpage: HTTP Error 403: Forbidden
```

**Solutions:**
```bash
# Use proxy
export YTDLP_PROXY="socks5://127.0.0.1:1080"

# Add delays between requests
yt-dlp --sleep-requests 2 --max-sleep-interval 5 [URL]

# Use cookies from browser
yt-dlp --cookies-from-browser chrome [URL]
```

#### 2. Network Timeouts

**Symptoms:**
```
ERROR: Unable to download webpage: The read operation timed out
```

**Solutions:**
```bash
# Increase timeout and retries
yt-dlp --socket-timeout 30 --retries 10 --fragment-retries 10 [URL]

# Use IPv4 only
yt-dlp --force-ipv4 [URL]
```

#### 3. Audio Format Issues

**Symptoms:**
```
ERROR: ffmpeg not found. Please install or provide the path using --ffmpeg-location
```

**Solutions:**
```bash
# Windows: Install FFmpeg
winget install Gyan.FFmpeg

# Or specify path
yt-dlp --ffmpeg-location "C:/ffmpeg/bin/ffmpeg.exe" [URL]

# Linux/macOS: Install FFmpeg
sudo apt install ffmpeg  # Ubuntu
brew install ffmpeg      # macOS
```

#### 4. Rate Limiting

**Symptoms:**
```
ERROR: [youtube] Sign in to confirm you're not a bot
```

**Solutions:**
```bash
# Aggressive throttling
yt-dlp --sleep-requests 3 --max-sleep-interval 10 --playlist-random [URL]

# Use browser cookies
yt-dlp --cookies-from-browser firefox [URL]

# Rotate user agents
yt-dlp --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" [URL]
```

### Pipeline-Specific Debugging

#### Debug Video Discovery

```bash
# Test video listing with verbose output
python scripts/common/list_videos_yt_dlp.py "https://www.youtube.com/@anthonychaffeemd" --debug

# Check specific video accessibility
yt-dlp --simulate --print title,duration,upload_date "https://www.youtube.com/watch?v=VIDEO_ID"
```

#### Debug Audio Extraction

```bash
# Test audio extraction for single video
python scripts/common/transcript_fetch.py VIDEO_ID --debug --force-whisper

# Check available formats
yt-dlp -F "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Advanced Configuration

### Proxy Rotation

For large-scale operations, configure proxy rotation:

```python
# In proxy_manager.py or custom script
proxies = [
    "socks5://proxy1.example.com:1080",
    "socks5://proxy2.example.com:1080", 
    "http://proxy3.example.com:8080"
]

# Rotate every N requests
current_proxy = proxies[request_count % len(proxies)]
```

### Custom yt-dlp Options

```bash
# High-quality audio extraction
yt-dlp -f "bestaudio[acodec=aac]/bestaudio" --extract-audio --audio-format wav --audio-quality 0

# Preserve original upload date
yt-dlp --write-info-json --write-description

# Bandwidth limiting
yt-dlp --limit-rate 1M

# Geographic restrictions
yt-dlp --geo-bypass --geo-bypass-country US
```

### Performance Optimization

```bash
# Parallel downloads (use with caution)
yt-dlp --concurrent-fragments 4

# Skip unavailable fragments
yt-dlp --ignore-errors --continue

# Optimize for playlist processing
yt-dlp --playlist-start 1 --playlist-end 100 --ignore-errors
```

## Integration with Enhanced ASR

The pipeline automatically handles yt-dlp integration for Enhanced ASR processing:

```bash
# Enhanced ASR with yt-dlp fallback
python scripts/ingest_youtube_enhanced_asr.py --source yt-dlp --enable-speaker-id

# With proxy support
python scripts/ingest_youtube_enhanced_asr.py --source yt-dlp --proxy socks5://127.0.0.1:1080 --enable-speaker-id

# Local file processing (bypasses yt-dlp)
python scripts/ingest_youtube_enhanced_asr.py --source local --from-files ./audio_files --enable-speaker-id
```

## Best Practices

### 1. Respect Rate Limits

```bash
# Always use delays in production
--sleep-requests 1 --max-sleep-interval 3

# Monitor for rate limiting responses
--retries 10 --fragment-retries 10
```

### 2. Proxy Management

```bash
# Test proxy before use
curl --proxy socks5://127.0.0.1:1080 https://www.youtube.com

# Rotate proxies for large batches
# Use different proxies for different operations
```

### 3. Error Handling

```bash
# Always use error recovery
--ignore-errors --continue --no-abort-on-error

# Log all operations
--verbose --print-json > processing.log 2>&1
```

### 4. Storage Management

```bash
# Clean up temporary files
--rm-cache-dir --clean-infojson

# Organize outputs
--output "downloads/%(uploader)s/%(title)s.%(ext)s"
```

## Monitoring & Logging

### Pipeline Integration

The ingestion pipeline provides built-in monitoring for yt-dlp operations:

```bash
# Check yt-dlp operation status
python scripts/monitor_ingestion.py --source yt-dlp

# View detailed logs
tail -f youtube_ingestion.log | grep yt-dlp

# Check proxy effectiveness
grep "proxy" youtube_ingestion.log | grep -c "success\|failed"
```

### Performance Metrics

```bash
# Monitor download speeds
yt-dlp --newline --progress [URL] 2>&1 | grep -o '[0-9.]*MiB/s'

# Track success rates
grep -c "ERROR\|WARNING\|INFO" processing.log
```

## Production Deployment

### Recommended Settings

```bash
# Production-safe yt-dlp options
YTDLP_OPTS="--sleep-requests 2 --max-sleep-interval 5 --retries 5 --fragment-retries 5 --socket-timeout 30 --ignore-errors --no-abort-on-error"

# With proxy rotation
YTDLP_PROXY_LIST="proxy1.com:1080,proxy2.com:1080,proxy3.com:1080"
```

### Batch Processing

```bash
# Process in smaller batches to avoid detection
python scripts/ingest_youtube_enhanced.py --source yt-dlp --limit 25 --delay 300

# Resume interrupted processing
python scripts/ingest_youtube_enhanced.py --source yt-dlp --resume-from-json data/progress.json
```

### Health Checks

```bash
# Test yt-dlp functionality
yt-dlp --simulate "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Verify proxy connectivity
yt-dlp --proxy "$YTDLP_PROXY" --simulate "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Check FFmpeg integration
yt-dlp --print-json "https://www.youtube.com/watch?v=dQw4w9WgXcQ" | jq .duration
```

## Version Compatibility

| Component | Minimum Version | Recommended | Notes |
|-----------|----------------|-------------|-------|
| yt-dlp | 2023.07.06 | Latest | Regular updates for YouTube changes |
| FFmpeg | 4.0 | 6.0+ | Required for audio extraction |
| Python | 3.8 | 3.11+ | For best performance |

## Related Documentation

- [README.md](README.md) - Main project documentation
- [ENHANCED_ASR_README.md](ENHANCED_ASR_README.md) - Enhanced ASR integration
- [PROXY_SOLUTIONS_ANALYSIS.md](PROXY_SOLUTIONS_ANALYSIS.md) - Proxy configuration details
- [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) - Production deployment guide

## Support

For yt-dlp specific issues:
1. Check the [yt-dlp GitHub repository](https://github.com/yt-dlp/yt-dlp)
2. Update to the latest version: `pip install -U yt-dlp`
3. Review verbose logs with `--verbose` flag
4. Test with minimal command line options first

For pipeline integration issues:
1. Check the ingestion logs in `youtube_ingestion.log`
2. Use `--dry-run` mode for testing
3. Verify environment variables are set correctly
4. Test with a single video first: `--limit 1`
