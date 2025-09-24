# Enhanced ASR System v2 - RTX 5080 Optimized

## Overview

The Enhanced ASR System v2 has been upgraded with the highest-quality Whisper models, RTX 5080 optimization, and comprehensive quality assurance features while maintaining full backward compatibility with existing APIs.

## 🚀 What's New in v2

### 🎯 Large-v3 by Default
- **Primary Model:** `large-v3` (highest accuracy available)
- **Fallback Models:** `large-v3-turbo`, `distil-large-v3`, `medium.en`, `small.en`
- **Automatic Fallbacks:** CUDA OOM detection with intelligent model downgrades

### ⚡ RTX 5080 Optimization  
- **CUDA + Float16:** Default precision for RTX 5080's 16GB VRAM
- **Auto-fallback:** `int8_float16` → `int8` on OOM with logging
- **VRAM Monitoring:** Real-time usage tracking and peak memory logging
- **Chunk Length:** Optimized 45-second chunks for maximum throughput

### 🏗️ 12-Factor Configuration
- **Environment Variables:** All settings configurable via env vars
- **CLI Overrides:** Command-line arguments override environment settings  
- **Quality-First Defaults:** Beam size 6, VAD enabled, temperature arrays
- **Domain Prompts:** Specialized for medical/nutrition content

### 🔍 Two-Pass Quality Assurance
- **Low Confidence Detection:** Auto-detect segments needing improvement
- **Stricter Re-processing:** Higher beam size + extended temperature range
- **Quality Metrics:** avg_logprob, compression_ratio, no_speech_prob tracking
- **Improvement Validation:** Replace only if demonstrably better

### 📊 Comprehensive Benchmarking
- **Multi-Model Testing:** Automated benchmarking across all model sizes
- **Performance Metrics:** RTF, speed factors, VRAM usage, quality scores
- **Detailed Reports:** Markdown, JSON, and CSV outputs
- **Model Recommendations:** Based on use case and available hardware

## Configuration

### Environment Variables

#### Whisper Model Configuration
```bash
# Model Selection (quality-first by default)
export WHISPER_MODEL=large-v3              # large-v3, large-v3-turbo, distil-large-v3
export WHISPER_DEVICE=cuda                 # cuda, cpu
export WHISPER_COMPUTE=float16             # float16, int8_float16, int8

# Quality-First Inference  
export WHISPER_BEAM=6                      # Beam search size
export WHISPER_CHUNK=45                    # Chunk length in seconds
export WHISPER_VAD=true                    # Voice activity detection
export WHISPER_LANG=en                     # Language code
export WHISPER_TASK=transcribe             # transcribe, translate
export WHISPER_TEMPS="0.0,0.2,0.4"        # Temperature array

# Domain-Specific Prompt for Medical/Nutrition Content
export DOMAIN_PROMPT="ketogenesis linoleic acid LDL statins seed oils DHA EPA taurine oxalates gout uric acid mTOR autoimmunity cholecystectomy"
```

#### Quality Assurance Configuration
```bash
# Two-Pass QA Settings
export QA_TWO_PASS=true                    # Enable two-pass quality assurance
export QA_LOW_LOGPROB=-0.35                # Low confidence threshold (avg_logprob)
export QA_LOW_COMPRESSION=2.4              # Low confidence threshold (compression_ratio)
export QA_RETRY_BEAM=8                     # Beam size for retry attempts
export QA_RETRY_TEMPS="0.0,0.2,0.4,0.6"   # Temperature array for retries
```

#### Word Alignment & Diarization
```bash
export ALIGN_WORDS=true                    # Enable word-level alignment
export DIARIZE=false                       # Enable speaker diarization (default off)
export MIN_SPEAKERS=1                      # Minimum speakers for diarization
export MAX_SPEAKERS=10                     # Maximum speakers for diarization
```

#### Legacy Speaker ID (Backward Compatibility)
```bash
export CHAFFEE_MIN_SIM=0.82               # Chaffee similarity threshold
export GUEST_MIN_SIM=0.82                 # Guest similarity threshold  
export ATTR_MARGIN=0.05                   # Attribution margin requirement
export OVERLAP_BONUS=0.03                 # Overlap penalty bonus
export ASSUME_MONOLOGUE=true              # Monologue fast-path
export UNKNOWN_LABEL=Unknown              # Unknown speaker label
export VOICES_DIR=voices                  # Voice profiles directory
```

## Usage Examples

