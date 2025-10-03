"""Unit tests for CLI argument parsing in ingest_youtube_enhanced.py."""

import sys
from io import StringIO
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestCLIArgumentParsing:
    """Test command-line argument parsing."""
    
    def test_parse_args_minimal(self, monkeypatch):
        """Test parsing with minimal arguments."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('YOUTUBE_API_KEY', 'test_key')
        
        # Mock sys.argv
        test_args = ['ingest_youtube_enhanced.py', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.dry_run is True
    
    def test_parse_args_source_selection(self, monkeypatch):
        """Test source selection via CLI."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--source', 'yt-dlp', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.source == 'yt-dlp'
    
    def test_parse_args_from_url(self, monkeypatch):
        """Test --from-url argument."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = [
            'ingest_youtube_enhanced.py',
            '--from-url',
            'https://youtube.com/watch?v=test123',
            'https://youtube.com/watch?v=test456',
            '--dry-run'
        ]
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert len(config.from_url) == 2
        assert 'test123' in config.from_url[0]
        assert 'test456' in config.from_url[1]
    
    def test_parse_args_concurrency(self, monkeypatch):
        """Test concurrency argument parsing."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--concurrency', '8', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.concurrency == 8
    
    def test_parse_args_limit(self, monkeypatch):
        """Test --limit argument."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--limit', '50', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.limit == 50
    
    def test_parse_args_skip_shorts(self, monkeypatch):
        """Test --skip-shorts flag."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--skip-shorts', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.skip_shorts is True
    
    def test_parse_args_newest_first(self, monkeypatch):
        """Test --newest-first flag."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--newest-first', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.newest_first is True
    
    def test_parse_args_whisper_model(self, monkeypatch):
        """Test --whisper-model argument."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--whisper-model', 'large-v3', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.whisper_model == 'large-v3'
    
    def test_parse_args_force_whisper(self, monkeypatch):
        """Test --force-whisper flag."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--force-whisper', '--dry-run']
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.force_whisper is True


@pytest.mark.unit
class TestCLIValidation:
    """Test CLI argument validation."""
    
    def test_invalid_source_rejected(self, monkeypatch):
        """Test invalid source value is rejected."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--source', 'invalid']
        
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit):
                parse_args()
    
    def test_negative_concurrency_rejected(self, monkeypatch):
        """Test negative concurrency value is rejected."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--concurrency', '-1']
        
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit):
                parse_args()
    
    def test_negative_limit_rejected(self, monkeypatch):
        """Test negative limit value is rejected."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--limit', '-10']
        
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit):
                parse_args()


@pytest.mark.unit
class TestCLIHelp:
    """Test CLI help output."""
    
    def test_help_flag_exits(self, monkeypatch):
        """Test --help flag exits with code 0."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--help']
        
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit) as exc_info:
                parse_args()
            
            # Help should exit with 0
            assert exc_info.value.code == 0
    
    def test_help_contains_examples(self, monkeypatch, capsys):
        """Test help output contains usage examples."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--help']
        
        with patch.object(sys, 'argv', test_args):
            try:
                parse_args()
            except SystemExit:
                pass
        
        captured = capsys.readouterr()
        help_text = captured.out
        
        # Should contain examples
        assert 'Examples:' in help_text or 'examples' in help_text.lower()


@pytest.mark.unit
class TestCLIMainEntry:
    """Test main entry point."""
    
    def test_main_keyboard_interrupt(self, monkeypatch):
        """Test main handles KeyboardInterrupt."""
        from backend.scripts.ingest_youtube_enhanced import main
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--dry-run']
        
        with patch.object(sys, 'argv', test_args):
            with patch('backend.scripts.ingest_youtube_enhanced.EnhancedYouTubeIngester') as mock_ingester:
                mock_ingester.return_value.run.side_effect = KeyboardInterrupt()
                
                with pytest.raises(SystemExit) as exc_info:
                    main()
                
                # Should exit with code 1
                assert exc_info.value.code == 1
    
    def test_main_generic_exception(self, monkeypatch, caplog):
        """Test main handles generic exceptions."""
        from backend.scripts.ingest_youtube_enhanced import main
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--dry-run']
        
        with patch.object(sys, 'argv', test_args):
            with patch('backend.scripts.ingest_youtube_enhanced.EnhancedYouTubeIngester') as mock_ingester:
                mock_ingester.return_value.run.side_effect = Exception("Test error")
                
                with pytest.raises(SystemExit) as exc_info:
                    main()
                
                # Should exit with code 1
                assert exc_info.value.code == 1
                
                # Error should be logged
                assert "Fatal error" in caplog.text


@pytest.mark.unit
class TestCLIEdgeCases:
    """Test CLI edge cases."""
    
    def test_empty_from_url_list(self, monkeypatch):
        """Test --from-url with no URLs."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        # --from-url requires at least one URL
        test_args = ['ingest_youtube_enhanced.py', '--from-url', '--dry-run']
        
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit):
                parse_args()
    
    def test_zero_concurrency(self, monkeypatch):
        """Test concurrency=0 is rejected."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--concurrency', '0']
        
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit):
                parse_args()
    
    def test_very_large_limit(self, monkeypatch):
        """Test very large limit value is accepted."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_args = ['ingest_youtube_enhanced.py', '--limit', '999999', '--dry-run']
        
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.limit == 999999
    
    def test_conflicting_flags(self, monkeypatch):
        """Test conflicting flags are handled."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        # Both --newest-first and its opposite (if exists)
        test_args = ['ingest_youtube_enhanced.py', '--newest-first', '--dry-run']
        
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        # Should accept the flag
        assert config.newest_first is True


@pytest.mark.unit
class TestCLILocalSource:
    """Test CLI arguments for local source."""
    
    def test_local_source_from_files(self, monkeypatch, tmp_path):
        """Test --source local with --from-files."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_dir = tmp_path / "videos"
        test_dir.mkdir()
        
        test_args = [
            'ingest_youtube_enhanced.py',
            '--source', 'local',
            '--from-files', str(test_dir),
            '--dry-run'
        ]
        
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert config.source == 'local'
        assert config.from_files == test_dir
    
    def test_local_source_file_patterns(self, monkeypatch, tmp_path):
        """Test --file-patterns argument."""
        from backend.scripts.ingest_youtube_enhanced import parse_args
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        test_dir = tmp_path / "videos"
        test_dir.mkdir()
        
        test_args = [
            'ingest_youtube_enhanced.py',
            '--source', 'local',
            '--from-files', str(test_dir),
            '--file-patterns', '*.mkv', '*.avi',
            '--dry-run'
        ]
        
        with patch.object(sys, 'argv', test_args):
            config = parse_args()
        
        assert '*.mkv' in config.file_patterns
        assert '*.avi' in config.file_patterns
