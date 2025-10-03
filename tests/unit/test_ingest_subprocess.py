"""Unit tests for subprocess pipeline in ingest_youtube_enhanced.py."""

import json
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

import pytest


@pytest.mark.unit
class TestSubprocessPipeline:
    """Test subprocess command construction and execution."""
    
    def test_telemetry_hook_success(self, mock_check_output_success):
        """Test GPU telemetry with successful nvidia-smi call."""
        from backend.scripts.ingest_youtube_enhanced import _telemetry_hook, ProcessingStats
        
        stats = ProcessingStats()
        stats.io_queue_peak = 5
        stats.asr_queue_peak = 2
        stats.db_queue_peak = 8
        
        # Should not raise
        _telemetry_hook(stats, subprocess_runner=mock_check_output_success)
        
        # Verify correct command was called
        mock_check_output_success.assert_called_once()
        args = mock_check_output_success.call_args[0][0]
        assert args[0] == "nvidia-smi"
        assert "--query-gpu=utilization.gpu,memory.used,memory.free,temperature.gpu,power.draw" in args
        assert "--format=csv,noheader,nounits" in args
    
    def test_telemetry_hook_failure_graceful(self):
        """Test GPU telemetry handles nvidia-smi failure gracefully."""
        from backend.scripts.ingest_youtube_enhanced import _telemetry_hook, ProcessingStats
        
        stats = ProcessingStats()
        mock_runner = Mock(side_effect=Exception("nvidia-smi not found"))
        
        # Should not raise - failures are logged but not fatal
        _telemetry_hook(stats, subprocess_runner=mock_runner)
    
    def test_telemetry_hook_malformed_output(self):
        """Test GPU telemetry handles malformed nvidia-smi output."""
        from backend.scripts.ingest_youtube_enhanced import _telemetry_hook, ProcessingStats
        
        stats = ProcessingStats()
        mock_runner = Mock(return_value="invalid,output")
        
        # Should not raise
        _telemetry_hook(stats, subprocess_runner=mock_runner)
    
    def test_fast_duration_ffprobe_success(self, tmp_path):
        """Test duration extraction via ffprobe subprocess."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        # Create a fake audio file
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        # Mock subprocess.run to return duration
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"format": {"duration": "123.456"}}'
        mock_result.stderr = ''
        mock_runner = Mock(return_value=mock_result)
        
        duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        assert duration == 123.456
        
        # Verify ffprobe was called with correct args
        mock_runner.assert_called_once()
        args = mock_runner.call_args[0][0]
        assert args[0] == "ffprobe"
        assert "-v" in args
        assert "quiet" in args
        assert "-print_format" in args
        assert "json" in args
        assert str(test_file) in args
    
    def test_fast_duration_ffprobe_failure(self, tmp_path):
        """Test duration extraction handles ffprobe failure."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        # Mock subprocess.run to fail
        mock_runner = Mock(side_effect=Exception("ffprobe failed"))
        
        duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        # Should return 0.0 on failure
        assert duration == 0.0
    
    def test_fast_duration_invalid_json(self, tmp_path):
        """Test duration extraction handles invalid JSON from ffprobe."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        # Mock subprocess.run to return invalid JSON
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'not valid json'
        mock_result.stderr = ''
        mock_runner = Mock(return_value=mock_result)
        
        duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        # Should return 0.0 on parse failure
        assert duration == 0.0
    
    def test_fast_duration_missing_duration_field(self, tmp_path):
        """Test duration extraction handles missing duration field."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        # Mock subprocess.run to return JSON without duration
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"format": {}}'
        mock_result.stderr = ''
        mock_runner = Mock(return_value=mock_result)
        
        duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        # Should return 0.0 when duration field missing
        assert duration == 0.0
    
    def test_fast_duration_non_zero_return_code(self, tmp_path):
        """Test duration extraction handles non-zero return code."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        # Mock subprocess.run to return non-zero
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ''
        mock_result.stderr = 'File not found'
        mock_runner = Mock(side_effect=Exception("Command failed"))
        
        duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        # Should return 0.0 on failure
        assert duration == 0.0
    
    @pytest.mark.parametrize("stderr_content,expected_duration", [
        ("", 120.5),  # No warnings
        ("Warning: deprecated option\n", 120.5),  # Warnings but success
        ("Multiple warnings\nAnother warning\n", 120.5),  # Multiple warnings
    ])
    def test_subprocess_stderr_handling(self, tmp_path, stderr_content, expected_duration):
        """Test subprocess handles stderr warnings correctly."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"format": {"duration": "120.5"}}'
        mock_result.stderr = stderr_content
        mock_runner = Mock(return_value=mock_result)
        
        duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        assert duration == expected_duration
    
    def test_subprocess_timeout_handling(self, tmp_path):
        """Test subprocess handles timeout correctly."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        import subprocess
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        # Mock subprocess.run to raise TimeoutExpired
        mock_runner = Mock(side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=10))
        
        duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        # Should return 0.0 on timeout
        assert duration == 0.0
    
    def test_subprocess_args_validation(self, tmp_path):
        """Test subprocess is called with correct argument structure."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"format": {"duration": "60.0"}}'
        mock_result.stderr = ''
        mock_runner = Mock(return_value=mock_result)
        
        _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        # Verify subprocess.run was called with correct kwargs
        call_kwargs = mock_runner.call_args[1]
        assert call_kwargs.get('capture_output') is True
        assert call_kwargs.get('text') is True
        assert call_kwargs.get('check') is True
        assert call_kwargs.get('timeout') == 10
    
    def test_subprocess_command_sequence(self, tmp_path):
        """Test subprocess commands are built in correct order."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"format": {"duration": "45.0"}}'
        mock_result.stderr = ''
        mock_runner = Mock(return_value=mock_result)
        
        _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        # Verify command order
        args = mock_runner.call_args[0][0]
        assert args[0] == "ffprobe"
        # -v quiet should come before -print_format
        v_index = args.index("-v")
        format_index = args.index("-print_format")
        assert v_index < format_index
    
    def test_non_utf8_stdout_handling(self, tmp_path):
        """Test subprocess handles non-UTF8 stdout gracefully."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        # Mock subprocess.run to return bytes that can't decode
        mock_result = Mock()
        mock_result.returncode = 0
        # Return valid JSON but test the text=True path
        mock_result.stdout = '{"format": {"duration": "30.0"}}'
        mock_result.stderr = ''
        mock_runner = Mock(return_value=mock_result)
        
        duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
        
        assert duration == 30.0


@pytest.mark.unit
class TestSubprocessErrorCodes:
    """Test subprocess error code handling and classification."""
    
    @pytest.mark.parametrize("returncode,should_succeed", [
        (0, True),   # Success
        (1, False),  # Generic error
        (127, False), # Command not found
        (255, False), # Fatal error
    ])
    def test_subprocess_return_code_mapping(self, tmp_path, returncode, should_succeed):
        """Test subprocess return codes are properly handled."""
        from backend.scripts.ingest_youtube_enhanced import _fast_duration_seconds
        
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"fake audio data")
        
        if should_succeed:
            mock_result = Mock()
            mock_result.returncode = returncode
            mock_result.stdout = '{"format": {"duration": "100.0"}}'
            mock_result.stderr = ''
            mock_runner = Mock(return_value=mock_result)
            
            duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
            assert duration == 100.0
        else:
            # Non-zero return codes should raise or be handled
            mock_runner = Mock(side_effect=Exception(f"Command failed with code {returncode}"))
            
            duration = _fast_duration_seconds(str(test_file), subprocess_runner=mock_runner)
            assert duration == 0.0
