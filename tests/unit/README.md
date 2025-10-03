# Unit Tests for Ask Dr. Chaffee Backend

Comprehensive unit tests for the ingestion pipeline, focusing on `ingest_youtube_enhanced.py`.

## Test Coverage

### Test Files

1. **`test_ingest_subprocess.py`** - Subprocess pipeline tests
   - GPU telemetry (nvidia-smi)
   - FFprobe duration extraction
   - Command argument validation
   - Error code handling
   - Non-UTF8 output handling
   - Timeout handling

2. **`test_ingest_cleanup.py`** - Cleanup and temp file management
   - Thread-specific temp directories
   - Cleanup on success/failure/KeyboardInterrupt
   - Audio storage configuration
   - Production mode behavior

3. **`test_ingest_config.py`** - Configuration and environment
   - Environment variable overrides
   - Default values
   - Validation logic
   - Secret redaction
   - Whisper preset selection
   - Content hashing

4. **`test_ingest_logging.py`** - Structured logging
   - Performance metrics (RTF, throughput)
   - Speaker attribution breakdown
   - Secret redaction in logs
   - Error logging with context
   - GPU telemetry logging

5. **`test_ingest_concurrency.py`** - Concurrency and queue management
   - Queue limits and FIFO ordering
   - Thread safety
   - Worker coordination
   - Poison pill pattern
   - Stats lock preventing race conditions

6. **`test_ingest_cli.py`** - CLI argument parsing
   - Argument validation
   - Help output
   - Main entry point error handling
   - Edge cases

## Running Tests

### Install Dependencies

```powershell
# Install test dependencies
pip install -r backend/requirements.txt
```

### Run All Unit Tests

```powershell
# Run all unit tests with coverage
pytest -m unit --cov=backend/scripts/ingest_youtube_enhanced.py --cov-branch --cov-report=term-missing -v

# Quick run (no coverage)
pytest -m unit -v

# Parallel execution (faster)
pytest -m unit -n auto
```

### Run Specific Test File

```powershell
# Run subprocess tests only
pytest tests/unit/test_ingest_subprocess.py -v

# Run config tests only
pytest tests/unit/test_ingest_config.py -v
```

### Run Specific Test

```powershell
# Run a single test
pytest tests/unit/test_ingest_subprocess.py::TestSubprocessPipeline::test_telemetry_hook_success -v
```

### Coverage Reports

```powershell
# Generate HTML coverage report
pytest -m unit --cov=backend/scripts/ingest_youtube_enhanced.py --cov-branch --cov-report=html

# Open coverage report
start htmlcov/index.html

# Generate terminal report with missing lines
pytest -m unit --cov=backend/scripts/ingest_youtube_enhanced.py --cov-branch --cov-report=term-missing
```

### Target Coverage Metrics

- **ingest_youtube_enhanced.py**: ≥95% line + branch coverage
- **Overall project**: ≥85% line + branch coverage

## Test Design Principles

### Hermetic Tests
- No real network calls
- No real subprocess execution
- No real file downloads
- All external dependencies mocked

### Windows Compatibility
- Uses `pathlib` for cross-platform paths
- No POSIX-only assumptions
- No `shell=True` in subprocess calls

### Minimal Production Changes
- Added optional `subprocess_runner` parameter to `_telemetry_hook` and `_fast_duration_seconds`
- No behavioral changes to production code
- All CLI flags and signatures preserved

### Test Isolation
- Each test uses `tmp_path` fixture
- Environment variables cleaned between tests
- No shared state between tests

## Fixtures (tests/conftest.py)

- `temp_dir` - Temporary directory (auto-cleanup)
- `mock_env` - Clean environment with minimal vars
- `mock_subprocess_success` - Mock successful subprocess
- `mock_subprocess_failure` - Mock failed subprocess
- `fake_video_info` - Fake VideoInfo object
- `fake_transcript_segment` - Fake transcript segment
- `mock_database_connection` - Mock database
- `capture_structured_logs` - Capture and parse logs

## Edge Cases Covered

1. **Subprocess Errors**
   - Non-zero return codes (1, 127, 255)
   - Timeout exceptions
   - Malformed JSON output
   - Non-UTF8 output
   - Very long stderr

2. **Cleanup Scenarios**
   - Success path
   - Exception path
   - KeyboardInterrupt
   - Multiple temp files
   - Nested directories

3. **Configuration**
   - Missing required env vars
   - Invalid values
   - Boundary conditions
   - Conflicting flags

4. **Concurrency**
   - Race conditions
   - Queue overflow
   - Worker coordination
   - Poison pills
   - Stats updates

5. **Logging**
   - Secret redaction
   - Performance metrics
   - Error context
   - Concurrent logging

## Continuous Integration

Add to CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run unit tests
  run: |
    pytest -m unit --cov=backend/scripts --cov-branch --cov-report=xml --cov-report=term
    
- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
    flags: unittests
```

## Troubleshooting

### Import Errors

```powershell
# Add backend to PYTHONPATH
$env:PYTHONPATH = "c:\Users\hugoa\Desktop\ask-dr-chaffee;c:\Users\hugoa\Desktop\ask-dr-chaffee\backend"
pytest -m unit -v
```

### Slow Tests

```powershell
# Run with timeout
pytest -m unit --timeout=10 -v

# Identify slow tests
pytest -m unit --durations=10
```

### Debugging Failed Tests

```powershell
# Verbose output with full traceback
pytest tests/unit/test_ingest_subprocess.py -vv --tb=long

# Drop into debugger on failure
pytest tests/unit/test_ingest_subprocess.py --pdb

# Show print statements
pytest tests/unit/test_ingest_subprocess.py -s
```

## Next Steps

1. Run tests: `pytest -m unit --cov --cov-branch -v`
2. Review coverage report
3. Add integration tests for end-to-end flows
4. Add performance tests for RTX 5080 optimization validation