### Basic High-Quality Transcription
```bash
# Default: large-v3 with quality-first settings
python asr_cli.py transcribe interview.wav --output results.json

# Configuration will be logged:
# [MODEL]  Whisper model: large-v3
# [DEVICE] Device: cuda  
# [COMPUTE] Compute type: float16
# [BEAM]   Beam size: 6
# [QA]     Two-pass QA: true
```

### Custom Model Selection
```bash
# Speed-optimized for real-time processing
python asr_cli.py transcribe stream.wav \
  --model small.en \
  --compute-type int8 \
  --beam-size 1 \
  --disable-two-pass

# Efficiency-optimized for batch processing
python asr_cli.py transcribe batch.wav \
  --model distil-large-v3 \
  --compute-type int8_float16 \
  --chunk-length 60
```

### Domain-Specific Processing
```bash
# Medical terminology optimization
python asr_cli.py transcribe medical_lecture.wav \
  --domain-prompt "ketogenesis cholesterol statins LDL HDL metabolism" \
  --beam-size 8 \
  --chunk-length 30
```

### Advanced Quality Control
```bash
# Maximum quality with extended QA
python asr_cli.py transcribe important.wav \
  --model large-v3 \
  --beam-size 8 \
  --disable-vad \
  --chunk-length 30
```

### Environment-Based Configuration
```bash
# Set environment for production workload
export WHISPER_MODEL=large-v3
export WHISPER_COMPUTE=float16
export WHISPER_BEAM=6
export QA_TWO_PASS=true
export DOMAIN_PROMPT="medical nutrition ketogenic"

# All subsequent transcriptions use these settings
python asr_cli.py transcribe file1.wav --output results1.json
python asr_cli.py transcribe file2.wav --output results2.json
```

## Benchmarking

### Run Comprehensive Benchmark
```bash
# Benchmark all models on your hardware
python bench_asr.py --samples-dir ./test_audio --output-dir ./reports

# Benchmark specific models
python bench_asr.py \
  --samples-dir ./test_audio \
  --models large-v3 large-v3-turbo distil-large-v3 \
  --compute-types float16 int8_float16 \
  --output-dir ./benchmark_results
```

### Benchmark Output
- **`asr_bench.md`**: Detailed markdown report with recommendations
- **`benchmark_summary.json`**: Complete results data
- **`performance_matrix.csv`**: Spreadsheet-compatible metrics

### Sample Benchmark Results
```
## Model Performance Ranking

| Model           | Avg RTF | Avg Quality | Avg VRAM (GB) | Speed Rank | Quality Rank |
|-----------------|---------|-------------|---------------|------------|--------------|
| large-v3        | 0.31x   | -0.156      | 3.2           | #6         | #1           |
| large-v3-turbo  | 0.22x   | -0.168      | 3.0           | #3         | #2           |
| distil-large-v3 | 0.16x   | -0.189      | 2.1           | #2         | #3           |
| medium.en       | 0.14x   | -0.223      | 1.5           | #1         | #4           |

**Balanced Choice:** `large-v3-turbo` (speed rank #3, quality rank #2)

**VRAM Requirements:**
- 16GB RTX 5080: Any model with float16
- 12GB RTX 4090: large-v3 with int8_float16
- 8GB RTX 4070: distil-large-v3 or medium.en
- 6GB RTX 4060: small.en or base.en
```

## Model Selection Guide

### By Use Case

| Use Case | Recommended Model | Compute Type | Expected RTF | Best For |
|----------|-------------------|--------------|--------------|----------|
| **Maximum Quality** | `large-v3` | `float16` | 0.3x | Critical transcriptions |
| **Balanced Performance** | `large-v3-turbo` | `float16` | 0.22x | General production use |
| **High Throughput** | `distil-large-v3` | `int8_float16` | 0.16x | Batch processing |
| **Real-Time** | `small.en` | `int8` | 0.08x | Live transcription |

### By Hardware

| GPU | VRAM | Recommended Model | Compute Type | Max Concurrent |
|-----|------|-------------------|--------------|----------------|
| **RTX 5080** | 16GB | `large-v3` | `float16` | 5-6 streams |
| **RTX 4090** | 24GB | `large-v3` | `float16` | 7-8 streams |
| **RTX 4080** | 16GB | `large-v3` | `float16` | 5-6 streams |
| **RTX 4070 Ti** | 12GB | `large-v3-turbo` | `int8_float16` | 4-5 streams |
| **RTX 4070** | 12GB | `distil-large-v3` | `int8_float16` | 6-7 streams |
| **RTX 4060 Ti** | 8GB | `medium.en` | `int8_float16` | 5-6 streams |

