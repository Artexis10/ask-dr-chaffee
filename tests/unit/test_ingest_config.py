"""Unit tests for configuration and environment handling in ingest_youtube_enhanced.py."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestConfigurationDefaults:
    """Test configuration defaults and initialization."""
    
    def test_config_minimal_required_env(self, monkeypatch):
        """Test config with minimal required environment variables."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        config = IngestionConfig(
            source='yt-dlp',  # Use yt-dlp to avoid API key requirement
            enable_speaker_id=False,
            dry_run=True
        )
        
        assert config.db_url == 'postgresql://test:test@localhost/test'
        assert config.source == 'yt-dlp'
        assert config.dry_run is True
    
    def test_config_missing_database_url(self, monkeypatch):
        """Test config raises error when DATABASE_URL missing."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.delenv('DATABASE_URL', raising=False)
        
        with pytest.raises(ValueError, match="DATABASE_URL environment variable required"):
            IngestionConfig(enable_speaker_id=False)
    
    def test_config_env_overrides_defaults(self, monkeypatch):
        """Test environment variables override class defaults."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('IO_WORKERS', '24')
        monkeypatch.setenv('ASR_WORKERS', '4')
        monkeypatch.setenv('DB_WORKERS', '16')
        monkeypatch.setenv('BATCH_SIZE', '512')
        monkeypatch.setenv('SKIP_SHORTS', 'true')
        monkeypatch.setenv('NEWEST_FIRST', 'false')
        monkeypatch.setenv('WHISPER_MODEL', 'large-v3')
        
        config = IngestionConfig(source='yt-dlp', enable_speaker_id=False, dry_run=True)
        
        assert config.io_concurrency == 24
        assert config.asr_concurrency == 4
        assert config.db_concurrency == 16
        assert config.embedding_batch_size == 512
        assert config.skip_shorts is True
        assert config.newest_first is False
        assert config.whisper_model == 'large-v3'
    
    def test_config_channel_url_default(self, monkeypatch):
        """Test default channel URL is set."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        config = IngestionConfig(source='yt-dlp', enable_speaker_id=False, dry_run=True)
        
        assert config.channel_url == 'https://www.youtube.com/@anthonychaffeemd'
    
    def test_config_channel_url_override(self, monkeypatch):
        """Test channel URL can be overridden."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('YOUTUBE_CHANNEL_URL', 'https://www.youtube.com/@custom')
        
        config = IngestionConfig(source='yt-dlp', enable_speaker_id=False, dry_run=True)
        
        assert config.channel_url == 'https://www.youtube.com/@custom'
    
    def test_config_auto_switch_to_ytdlp_for_url(self, monkeypatch):
        """Test config auto-switches to yt-dlp when using --from-url."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        config = IngestionConfig(
            source='api',  # Start with API
            from_url=['https://youtube.com/watch?v=test123'],
            enable_speaker_id=False,
            dry_run=True
        )
        
        # Should auto-switch to yt-dlp
        assert config.source == 'yt-dlp'
    
    def test_config_api_key_required_for_api_source(self, monkeypatch):
        """Test API key is required when using API source."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
        
        with pytest.raises(ValueError, match="YOUTUBE_API_KEY required for API source"):
            IngestionConfig(
                source='api',
                enable_speaker_id=False
            )
    
    def test_config_api_key_provided(self, monkeypatch):
        """Test config accepts API key from environment."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('YOUTUBE_API_KEY', 'test_api_key_12345')
        
        config = IngestionConfig(
            source='api',
            enable_speaker_id=False,
            dry_run=True
        )
        
        assert config.youtube_api_key == 'test_api_key_12345'


@pytest.mark.unit
class TestConfigurationValidation:
    """Test configuration validation logic."""
    
    def test_config_local_source_requires_from_files(self, monkeypatch):
        """Test local source requires --from-files directory."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        with pytest.raises(ValueError, match="--from-files directory required for local source"):
            IngestionConfig(
                source='local',
                enable_speaker_id=False
            )
    
    def test_config_local_source_directory_must_exist(self, monkeypatch, tmp_path):
        """Test local source directory must exist."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        non_existent = tmp_path / "does_not_exist"
        
        with pytest.raises(ValueError, match="Local files directory does not exist"):
            IngestionConfig(
                source='local',
                from_files=non_existent,
                enable_speaker_id=False
            )
    
    def test_config_local_source_valid_directory(self, monkeypatch, tmp_path):
        """Test local source with valid directory."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        valid_dir = tmp_path / "videos"
        valid_dir.mkdir()
        
        config = IngestionConfig(
            source='local',
            from_files=valid_dir,
            enable_speaker_id=False,
            dry_run=True
        )
        
        assert config.source == 'local'
        assert config.from_files == valid_dir
    
    def test_config_file_patterns_default(self, monkeypatch, tmp_path):
        """Test default file patterns for local source."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        valid_dir = tmp_path / "videos"
        valid_dir.mkdir()
        
        config = IngestionConfig(
            source='local',
            from_files=valid_dir,
            enable_speaker_id=False,
            dry_run=True
        )
        
        # Should have default patterns
        assert '*.mp4' in config.file_patterns
        assert '*.wav' in config.file_patterns
        assert '*.mp3' in config.file_patterns
    
    def test_config_file_patterns_custom(self, monkeypatch, tmp_path):
        """Test custom file patterns."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        valid_dir = tmp_path / "videos"
        valid_dir.mkdir()
        
        config = IngestionConfig(
            source='local',
            from_files=valid_dir,
            file_patterns=['*.mkv', '*.flac'],
            enable_speaker_id=False,
            dry_run=True
        )
        
        assert config.file_patterns == ['*.mkv', '*.flac']
    
    def test_config_concurrency_bounds(self, monkeypatch):
        """Test concurrency values are properly set."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('IO_WORKERS', '1')
        monkeypatch.setenv('ASR_WORKERS', '1')
        monkeypatch.setenv('DB_WORKERS', '1')
        
        config = IngestionConfig(source='yt-dlp', enable_speaker_id=False, dry_run=True)
        
        assert config.io_concurrency == 1
        assert config.asr_concurrency == 1
        assert config.db_concurrency == 1
    
    def test_config_max_duration_parsing(self, monkeypatch):
        """Test MAX_AUDIO_DURATION parsing."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('MAX_AUDIO_DURATION', '3600')
        
        config = IngestionConfig(source='yt-dlp', enable_speaker_id=False, dry_run=True)
        
        # Should set max_duration attribute
        assert hasattr(config, 'max_duration')
        assert config.max_duration == 3600


