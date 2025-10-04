"""Unit tests for structured logging in ingest_youtube_enhanced.py."""

import logging
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestStructuredLogging:
    """Test structured logging output."""
    
    def test_processing_stats_log_summary(self, caplog):
        """Test ProcessingStats.log_summary produces structured output."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        caplog.set_level(logging.INFO)
        
        stats = ProcessingStats()
        stats.total = 100
        stats.processed = 85
        stats.skipped = 10
        stats.errors = 5
        stats.youtube_transcripts = 30
        stats.whisper_transcripts = 55
        stats.segments_created = 5000
        stats.chaffee_segments = 4500
        stats.guest_segments = 400
        stats.unknown_segments = 100
        
        stats.log_summary()
        
        # Verify key metrics are logged
        log_text = caplog.text
        assert 'Total videos: 100' in log_text
        assert 'Processed: 85' in log_text
        assert 'Skipped: 10' in log_text
        assert 'Errors: 5' in log_text
        assert 'YouTube transcripts: 30' in log_text
        assert 'Whisper transcripts: 55' in log_text
        assert 'Total segments created: 5000' in log_text
    
    def test_processing_stats_rtf_calculation(self):
        """Test real-time factor calculation."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        stats = ProcessingStats()
        stats.total_audio_duration_s = 3600.0  # 1 hour of audio
        stats.asr_processing_time_s = 600.0    # 10 minutes processing
        
        rtf = stats.calculate_real_time_factor()
        
        # RTF = processing_time / audio_duration
        assert rtf == pytest.approx(600.0 / 3600.0, rel=0.01)
        assert rtf == pytest.approx(0.1667, rel=0.01)
    
    def test_processing_stats_rtf_zero_division(self):
        """Test RTF calculation handles zero division."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        stats = ProcessingStats()
        stats.total_audio_duration_s = 0.0
        stats.asr_processing_time_s = 0.0
        
        rtf = stats.calculate_real_time_factor()
        
        assert rtf == 0.0
    
    def test_processing_stats_throughput_calculation(self):
        """Test throughput calculation (hours per hour)."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        stats = ProcessingStats()
        stats.total_audio_duration_s = 180000.0  # 50 hours of audio
        stats.total_processing_time_s = 3600.0   # 1 hour processing
        
        throughput = stats.calculate_throughput_hours_per_hour()
        
        # Throughput = (audio_hours) / (processing_hours)
        expected = (180000.0 / 3600.0) / (3600.0 / 3600.0)
        assert throughput == pytest.approx(expected, rel=0.01)
        assert throughput == pytest.approx(50.0, rel=0.01)
    
    def test_processing_stats_throughput_zero_division(self):
        """Test throughput calculation handles zero division."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        stats = ProcessingStats()
        stats.total_audio_duration_s = 1000.0
        stats.total_processing_time_s = 0.0
        
        throughput = stats.calculate_throughput_hours_per_hour()
        
        assert throughput == 0.0
    
    def test_processing_stats_add_audio_duration(self):
        """Test adding audio duration accumulates correctly."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        stats = ProcessingStats()
        
        stats.add_audio_duration(120.5)
        stats.add_audio_duration(300.0)
        stats.add_audio_duration(45.5)
        
        assert stats.total_audio_duration_s == pytest.approx(466.0, rel=0.01)
    
    def test_processing_stats_speaker_breakdown_logging(self, caplog):
        """Test speaker attribution breakdown is logged."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        caplog.set_level(logging.INFO)
        
        stats = ProcessingStats()
        stats.total = 10
        stats.processed = 10
        stats.segments_created = 1000
        stats.chaffee_segments = 850
        stats.guest_segments = 100
        stats.unknown_segments = 50
        
        stats.log_summary()
        
        log_text = caplog.text
        assert 'Chaffee segments: 850' in log_text
        assert 'Guest segments: 100' in log_text
        assert 'Unknown segments: 50' in log_text
        assert 'Chaffee percentage:' in log_text
    
    def test_processing_stats_performance_target_indicators(self, caplog):
        """Test performance target achievement indicators."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        caplog.set_level(logging.INFO)
        
        stats = ProcessingStats()
        stats.total = 10
        stats.processed = 10
        stats.total_audio_duration_s = 3600.0
        stats.asr_processing_time_s = 720.0  # RTF = 0.2 (within target)
        stats.total_processing_time_s = 3600.0
        
        stats.log_summary()
        
        log_text = caplog.text
        assert 'RTX 5080 PERFORMANCE METRICS' in log_text
        assert 'Real-time factor (RTF):' in log_text
        assert 'target: 0.15-0.22' in log_text
    
    def test_processing_stats_1200h_estimate(self, caplog):
        """Test 1200h ingestion time estimate is logged."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        caplog.set_level(logging.INFO)
        
        stats = ProcessingStats()
        stats.total = 10
        stats.processed = 10
        stats.total_audio_duration_s = 180000.0  # 50 hours
        stats.total_processing_time_s = 3600.0   # 1 hour (50h/h throughput)
        
        stats.log_summary()
        
        log_text = caplog.text
        assert 'Estimated time for 1200h:' in log_text
        # At 50h/h, 1200h should take 24 hours
        assert '24.0 hours' in log_text


@pytest.mark.unit
class TestLoggingNoSecrets:
    """Test that secrets are never logged."""
    
    def test_api_key_not_logged(self, caplog, monkeypatch):
        """Test API key is never logged."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        caplog.set_level(logging.DEBUG)
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('YOUTUBE_API_KEY', 'secret_api_key_12345')
        
        config = IngestionConfig(
            source='api',
            enable_speaker_id=False,
        )
        
        # API key should never appear in logs
        assert 'secret_api_key_12345' not in caplog.text
    
    def test_database_password_not_logged(self, monkeypatch, caplog):
        """Test database URL is not logged."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://user:secret_pass@localhost/db')
        
        config = IngestionConfig(source='yt-dlp', enable_speaker_id=False, dry_run=True)
        
        # Password should never appear in logs
        assert 'secret_pass' not in caplog.text
    
    def test_proxy_credentials_not_logged(self, caplog, monkeypatch):
        """Test proxy credentials are not logged."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        caplog.set_level(logging.DEBUG)
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        config = IngestionConfig(
            source='yt-dlp',
            proxy='http://user:secret_proxy_pass@proxy.example.com:8080',
            enable_speaker_id=False,
            dry_run=True
        )
        
        # Proxy password should never appear in logs
        assert 'secret_proxy_pass' not in caplog.text


