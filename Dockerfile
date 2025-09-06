# Multi-stage Docker build for yt-dlp + Whisper support
FROM python:3.11-slim as base

# Install system dependencies for yt-dlp and ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp from latest release
RUN pip install --no-cache-dir yt-dlp

WORKDIR /app

# Copy requirements first for better caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .
COPY .env .env

# Create directories for temporary files
RUN mkdir -p /tmp/whisper_cache /tmp/audio_downloads

# Set environment variables for yt-dlp and Whisper
ENV PYTHONPATH=/app
ENV WHISPER_CACHE_DIR=/tmp/whisper_cache
ENV TEMP_AUDIO_DIR=/tmp/audio_downloads
ENV YT_DLP_PATH=yt-dlp
ENV FFMPEG_PATH=ffmpeg

# Health check to ensure yt-dlp works
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import yt_dlp; print('yt-dlp OK')" || exit 1

# Run the FastAPI application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
