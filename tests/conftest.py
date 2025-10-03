"""Shared pytest fixtures for unit tests."""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock

import pytest


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory that's automatically cleaned up."""
    return tmp_path


@pytest.fixture
def mock_env(monkeypatch):
    """Provide a clean environment for testing."""
    # Clear relevant env vars
    env_vars = [
        'DATABASE_URL',
        'YOUTUBE_API_KEY',
        'YOUTUBE_CHANNEL_URL',
        'IO_WORKERS',
        'ASR_WORKERS',
        'DB_WORKERS',
        'BATCH_SIZE',
        'SKIP_SHORTS',
        'NEWEST_FIRST',
        'WHISPER_MODEL',
        'MAX_AUDIO_DURATION',
        'AUTO_BOOTSTRAP_CHAFFEE',
        'AUDIO_STORAGE_DIR',
        'VOICES_DIR',
        'CHAFFEE_MIN_SIM',
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    
    # Set minimal required vars
    monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
    
    return monkeypatch


@pytest.fixture
def mock_subprocess_success():
    """Mock subprocess.run that returns success."""
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = '{"format": {"duration": "120.5"}}'
    mock_result.stderr = ''
    return Mock(return_value=mock_result)


@pytest.fixture
def mock_subprocess_failure():
    """Mock subprocess.run that returns failure."""
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stdout = ''
    mock_result.stderr = 'Error: command failed'
    return Mock(return_value=mock_result)


@pytest.fixture
def mock_check_output_success():
    """Mock subprocess.check_output that returns success."""
    return Mock(return_value="90, 8000, 8000, 75.0, 250.0")


@pytest.fixture
def fake_video_info():
    """Create a fake VideoInfo object for testing."""
    from datetime import datetime, timezone
    
    class FakeVideoInfo:
        def __init__(self, video_id='test_video_123', title='Test Video'):
            self.video_id = video_id
            self.title = title
            self.published_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
            self.duration_s = 120
            self.view_count = 1000
            self.channel_name = 'Test Channel'
            self.channel_url = 'https://youtube.com/@test'
            self.thumbnail_url = 'https://example.com/thumb.jpg'
            self.like_count = 50
            self.comment_count = 10
            self.description = 'Test description'
            self.tags = ['test', 'video']
            self.url = f'https://youtube.com/watch?v={video_id}'
    
    return FakeVideoInfo


@pytest.fixture
def fake_transcript_segment():
    """Create a fake transcript segment for testing."""
    class FakeSegment:
        def __init__(self, start=0.0, end=5.0, text='Test segment', speaker='CHAFFEE'):
            self.start = start
            self.end = end
            self.text = text
            self.speaker_label = speaker
            self.speaker_confidence = 0.95
            self.avg_logprob = -0.2
            self.compression_ratio = 1.5
            self.no_speech_prob = 0.01
            self.temperature_used = 0.0
            self.re_asr = False
            self.is_overlap = False
            self.needs_refinement = False
            self.embedding = None
    
    return FakeSegment


@pytest.fixture
def mock_logger(monkeypatch):
    """Mock logger to capture log calls."""
    mock_log = Mock()
    import logging
    
    # Create a mock logger that captures calls
    logger = logging.getLogger('backend.scripts.ingest_youtube_enhanced')
    original_handlers = logger.handlers[:]
    logger.handlers = []
    
    mock_handler = Mock()
    logger.addHandler(mock_handler)
    
    yield logger
    
    # Restore original handlers
    logger.handlers = original_handlers


@pytest.fixture
def frozen_time():
    """Provide frozen time for deterministic testing."""
    from freezegun import freeze_time
    with freeze_time("2024-01-01 12:00:00"):
        yield


@pytest.fixture
def mock_database_connection(monkeypatch):
    """Mock database connections to avoid real DB calls."""
    mock_db = Mock()
    mock_db.check_video_exists = Mock(return_value=(None, 0))
    mock_db.upsert_source = Mock(return_value=1)
    mock_db.batch_insert_segments = Mock(return_value=10)
    mock_db.close_connection = Mock()
    return mock_db


@pytest.fixture
def mock_embedder():
    """Mock embedding generator."""
    mock = Mock()
    mock.generate_embeddings = Mock(return_value=[[0.1] * 384] * 10)
    return mock


@pytest.fixture
def capture_structured_logs(caplog):
    """Capture and parse structured logs."""
    import logging
    caplog.set_level(logging.INFO)
    
    def parse_logs():
        """Parse captured logs into structured format."""
        logs = []
        for record in caplog.records:
            logs.append({
                'level': record.levelname,
                'message': record.message,
                'name': record.name,
            })
        return logs
    
    caplog.parse_logs = parse_logs
    return caplog