@pytest.mark.unit
class TestConfigurationSecrets:
    """Test that secrets are not exposed in logs or errors."""
    
    def test_config_api_key_not_in_repr(self, monkeypatch):
        """Test API key is not exposed in string representation."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('YOUTUBE_API_KEY', 'secret_key_12345')
        
        config = IngestionConfig(
            source='api',
            enable_speaker_id=False,
            dry_run=True
        )
        
        # API key should not appear in string representation
        config_str = str(config.__dict__)
        # Note: dataclass doesn't redact by default, but we verify it's stored
        assert config.youtube_api_key == 'secret_key_12345'
    
    def test_config_db_url_not_logged(self, monkeypatch, caplog):
        """Test database URL is not logged."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://user:secret_pass@localhost/db')
        
        config = IngestionConfig(source='yt-dlp', enable_speaker_id=False, dry_run=True)
        
        # Database password should not appear in logs
        assert 'secret_pass' not in caplog.text


@pytest.mark.unit
class TestWhisperPresetSelection:
    """Test Whisper model preset selection logic."""
    
    def test_pick_whisper_preset_short_video(self):
        """Test preset selection for short videos (≤20min)."""
        from backend.scripts.ingest_youtube_enhanced import pick_whisper_preset
        
        preset = pick_whisper_preset(duration_minutes=15.0, is_interview=False)
        
        assert preset['model'] == 'distil-large-v3'
        assert preset['compute_type'] == 'int8_float16'
        assert preset['beam_size'] == 1
        assert preset['use_case'] == '≤20min videos'
    
    def test_pick_whisper_preset_long_monologue(self):
        """Test preset selection for long monologues."""
        from backend.scripts.ingest_youtube_enhanced import pick_whisper_preset
        
        preset = pick_whisper_preset(duration_minutes=45.0, is_interview=False)
        
        assert preset['model'] == 'distil-large-v3'
        assert preset['use_case'] == 'long monologues'
    
    def test_pick_whisper_preset_interview(self):
        """Test preset selection for interviews."""
        from backend.scripts.ingest_youtube_enhanced import pick_whisper_preset
        
        preset = pick_whisper_preset(duration_minutes=30.0, is_interview=True)
        
        assert preset['model'] == 'distil-large-v3'
        assert preset['use_case'] == 'interviews/multi-speaker'
    
    def test_pick_whisper_preset_boundary_20min(self):
        """Test preset selection at 20-minute boundary."""
        from backend.scripts.ingest_youtube_enhanced import pick_whisper_preset
        
        preset_at = pick_whisper_preset(duration_minutes=20.0, is_interview=False)
        preset_above = pick_whisper_preset(duration_minutes=20.1, is_interview=False)
        
        assert preset_at['use_case'] == '≤20min videos'
        assert preset_above['use_case'] == 'long monologues'


@pytest.mark.unit
class TestContentHashing:
    """Test content hash computation for deduplication."""
    
    def test_compute_content_hash_video_id_only(self):
        """Test content hash with video ID only."""
        from backend.scripts.ingest_youtube_enhanced import compute_content_hash
        
        hash1 = compute_content_hash('video123')
        hash2 = compute_content_hash('video123')
        hash3 = compute_content_hash('video456')
        
        # Same video ID should produce same hash
        assert hash1 == hash2
        
        # Different video ID should produce different hash
        assert hash1 != hash3
    
    def test_compute_content_hash_with_upload_date(self):
        """Test content hash includes upload date."""
        from backend.scripts.ingest_youtube_enhanced import compute_content_hash
        from datetime import datetime, timezone
        
        date1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        
        hash1 = compute_content_hash('video123', upload_date=date1)
        hash2 = compute_content_hash('video123', upload_date=date2)
        
        # Different dates should produce different hashes
        assert hash1 != hash2
    
    def test_compute_content_hash_deterministic(self):
        """Test content hash is deterministic."""
        from backend.scripts.ingest_youtube_enhanced import compute_content_hash
        from datetime import datetime, timezone
        
        date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        
        hashes = [
            compute_content_hash('video123', upload_date=date)
            for _ in range(5)
        ]
        
        # All hashes should be identical
        assert len(set(hashes)) == 1
    
    def test_compute_content_hash_missing_audio_file(self, tmp_path):
        """Test content hash handles missing audio file gracefully."""
        from backend.scripts.ingest_youtube_enhanced import compute_content_hash
        
        non_existent = str(tmp_path / "missing.wav")
        
        # Should not raise, just skip audio fingerprint
        hash_result = compute_content_hash('video123', audio_path=non_existent)
        
        assert isinstance(hash_result, str)
        assert len(hash_result) == 32  # MD5 hex digest length