## Quality Features

### Two-Pass Quality Assurance
```bash
# Automatically enabled - will retry low-confidence segments
[QA] Found 3 low-confidence segments, performing two-pass QA
[QA] Low confidence: 45.2-48.7s, logprob=-0.456, compression=2.8
[QA] Low confidence: 72.1-75.3s, logprob=-0.389, compression=2.6  
[QA] Low confidence: 118.8-121.2s, logprob=-0.421, compression=3.1
[QA] Two-pass QA completed: 3 segments processed, 2 improved
```

### Quality Metrics Logging
```bash
=== Quality Metrics ===
Average log probability: -0.234
Average compression ratio: 1.78
Average no-speech probability: 0.086
Low confidence segments: 2/24 (8.3%)
VRAM usage: 3.2GB (peak: 3.8GB)
```

### Domain Prompt Optimization
The system includes a specialized prompt for Dr. Chaffee's content:
```
"ketogenesis linoleic acid LDL statins seed oils DHA EPA taurine 
oxalates gout uric acid mTOR autoimmunity cholecystectomy"
```

This improves recognition of:
- ✅ Medical terminology
- ✅ Nutritional compounds  
- ✅ Biochemical processes
- ✅ Health conditions
- ✅ Supplement names

## VRAM Safety & Fallbacks

### Automatic OOM Handling
```bash
[WARNING] CUDA OOM with large-v3 (float16), trying fallbacks...
[INFO] Trying fallback compute type: int8_float16
[INFO] Trying smaller chunk length: 30s
[INFO] Trying fallback model: large-v3-turbo
[SUCCESS] Fallback successful: large-v3-turbo with int8_float16
```

### Fallback Hierarchy
1. **Compute Type Fallbacks:** `float16` → `int8_float16` → `int8`
2. **Chunk Length Fallbacks:** `45s` → `30s` → `20s` → `15s`  
3. **Model Fallbacks:** `large-v3` → `large-v3-turbo` → `distil-large-v3` → `medium.en`

### Manual Fallback Configuration
```bash
# Force specific fallback settings
export WHISPER_MODEL=distil-large-v3
export WHISPER_COMPUTE=int8_float16  
export WHISPER_CHUNK=30
export ENABLE_FALLBACK=false         # Disable auto-fallback
```

## Performance Optimization

### RTX 5080 Specific Settings
```bash
# Optimized for RTX 5080 (16GB VRAM)
export WHISPER_MODEL=large-v3
export WHISPER_COMPUTE=float16
export WHISPER_CHUNK=45
export WHISPER_BEAM=6

# Expected performance:
# - Single stream: ~0.3x real-time
# - Quality: -0.15 avg_logprob  
# - VRAM usage: ~3.2GB
# - Concurrent streams: 5-6 max
```

### Memory Management
```bash
# Conservative memory usage
export WHISPER_MODEL=distil-large-v3
export WHISPER_COMPUTE=int8_float16
export WHISPER_CHUNK=30

# Aggressive performance (requires 16GB+ VRAM)
export WHISPER_MODEL=large-v3
export WHISPER_COMPUTE=float16
export WHISPER_CHUNK=60
export WHISPER_BEAM=8
```

## Integration with YouTube Ingestion

The enhanced ASR integrates seamlessly with the existing YouTube ingestion pipeline:

```bash
# Use enhanced ASR for YouTube ingestion
python ingest_youtube_enhanced_asr.py VIDEO_ID \
  --use-enhanced-asr \
  --whisper-model large-v3 \
  --enable-speaker-id

# Bulk processing with optimized settings
python ingest_youtube_enhanced_asr.py --batch \
  --whisper-model large-v3-turbo \
  --compute-type int8_float16 \
  --parallel-workers 4
```

## API Reference

### Python API
```python
from backend.scripts.common.enhanced_asr import EnhancedASR
from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig

# Create configuration
config = EnhancedASRConfig(
    model='large-v3',
    compute_type='float16',
    beam_size=6,
    enable_two_pass=True,
    initial_prompt='medical nutrition ketogenic'
)

# Initialize ASR
asr = EnhancedASR(config)

# Transcribe with runtime overrides
result = asr.run('audio.wav', 
                 model='large-v3-turbo',  # Runtime override
                 beam_size=8)             # Runtime override

# Access results
print(f"Text: {result.text}")
print(f"Quality: {result.metadata['quality_metrics']}")
print(f"Two-pass QA: {result.metadata['two_pass_qa']}")
```

