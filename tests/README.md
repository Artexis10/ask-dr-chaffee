# Tests Directory

This directory contains the test suite for the Ask Dr. Chaffee project, organized by test type and functionality.

## Structure

- **`unit/`** - Small, focused unit tests for individual components
- **`integration/`** - Full pipeline and system integration tests
- **`performance/`** - Speed, load, and performance validation tests
- **`enhanced_asr/`** - Enhanced ASR and speaker identification specific tests

## Running Tests

### All Tests
```bash
python -m pytest tests/ -v
```

### By Category
```bash
# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests only  
python -m pytest tests/integration/ -v

# Performance tests only
python -m pytest tests/performance/ -v

# Enhanced ASR tests only
python -m pytest tests/enhanced_asr/ -v
```

### Individual Tests
```bash
# Run specific test file
python -m pytest tests/unit/test_embedding_model.py -v

# Run specific test function
python -m pytest tests/integration/test_mvp_pipeline.py::test_full_pipeline -v
```

## Test Categories

### Unit Tests
Focus on testing individual functions and classes in isolation. These should be fast and not require external dependencies.

### Integration Tests
Test full workflows and system integration. These may require database access, external APIs, or file system operations.

### Performance Tests
Validate processing speed, memory usage, and system performance under load. These may take longer to run.

### Enhanced ASR Tests
Specialized tests for Enhanced ASR functionality including speaker identification, voice enrollment, and diarization features.

## Development Guidelines

- Keep unit tests fast and isolated
- Use mocks for external dependencies in unit tests
- Integration tests should use test data when possible
- Performance tests should have clear benchmarks
- Add new tests when adding new functionality