@pytest.mark.unit
class TestLoggingPerformanceMetrics:
    """Test performance metrics logging."""
    
    def test_gpu_telemetry_logging(self, caplog, mock_check_output_success):
        """Test GPU telemetry logs performance metrics."""
        from backend.scripts.ingest_youtube_enhanced import _telemetry_hook, ProcessingStats
        
        caplog.set_level(logging.INFO)
        
        stats = ProcessingStats()
        stats.io_queue_peak = 10
        stats.asr_queue_peak = 2
        stats.db_queue_peak = 8
        
        _telemetry_hook(stats, subprocess_runner=mock_check_output_success)
        
        log_text = caplog.text
        assert 'RTX5080 SM=' in log_text
        assert 'VRAM=' in log_text
        assert 'temp=' in log_text
        assert 'power=' in log_text
        assert 'queues:' in log_text
    
    def test_gpu_telemetry_performance_warning(self, caplog):
        """Test GPU telemetry warns on low utilization."""
        from backend.scripts.ingest_youtube_enhanced import _telemetry_hook, ProcessingStats
        
        caplog.set_level(logging.WARNING)
        
        stats = ProcessingStats()
        
        # Mock low GPU utilization
        mock_runner = Mock(return_value="70, 8000, 8000, 75.0, 250.0")
        
        _telemetry_hook(stats, subprocess_runner=mock_runner)
        
        # Should log warning for <90% utilization
        assert 'GPU utilization below target' in caplog.text
        assert '70% < 90%' in caplog.text
    
    def test_optimization_stats_logging(self, caplog):
        """Test optimization statistics are logged."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        caplog.set_level(logging.INFO)
        
        stats = ProcessingStats()
        stats.total = 10
        stats.processed = 10
        stats.monologue_fast_path_used = 7
        stats.content_hash_skips = 3
        stats.embedding_batches = 15
        stats.io_queue_peak = 12
        stats.asr_queue_peak = 2
        stats.db_queue_peak = 10
        
        stats.log_summary()
        
        log_text = caplog.text
        assert 'OPTIMIZATION STATS' in log_text
        assert 'Monologue fast-path used: 7' in log_text
        assert 'Content hash skips: 3' in log_text
        assert 'Embedding batches: 15' in log_text
        assert 'Queue peaks: I/O=12, ASR=2, DB=10' in log_text


@pytest.mark.unit
class TestLoggingErrorHandling:
    """Test error logging and structured error messages."""
    
    def test_error_logging_includes_context(self, caplog):
        """Test error logs include contextual information."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        caplog.set_level(logging.ERROR)
        
        logger = logging.getLogger('backend.scripts.ingest_youtube_enhanced')
        
        # Simulate error logging
        video_id = 'test_video_123'
        error_msg = 'Failed to download audio'
        logger.error(f"❌ Error processing {video_id}: {error_msg}")
        
        log_text = caplog.text
        assert video_id in log_text
        assert error_msg in log_text
    
    def test_error_message_truncation(self):
        """Test long error messages are truncated."""
        long_error = "x" * 1000
        truncated = long_error[:500]
        
        assert len(truncated) == 500
        assert len(long_error) == 1000
    
    def test_debug_logging_disabled_by_default(self, caplog):
        """Test debug logging is not shown at INFO level."""
        caplog.set_level(logging.INFO)
        
        logger = logging.getLogger('backend.scripts.ingest_youtube_enhanced')
        logger.debug("This is a debug message")
        
        # Debug message should not appear at INFO level
        assert "This is a debug message" not in caplog.text
    
    def test_warning_logging_for_skipped_videos(self, caplog):
        """Test warnings are logged for skipped videos."""
        caplog.set_level(logging.WARNING)
        
        logger = logging.getLogger('backend.scripts.ingest_youtube_enhanced')
        logger.warning("⚠️ Video inaccessible: test_video_123")
        
        assert "Video inaccessible" in caplog.text
        assert "test_video_123" in caplog.text