### Configuration Classes
```python
# Whisper-specific configuration
config.whisper.model              # Model name
config.whisper.device              # cuda/cpu  
config.whisper.compute_type        # float16/int8_float16/int8
config.whisper.beam_size           # Beam search size
config.whisper.chunk_length        # Chunk length in seconds
config.whisper.vad_filter          # VAD enabled/disabled
config.whisper.temperature         # Temperature array
config.whisper.initial_prompt      # Domain prompt

# Quality assurance configuration  
config.quality.enable_two_pass     # Two-pass QA enabled
config.quality.low_conf_avg_logprob    # Low confidence threshold
config.quality.retry_beam_size     # Retry beam size

# Alignment configuration
config.alignment.enable_alignment  # Word alignment
config.alignment.enable_diarization # Speaker diarization
```

## Migration Guide

### From v1 to v2

**✅ Backward Compatible:** All existing code continues to work unchanged.

**Environment Variables:** Update your environment variables to use the new options:
```bash
# Old (still works)
export WHISPER_MODEL=base.en

# New (recommended)  
export WHISPER_MODEL=large-v3
export WHISPER_COMPUTE=float16
export WHISPER_BEAM=6
export QA_TWO_PASS=true
```

**CLI Arguments:** New arguments available, old ones still supported:
```bash
# Old (still works)
python asr_cli.py transcribe audio.wav --whisper-model large-v2

# New (recommended)
python asr_cli.py transcribe audio.wav --model large-v3 --compute-type float16
```

**Configuration Objects:** Import from the new config module:
```python
# Old (still works)
from backend.scripts.common.enhanced_asr import EnhancedASRConfig

# New (recommended)
from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig
```

## Troubleshooting

### CUDA Out of Memory
```bash
# Error indicators
[ERROR] CUDA OOM with large-v3 (float16)
[ERROR] All fallbacks failed

# Solutions
export WHISPER_MODEL=distil-large-v3  # Use smaller model
export WHISPER_COMPUTE=int8_float16   # Use lower precision  
export WHISPER_CHUNK=30               # Use smaller chunks
export ENABLE_FALLBACK=true           # Enable auto-fallback
```

### Poor Quality Results
```bash
# Check quality metrics in output
"quality_metrics": {
  "avg_logprob_mean": -0.456,        # Should be > -0.35
  "compression_ratio_mean": 2.8,     # Should be < 2.4  
  "low_conf_percentage": 15.2        # Should be < 10%
}

# Solutions
export WHISPER_BEAM=8               # Increase beam size
export QA_TWO_PASS=true            # Enable two-pass QA
export WHISPER_CHUNK=30            # Use smaller chunks
```

### Slow Performance
```bash
# Check real-time factor in logs
[INFO] Processing time: 45.2s (0.85x RT, 1.18x speed)

# Solutions  
export WHISPER_MODEL=large-v3-turbo  # Use faster model
export WHISPER_COMPUTE=int8_float16   # Use faster precision
export WHISPER_BEAM=1                # Reduce beam size
export QA_TWO_PASS=false             # Disable two-pass QA
```

## Testing

Run the enhanced test suite:
```bash
# Full test suite including new features
python test_enhanced_asr.py

# Specific test categories
python -m unittest TestEnhancedASRConfig    # Configuration tests
python -m unittest TestQualityAssurance     # Two-pass QA tests  
python -m unittest TestVoiceEnrollment      # Speaker ID tests
```

---

## Summary

Enhanced ASR System v2 delivers:

✅ **Highest Quality:** Large-v3 model with domain optimization  
✅ **RTX 5080 Optimized:** Maximum VRAM utilization with safety fallbacks  
✅ **Quality Assurance:** Two-pass processing for low-confidence segments  
✅ **12-Factor Config:** Environment-driven configuration with CLI overrides  
✅ **Comprehensive Testing:** Automated benchmarking and quality validation  
✅ **Backward Compatible:** All existing APIs and configurations preserved  
✅ **Production Ready:** VRAM monitoring, fallback handling, detailed logging  

The system automatically adapts to your hardware capabilities while delivering the highest possible transcription quality for Dr. Chaffee's content.
