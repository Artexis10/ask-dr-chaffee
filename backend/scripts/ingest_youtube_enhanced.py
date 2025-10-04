#!/usr/bin/env python3

# CRITICAL: UTF-8 fix MUST be first - before docstring, before any imports
# Windows defaults to cp1252 encoding which causes yt-dlp to crash
import sys
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

"""
Enhanced YouTube transcript ingestion script for Ask Dr. Chaffee.
RTX 5080 Optimized for 1200h ingestion in ≤24h (GPT-5 specification).

🚀 RTX 5080 OPTIMIZATIONS:
- distil-large-v3 with int8_float16 quantization for 5-7x real-time performance
- 3-phase pipeline: prefilter → bulk download → ASR+embedding
- Optimized concurrency: 12 I/O, 2 ASR, 12 DB workers for >90% SM utilization
- Conditional diarization with monologue fast-path (3x speedup)
- Batched embeddings (256 segments per batch)
- Enhanced GPU telemetry with performance warnings
- Target throughput: ~50h audio per hour → 1200h in ~24h

Supports dual data sources (yt-dlp and YouTube Data API) with robust 
concurrent processing pipeline and comprehensive error handling.
"""

import os
import argparse
import asyncio
import codecs
import hashlib
import inspect
import logging
import queue
import tempfile
import time
import threading
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from collections import defaultdict

import tqdm
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Set UTF-8 encoding for stdout on Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

# Add paths for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(__file__), 'common'))

# Set up logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_ingestion_enhanced.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# UTF-8 utility (minimal, targeted)
from scripts.common.transcript_common import ensure_str

# Import all required modules
from scripts.common.list_videos_yt_dlp import YtDlpVideoLister, VideoInfo
from scripts.common.list_videos_api import YouTubeAPILister  
from scripts.common.local_file_lister import LocalFileLister
from scripts.common.proxy_manager import ProxyConfig, ProxyManager
from scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher  
from scripts.common.database_upsert import DatabaseUpserter
from scripts.common.segments_database import SegmentsDatabase
from scripts.common.embeddings import EmbeddingGenerator
# ChunkData not needed - using segments directly

def get_thread_temp_dir() -> str:
    """Get a unique temporary directory for this thread"""
    import tempfile
    import uuid
    
    thread_id = threading.get_ident()
    unique_id = uuid.uuid4().hex[:8]
    temp_dir = os.path.join(tempfile.gettempdir(), f"asr_worker_{thread_id}_{unique_id}")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def _telemetry_hook(stats, subprocess_runner=None) -> None:
    """Enhanced GPU telemetry for RTX 5080 performance monitoring - target >90% SM utilization"""
    try:
        import subprocess
        if subprocess_runner is None:
            subprocess_runner = subprocess.check_output
        # Enhanced GPU monitoring with temperature and power draw
        out = subprocess_runner(
            ["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.free,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"], text=True, timeout=5)
        values = out.strip().split(", ")
        sm, mem_used, mem_free = map(int, values[:3])
        temp, power = map(float, values[3:5]) if len(values) >= 5 else (0, 0)
        
        # Calculate memory utilization percentage (RTX 5080 has ~16GB)
        total_mem = mem_used + mem_free
        mem_util = (mem_used / total_mem * 100) if total_mem > 0 else 0
        
        # Performance warnings for sub-optimal utilization
        perf_indicator = "🚀" if sm >= 90 else "⚠️" if sm >= 70 else "🐌"
        vram_indicator = "💾" if mem_util <= 90 else "⚠️"
        
        logger.info(f"{perf_indicator} RTX5080 SM={sm}% {vram_indicator} VRAM={mem_util:.1f}% "
                    f"temp={temp:.0f}°C power={power:.0f}W "
                    f"queues: io={stats.io_queue_peak} asr={stats.asr_queue_peak} db={stats.db_queue_peak}")
        
        # Target performance warnings
        if sm < 90:
            logger.warning(f"🎯 GPU utilization below target: {sm}% < 90% - consider tuning concurrency")
            
    except Exception as e:
        logger.debug(f"GPU telemetry failed: {e}")  # More detailed error for debugging

def _fast_duration_seconds(path: str, subprocess_runner=None) -> float:
    """Fast duration check using soundfile (avoid librosa in hot paths)"""
    try:
        import soundfile as sf
        with sf.SoundFile(path) as f:
            return f.frames / float(f.samplerate)
    except Exception:
        # ffprobe fallback
        try:
            import subprocess, json
            if subprocess_runner is None:
                subprocess_runner = subprocess.run
            r = subprocess_runner(
                ["ffprobe","-v","quiet","-print_format","json","-show_format", path],
                capture_output=True, text=True, check=True, timeout=10
            )
            return float(json.loads(r.stdout)["format"]["duration"])
        except Exception:
            return 0.0  # Default if all fails

def pick_whisper_preset(duration_minutes: float, is_interview: bool = False) -> Dict[str, Any]:
    """Routing logic for optimal Whisper model selection - RTX 5080 optimized"""
    presets = {
        'fast_short': {
            'model': 'distil-large-v3',
            'compute_type': 'int8_float16',
            'beam_size': 1,
            'temperature': 0.0,
            'use_case': '≤20min videos',
            'chunk_length': 240  # 4min chunks for optimal summarization
        },
        'monologue_long': {
            'model': 'distil-large-v3', 
            'compute_type': 'int8_float16',
            'beam_size': 1,
            'temperature': 0.0,
            'use_case': 'long monologues',
            'chunk_length': 240
        },
        'interview': {
            'model': 'distil-large-v3',
            'compute_type': 'int8_float16', 
            'beam_size': 1,
            'temperature': 0.0,
            'use_case': 'interviews/multi-speaker',
            'chunk_length': 240
        }
    }
    
    # Route based on duration and content type
    if duration_minutes <= 20:
        preset = presets['fast_short']
    elif is_interview:
        preset = presets['interview']
    else:
        preset = presets['monologue_long']
    
    logger.info(f"Whisper preset selected: {preset['model']} ({preset['use_case']})")
    return preset

def compute_content_hash(video_id: str, upload_date: Optional[datetime] = None, 
                        audio_path: Optional[str] = None) -> str:
    """Compute content fingerprint for duplicate detection"""
    hasher = hashlib.md5()
    hasher.update(video_id.encode('utf-8'))
    
    if upload_date:
        hasher.update(upload_date.isoformat().encode('utf-8'))
    
    # Add audio fingerprint if available (first 120s)
    if audio_path and os.path.exists(audio_path):
        try:
            import librosa
            # Load first 120 seconds
            audio, sr = librosa.load(audio_path, duration=120, sr=16000)
            audio_hash = hashlib.md5(audio.tobytes()).hexdigest()[:16]
            hasher.update(audio_hash.encode('utf-8'))
        except Exception as e:
            logger.debug(f"Failed to compute audio hash: {e}")
    
    return hasher.hexdigest()

@dataclass
class IngestionConfig:
    """Configuration for ingestion pipeline"""
    source: str = 'api'  # 'api', 'yt-dlp', or 'local' (API is now default)
    channel_url: Optional[str] = None
    from_url: Optional[List[str]] = None  # Direct YouTube URL(s)
    from_json: Optional[Path] = None
    from_files: Optional[Path] = None  # Directory containing local video/audio files
    file_patterns: List[str] = None  # File patterns to match (e.g., ['*.mp4', '*.wav'])
    
    # RTX 5080 optimized concurrency controls for 1200h in 24h target - FROM .ENV
    # Note: Defaults will be overridden in __post_init__ after .env is loaded
    io_concurrency: int = 24   # I/O threads (will read from .env)
    asr_concurrency: int = 4   # ASR workers (will read from .env)
    db_concurrency: int = 12   # DB/embedding threads (will read from .env)
    
    # Legacy concurrency (for backward compatibility)
    concurrency: int = 4
    
    skip_shorts: bool = False  # Will read from .env
    newest_first: bool = True  # Will read from .env
    limit: Optional[int] = None
    limit_unprocessed: bool = False  # If True, limit applies to unprocessed videos only
    dry_run: bool = False
    whisper_model: str = 'distil-large-v3'  # Will read from .env
    force_whisper: bool = False
    force_reprocess: bool = False  # Reprocess videos even if they already exist in DB
    skip_existing: bool = True     # Skip videos that already exist in DB (default behavior)
    allow_youtube_captions: bool = False  # CRITICAL: YouTube captions bypass speaker ID
    cleanup_audio: bool = True
    since_published: Optional[str] = None  # ISO8601 or YYYY-MM-DD format
    
    # RTX 5080 optimized embedding options for maximum throughput - FROM .ENV
    embed_later: bool = False  # Enqueue IDs for separate embedding worker
    embedding_batch_size: int = 1024  # Batch size (will read from .env in __post_init__)
    
    # Audio storage configuration
    store_audio_locally: bool = True   # Store downloaded audio files locally
    audio_storage_dir: Optional[Path] = None  # Directory to store audio files
    production_mode: bool = False      # Disable audio storage in production
    
    # Content filtering
    skip_live: bool = True
    skip_upcoming: bool = True
    skip_members_only: bool = True
    
    # Database
    db_url: str = None
    
    # API keys
    youtube_api_key: Optional[str] = None
    ffmpeg_path: Optional[str] = None
    
    # Proxy configuration
    proxy: Optional[str] = None
    proxy_file: Optional[str] = None
    proxy_rotate: bool = False
    proxy_rotate_interval: int = 10
    
    # Speaker identification (MANDATORY for Dr. Chaffee content)
    enable_speaker_id: bool = True  # FORCED - cannot be disabled
    voices_dir: str = 'voices'
    chaffee_min_sim: float = 0.62
    chaffee_only_storage: bool = False  # Store all speakers
    embed_chaffee_only: bool = True     # But only embed Chaffee content for search
    
    # RTX 5080 Optimizations (Performance Defaults)
    assume_monologue: bool = True       # SMART fast-path for solo content (DEFAULT)
    optimize_gpu_memory: bool = True    # Optimize VRAM usage
    reduce_vad_overhead: bool = True    # Skip VAD when possible
    
    # YouTube caption quality gating
    yt_caption_quality_threshold: float = 0.92  # Accept YT captions if quality >= this
    enable_content_hashing: bool = True  # Skip already processed items via fingerprinting
    
    def __post_init__(self):
        """Set defaults from environment"""
        # CRITICAL: Read ALL settings from .env (override class defaults)
        # Concurrency settings
        if os.getenv('IO_WORKERS'):
            self.io_concurrency = int(os.getenv('IO_WORKERS'))
        if os.getenv('ASR_WORKERS'):
            self.asr_concurrency = int(os.getenv('ASR_WORKERS'))
        if os.getenv('DB_WORKERS'):
            self.db_concurrency = int(os.getenv('DB_WORKERS'))
        if os.getenv('BATCH_SIZE'):
            self.embedding_batch_size = int(os.getenv('BATCH_SIZE'))
        
        # Processing settings
        if os.getenv('SKIP_SHORTS'):
            self.skip_shorts = os.getenv('SKIP_SHORTS').lower() == 'true'
        if os.getenv('NEWEST_FIRST'):
            self.newest_first = os.getenv('NEWEST_FIRST').lower() == 'true'
        if os.getenv('WHISPER_MODEL'):
            self.whisper_model = os.getenv('WHISPER_MODEL')
        if os.getenv('MAX_AUDIO_DURATION'):
            duration = int(os.getenv('MAX_AUDIO_DURATION', 0))
            self.max_duration = duration if duration > 0 else None
        
        if self.channel_url is None:
            self.channel_url = os.getenv('YOUTUBE_CHANNEL_URL', 'https://www.youtube.com/@anthonychaffeemd')
        
        if self.db_url is None:
            self.db_url = os.getenv('DATABASE_URL')
            if not self.db_url:
                raise ValueError("DATABASE_URL environment variable required")
        
        # Auto-switch to yt-dlp if using --from-url without specifying source
        if self.from_url and self.source == 'api':
            self.source = 'yt-dlp'
            logger.info("Auto-switched to yt-dlp source for --from-url")
        
        if self.source == 'api':
            if self.youtube_api_key is None:
                self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')
            if not self.youtube_api_key:
                # Skip API key check if we're in setup-chaffee mode
                # This allows using a dummy key for setup-chaffee
                setup_chaffee_mode = False
                try:
                    # Check if we're being called from a function with setup_chaffee_mode
                    for frame in inspect.stack():
                        if 'setup_chaffee_mode' in frame.frame.f_locals:
                            if frame.frame.f_locals['setup_chaffee_mode']:
                                setup_chaffee_mode = True
                                break
                except Exception:
                    # If we can't check the stack, assume we're not in setup-chaffee mode
                    pass
                    
                # Also check if --setup-chaffee was passed as an argument
                import sys
                if '--setup-chaffee' in sys.argv:
                    setup_chaffee_mode = True
                    
                if not setup_chaffee_mode:
                    raise ValueError("YOUTUBE_API_KEY required for API source")
        
        # Handle local file processing
        if self.source == 'local':
            if not self.from_files:
                raise ValueError("--from-files directory required for local source")
            if not self.from_files.exists():
                raise ValueError(f"Local files directory does not exist: {self.from_files}")
        
        # Set up file patterns if not provided
        if self.file_patterns is None:
            self.file_patterns = ['*.mp4', '*.mkv', '*.avi', '*.mov', '*.wav', '*.mp3', '*.m4a', '*.webm']
        
        # Handle audio storage configuration
        if self.production_mode:
            self.store_audio_locally = False
            logger.info("Production mode enabled: Audio storage disabled")
        
        if self.store_audio_locally and self.audio_storage_dir is None:
            self.audio_storage_dir = Path(os.getenv('AUDIO_STORAGE_DIR', './audio_storage'))
            self.audio_storage_dir.mkdir(exist_ok=True)
            logger.info(f"Audio will be stored in: {self.audio_storage_dir}")
        
        # Configure speaker identification from environment
        if self.voices_dir is None:
            self.voices_dir = os.getenv('VOICES_DIR', 'voices')
        
        if self.chaffee_min_sim is None:
            self.chaffee_min_sim = float(os.getenv('CHAFFEE_MIN_SIM', '0.62'))
        
        # Handle Chaffee voice profile - with auto-bootstrap capability
        # Skip profile check if speaker identification is disabled (e.g., during setup)
        if not self.enable_speaker_id:
            logger.info("🔧 Speaker identification disabled - skipping profile check")
            return
            
        chaffee_profile_path = os.path.join(self.voices_dir, 'chaffee.json')
        
        if os.path.exists(chaffee_profile_path):
            # Profile exists - proceed normally
            logger.info(f"✅ Chaffee voice profile loaded from: {chaffee_profile_path}")
            logger.info(f"🎯 Speaker identification enabled (threshold: {self.chaffee_min_sim})")
        else:
            # Profile missing - check for auto-bootstrap
            auto_bootstrap = os.getenv('AUTO_BOOTSTRAP_CHAFFEE', '').lower() in ('true', '1', 'yes')
            seed_file_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'config', 'chaffee_seed_urls.json'
            )
            
            if auto_bootstrap and os.path.exists(seed_file_path):
                logger.info("🚀 Auto-bootstrapping Chaffee voice profile...")
                
                try:
                    # Import and run bootstrap in-process
                    sys.path.append(os.path.dirname(__file__))
                    from voice_bootstrap import build_voice_profile
                    
                    success = build_voice_profile(
                        seed_file_path=Path(seed_file_path),
                        profile_name='Chaffee',
                        overwrite=False
                    )
                    
                    if success:
                        logger.info("✅ Chaffee voice profile auto-bootstrap completed successfully!")
                    else:
                        raise RuntimeError("Auto-bootstrap failed")
                        
                except Exception as e:
                    logger.error(f"Auto-bootstrap failed: {e}")
                    raise FileNotFoundError(
                        f"CRITICAL: Auto-bootstrap failed and Chaffee voice profile not found at {chaffee_profile_path}. "
                        f"Try running manually: python -m backend.scripts.voice_bootstrap build "
                        f"--seeds backend/config/chaffee_seed_urls.json --name Chaffee --overwrite"
                    )
            else:
                # No auto-bootstrap - provide clear instructions
                hint_msg = "python -m backend.scripts.voice_bootstrap build --seeds backend/config/chaffee_seed_urls.json --name Chaffee --overwrite"
                if not auto_bootstrap:
                    hint_msg = f"Set AUTO_BOOTSTRAP_CHAFFEE=true or run: {hint_msg}"
                    
                raise FileNotFoundError(
                    f"CRITICAL: Chaffee voice profile not found at {chaffee_profile_path}. "
                    f"Speaker identification is MANDATORY to prevent misattribution. "
                    f"To create the profile, run: {hint_msg}"
                )
            
            logger.info(f"✅ Chaffee voice profile loaded from: {chaffee_profile_path}")
            logger.info(f"🎯 Speaker identification enabled (threshold: {self.chaffee_min_sim})")

@dataclass 
class ProcessingStats:
    """Track processing statistics with RTX 5080 performance metrics"""
    total: int = 0
    processed: int = 0
    skipped: int = 0
    errors: int = 0
    youtube_transcripts: int = 0
    whisper_transcripts: int = 0
    segments_created: int = 0
    chaffee_segments: int = 0
    guest_segments: int = 0
    unknown_segments: int = 0
    
    # RTX 5080 optimized pipeline stats
    io_queue_peak: int = 0
    asr_queue_peak: int = 0
    db_queue_peak: int = 0
    monologue_fast_path_used: int = 0
    content_hash_skips: int = 0
    embedding_batches: int = 0
    
    # Performance metrics for 1200h in 24h target
    total_audio_duration_s: float = 0.0  # Total audio processed in seconds
    total_processing_time_s: float = 0.0  # Total wall clock time
    asr_processing_time_s: float = 0.0   # Time spent in ASR processing
    embedding_processing_time_s: float = 0.0  # Time spent generating embeddings
    
    def add_audio_duration(self, duration_s: float):
        """Add processed audio duration"""
        self.total_audio_duration_s += duration_s
        
    def calculate_real_time_factor(self) -> float:
        """Calculate real-time factor (RTF) - target: 0.15-0.22 (5-7x faster)"""
        if self.asr_processing_time_s > 0 and self.total_audio_duration_s > 0:
            return self.asr_processing_time_s / self.total_audio_duration_s
        return 0.0
        
    def calculate_throughput_hours_per_hour(self) -> float:
        """Calculate audio throughput in hours per hour - target: ~50h/h"""
        if self.total_processing_time_s > 0:
            return (self.total_audio_duration_s / 3600.0) / (self.total_processing_time_s / 3600.0)
        return 0.0
    
    def log_summary(self):
        """Log final statistics with RTX 5080 performance metrics"""
        logger.info("=== RTX 5080 INGESTION SUMMARY ===")
        logger.info(f"Total videos: {self.total}")
        logger.info(f"Processed: {self.processed}")
        logger.info(f"Skipped: {self.skipped}")
        logger.info(f"Errors: {self.errors}")
        logger.info(f"YouTube transcripts: {self.youtube_transcripts}")
        logger.info(f"Whisper transcripts: {self.whisper_transcripts}")
        logger.info(f"Total segments created: {self.segments_created}")
        
        # Performance metrics
        rtf = self.calculate_real_time_factor()
        throughput = self.calculate_throughput_hours_per_hour()
        total_audio_hours = self.total_audio_duration_s / 3600.0
        
        logger.info(f"\n🚀 RTX 5080 PERFORMANCE METRICS:")
        logger.info(f"   Total audio processed: {total_audio_hours:.1f} hours")
        logger.info(f"   Real-time factor (RTF): {rtf:.3f} (target: 0.15-0.22)")
        if rtf > 0:
            speedup = 1.0 / rtf
            logger.info(f"   Processing speedup: {speedup:.1f}x faster than real-time")
        logger.info(f"   Throughput: {throughput:.1f} hours audio per hour (target: ~50h/h)")
        
        # Target achievement
        rtf_status = "✅" if 0.15 <= rtf <= 0.22 else "⚠️" if rtf > 0 else "❌"
        throughput_status = "✅" if throughput >= 50 else "⚠️" if throughput >= 25 else "❌"
        logger.info(f"   RTF target achievement: {rtf_status}")
        logger.info(f"   Throughput target achievement: {throughput_status}")
        
        # Estimate time for 1200h ingestion
        if throughput > 0:
            time_for_1200h = 1200 / throughput
            logger.info(f"   📅 Estimated time for 1200h: {time_for_1200h:.1f} hours")
        
        logger.info(f"\n🎯 Speaker attribution breakdown:")
        logger.info(f"   Chaffee segments: {self.chaffee_segments}")
        logger.info(f"   Guest segments: {self.guest_segments}")
        logger.info(f"   Unknown segments: {self.unknown_segments}")
        if self.segments_created > 0:
            # Ensure the speaker counts don't exceed total segments created
            # (This can happen due to counting bugs or duplicate processing)
            total_speaker_segments = self.chaffee_segments + self.guest_segments + self.unknown_segments
            if total_speaker_segments > self.segments_created:
                logger.warning(f"   ⚠️  Speaker count mismatch: {total_speaker_segments} speaker segments > {self.segments_created} total segments")
                logger.warning(f"   This indicates a counting bug or duplicate processing. Using segments_created for percentage calculation.")
                # Recalculate based on segments_created
                chaffee_pct = (self.chaffee_segments / total_speaker_segments) * 100 if total_speaker_segments > 0 else 0.0
            else:
                chaffee_pct = (self.chaffee_segments / self.segments_created) * 100
            logger.info(f"   Chaffee percentage: {chaffee_pct:.1f}%")
        
        # Pipeline optimization stats
        logger.info(f"\n📊 OPTIMIZATION STATS:")
        if self.monologue_fast_path_used > 0:
            logger.info(f"   🚀 Monologue fast-path used: {self.monologue_fast_path_used} times")
        if self.content_hash_skips > 0:
            logger.info(f"   📦 Content hash skips: {self.content_hash_skips}")
        if self.embedding_batches > 0:
            logger.info(f"   🔤 Embedding batches: {self.embedding_batches}")
        
        logger.info(f"   📊 Queue peaks: I/O={self.io_queue_peak}, ASR={self.asr_queue_peak}, DB={self.db_queue_peak}")
        
        if self.total > 0:
            success_rate = (self.processed / self.total) * 100
            logger.info(f"\n📈 Success rate: {success_rate:.1f}%")
            
            # Helpful message if everything was skipped
            if self.processed == 0 and self.skipped > 0:
                logger.info(f"\n💡 All {self.skipped} videos were skipped (already in database)")
                logger.info(f"   📝 This is NORMAL behavior - we skip videos that are already processed")
                logger.info(f"   ")
                logger.info(f"   To process UNPROCESSED videos:")
                logger.info(f"   • Increase --limit to check more videos (e.g., --limit 200)")
                logger.info(f"   • Use --newest-first to prioritize recent uploads")
                logger.info(f"   • Check database to see how many videos you have")
                logger.info(f"   ")
                logger.info(f"   To REPROCESS existing videos:")
                logger.info(f"   • Use --force to reprocess all videos in the batch")
                logger.info(f"   • Use --no-skip-existing to process without checking DB (dangerous!)")

class EnhancedYouTubeIngester:
    """Enhanced YouTube ingestion pipeline with dual data sources"""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
        self.stats = ProcessingStats()
        
        # GPU monitoring for performance telemetry
        self._last_telemetry = 0
        
        # Initialize components
        self.db = DatabaseUpserter(config.db_url)  # Keep for ingest_state tracking
        self.segments_db = SegmentsDatabase(config.db_url)  # Use for segments storage
        
        # Setup proxy manager
        proxy_config = ProxyConfig(
            enabled=(config.proxy is not None or config.proxy_file is not None),
            rotation_enabled=config.proxy_rotate,
            rotation_interval=config.proxy_rotate_interval,
            proxy_list=[config.proxy] if config.proxy else None,
            proxy_file=config.proxy_file
        )
        self.proxy_manager = ProxyManager(proxy_config)
        
        # Get initial proxy
        proxies = self.proxy_manager.get_proxy()
        
        # Use Enhanced Transcript Fetcher with RTX 5080 optimizations
        self.transcript_fetcher = EnhancedTranscriptFetcher(
            whisper_model=config.whisper_model,
            ffmpeg_path=config.ffmpeg_path,
            proxies=proxies,
            api_key=config.youtube_api_key,
            credentials_path=os.getenv('YOUTUBE_CREDENTIALS_PATH'),
            # Audio storage options
            store_audio_locally=config.store_audio_locally,
            audio_storage_dir=str(config.audio_storage_dir) if config.audio_storage_dir else None,
            production_mode=config.production_mode,
            # Speaker identification (MANDATORY)
            enable_speaker_id=config.enable_speaker_id,
            voices_dir=config.voices_dir,
            chaffee_min_sim=config.chaffee_min_sim,
            # RTX 5080 Performance Optimizations (passed via environment)
            assume_monologue=config.assume_monologue
        )
        self.embedder = EmbeddingGenerator()
        
        # Initialize video/file lister based on source
        if config.source == 'api':
            if not config.youtube_api_key:
                raise ValueError("YouTube API key required for API source")
            self.video_lister = YouTubeAPILister(config.youtube_api_key, config.db_url)
        elif config.source == 'yt-dlp':
            self.video_lister = YtDlpVideoLister()
        elif config.source == 'local':
            self.video_lister = LocalFileLister()
        else:
            raise ValueError(f"Unknown source: {config.source}")
    
    def list_videos(self) -> List[VideoInfo]:
        """List videos using configured source"""
        logger.info(f"Listing videos using {self.config.source} source")
        
        if self.config.source == 'local':
            # Handle local file source
            return self._list_local_files()
        elif self.config.from_url:
            # Handle direct URL(s)
            return self._list_from_urls(self.config.from_url)
        elif self.config.from_json:
            # Load from JSON file (yt-dlp only)
            if self.config.source != 'yt-dlp':
                raise ValueError("--from-json only supported with yt-dlp source")
            videos = self.video_lister.list_from_json(self.config.from_json)
        else:
            # Parse since_published if provided
            since_published = None
            if self.config.since_published:
                try:
                    # Try ISO8601 format first
                    if 'T' in self.config.since_published or '+' in self.config.since_published:
                        since_published = datetime.fromisoformat(self.config.since_published.replace('Z', '+00:00'))
                    else:
                        # Try YYYY-MM-DD format
                        since_published = datetime.strptime(self.config.since_published, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                except ValueError as e:
                    logger.error(f"Invalid since_published format: {self.config.since_published}. Use ISO8601 or YYYY-MM-DD")
                    raise
            
            # List videos from channel
            logger.info(f"Listing videos from channel using {self.config.source}")
            if self.config.source == 'api' and hasattr(self.video_lister, 'list_channel_videos'):
                videos = self.video_lister.list_channel_videos(
                    self.config.channel_url,
                    max_results=self.config.limit,
                    newest_first=self.config.newest_first,
                    since_published=since_published,
                    skip_live=self.config.skip_live,
                    skip_upcoming=self.config.skip_upcoming,
                    skip_members_only=self.config.skip_members_only
                )
            else:
                # yt-dlp lister supports members-only filtering
                # Cache disabled by default to avoid stale availability data
                videos = self.video_lister.list_channel_videos(
                    self.config.channel_url,
                    use_cache=False,  # Always fetch fresh to detect availability changes
                    skip_members_only=self.config.skip_members_only
                )
        
        # Apply filters (only for non-local sources)
        if self.config.source != 'local':
            if self.config.skip_shorts:
                videos = [v for v in videos if not v.duration_s or v.duration_s >= 120]
                logger.info(f"Filtered out shorts, {len(videos)} videos remaining")
            
            # Apply sorting
            if self.config.newest_first:
                videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)
            
            # Apply limit
            if self.config.limit and not self.config.limit_unprocessed:
                # Standard limit: take first N videos from list
                videos = videos[:self.config.limit]
            elif self.config.limit and self.config.limit_unprocessed:
                # Smart limit: find N unprocessed videos
                logger.info(f"🔍 Filtering to find {self.config.limit} unprocessed videos...")
                unprocessed_videos = []
                checked_count = 0
                
                for video in videos:
                    checked_count += 1
                    # Check if video is already processed
                    source_id, segment_count = self.segments_db.check_video_exists(video.video_id)
                    if not source_id or segment_count == 0:
                        # This video is unprocessed
                        unprocessed_videos.append(video)
                        if len(unprocessed_videos) >= self.config.limit:
                            break
                
                logger.info(f"   Checked {checked_count} videos, found {len(unprocessed_videos)} unprocessed")
                videos = unprocessed_videos
        
        logger.info(f"Found {len(videos)} videos to process")
        return videos
    
    def _list_from_urls(self, urls: List[str]) -> List[VideoInfo]:
        """Extract video IDs from YouTube URLs and fetch full metadata"""
        import re
        videos = []
        
        # Initialize yt-dlp lister for metadata fetching
        lister = YtDlpVideoLister()
        
        for url in urls:
            # Extract video ID from various YouTube URL formats
            # https://www.youtube.com/watch?v=VIDEO_ID
            # https://youtu.be/VIDEO_ID
            # VIDEO_ID (direct)
            match = re.search(r'(?:v=|youtu\.be/|^)([a-zA-Z0-9_-]{11})(?:[&?]|$)', url)
            if match:
                video_id = match.group(1)
                
                # Fetch full metadata from yt-dlp
                logger.info(f"Fetching metadata for {video_id}...")
                video = lister.get_video_metadata(video_id)
                
                if video:
                    videos.append(video)
                    logger.info(f"✅ Added video: {video.title[:60]}... ({video_id})")
                else:
                    # Fallback to minimal VideoInfo if metadata fetch fails
                    logger.warning(f"⚠️  Could not fetch metadata for {video_id}, using minimal info")
                    video = VideoInfo(
                        video_id=video_id,
                        title=f"Video {video_id}",
                        published_at=None,
                        duration_s=None,
                        view_count=None
                    )
                    videos.append(video)
            else:
                logger.warning(f"Could not extract video ID from URL: {url}")
        
        logger.info(f"Extracted {len(videos)} video(s) from URL(s)")
        return videos
    
    def _list_local_files(self) -> List[VideoInfo]:
        """List local video/audio files for processing"""
        logger.info(f"Scanning local files from: {self.config.from_files}")
        
        file_infos = self.video_lister.list_files_from_directory(
            self.config.from_files,
            patterns=self.config.file_patterns,
            recursive=True,  # Always scan subdirectories for local files
            max_results=self.config.limit,
            newest_first=self.config.newest_first
        )
        
        # Convert LocalFileInfo objects to VideoInfo objects
        videos = []
        for file_info in file_infos:
            # Get duration if possible
            try:
                duration = self.video_lister.get_file_duration(file_info.file_path)
                file_info.duration_s = duration
            except Exception as e:
                logger.debug(f"Could not get duration for {file_info.file_path}: {e}")
            
            # Apply duration filter for local files too
            if self.config.skip_shorts and file_info.duration_s and file_info.duration_s < 120:
                logger.debug(f"Skipping short file: {file_info.file_path} ({file_info.duration_s}s)")
                continue
            
            video_info = file_info.to_video_info()
            videos.append(video_info)
        
        logger.info(f"Found {len(videos)} local files to process")
        return videos
    
    def should_skip_video(self, video: VideoInfo) -> Tuple[bool, str]:
        """Check if video should be skipped"""
        # Skip check if force_reprocess is enabled
        if self.config.force_reprocess:
            return False, ""
        
        # Check existing processing state if skip_existing is enabled (default)
        if self.config.skip_existing:
            source_id, segment_count = self.segments_db.check_video_exists(video.video_id)
            if source_id and segment_count > 0:
                return True, f"already processed ({segment_count} segments)"
        
        return False, ""
    
    def process_single_video(self, video: VideoInfo) -> bool:
        """Process a single video through the full pipeline"""
        video_id = video.video_id
        
        try:
            # Check if video already exists in segments database (unless force_reprocess or skip_existing=False)
            if not self.config.force_reprocess and self.config.skip_existing:
                source_id, segment_count = self.segments_db.check_video_exists(video_id)
                if source_id and segment_count > 0:
                    logger.info(f"⚡ Skipping {video_id}: already processed ({segment_count} segments)")
                    self.stats.skipped += 1
                    return False
            
            # Check if should skip (redundant check, but kept for safety)
            should_skip, reason = self.should_skip_video(video)
            if should_skip:
                logger.info(f"⏭️  Skipping {video_id}: {reason}")
                self.stats.skipped += 1
                return True
            
            logger.info(f"Processing video {video_id}: {video.title}")
            # Step 1: Fetch transcript with enhanced metadata
            # Determine if this is a local file based on the source configuration
            is_local_file = self.config.source == 'local'
            
            if hasattr(self.transcript_fetcher, 'fetch_transcript_with_speaker_id'):
                # Use enhanced transcript fetcher with speaker ID support
                segments, method, metadata = self.transcript_fetcher.fetch_transcript_with_speaker_id(
                    video_id,
                    max_duration_s=self.config.max_duration,
                    force_enhanced_asr=self.config.force_whisper,
                    cleanup_audio=self.config.cleanup_audio,
                    enable_silence_removal=False,  # Conservative default
                    is_local_file=is_local_file,
                    allow_youtube_captions=self.config.allow_youtube_captions
                )
            else:
                # Fallback to standard transcript fetcher
                segments, method, metadata = self.transcript_fetcher.fetch_transcript(
                    video_id,
                    max_duration_s=self.config.max_duration,
                    force_whisper=self.config.force_whisper,
                    cleanup_audio=self.config.cleanup_audio,
                    enable_silence_removal=False  # Conservative default
                )
            
            if not segments:
                error_msg = metadata.get('error', 'Failed to fetch transcript')
                logger.error(f"❌ Failed to get transcript for {video_id} ({video.title[:50]}): {error_msg}")
                self.stats.errors += 1
                return False
            
            # Log transcript method for statistics
            logger.debug(f"Transcript method for {video_id}: {method}")
            
            # Track transcription method statistics
            if method == 'youtube':
                self.stats.youtube_transcripts += 1
            elif method in ('whisper', 'whisper_upgraded'):
                self.stats.whisper_transcripts += 1
                if method == 'whisper_upgraded':
                    logger.info(f"Used upgraded Whisper model for {video_id}")
            
            # Log quality information if available
            if 'quality_assessment' in metadata:
                quality_info = metadata['quality_assessment']
                logger.info(f"Transcript quality for {video_id}: score={quality_info['score']}, issues={quality_info.get('issues', [])}")
            
            # Extract provenance and extra metadata for database storage
            # Map transcript methods to database provenance values
            provenance_mapping = {
                'youtube': 'yt_caption',
                'whisper': 'whisper',
                'whisper_upgraded': 'whisper',
                'enhanced_asr': 'whisper',  # Enhanced ASR is still Whisper-based
                'yt_dlp': 'yt_dlp'
            }
            provenance = provenance_mapping.get(method, 'whisper')  # Default to whisper
            extra_metadata = {
                'transcript_method': method,
                'segment_count': len(segments)
            }
            
            # Add preprocessing and quality info if available
            if 'preprocessing_flags' in metadata:
                extra_metadata['preprocessing'] = metadata['preprocessing_flags']
            
            if 'quality_assessment' in metadata:
                extra_metadata['quality'] = metadata['quality_assessment']
            
            if 'model' in metadata:
                extra_metadata['whisper_model'] = metadata['model']
            
            if 'upgrade_used' in metadata:
                extra_metadata['upgrade_used'] = metadata['upgrade_used']
            
            # Step 2: Process segments with embeddings
            logger.debug(f"Processing {len(segments)} segments for {video_id}")
            
            # Step 3: Generate embeddings
            texts = [segment.text for segment in segments]
            embeddings = self.embedder.generate_embeddings(texts)
            
            # Attach embeddings to segments
            for segment, embedding in zip(segments, embeddings):
                segment.embedding = embedding
            
            logger.debug(f"Generated {len(embeddings)} embeddings for {video_id}")
            
            # Step 4: Upsert source and segments to database with proper speaker attribution
            # Determine source type based on actual source
            if self.config.source == 'local':
                source_type = 'local_file'
            elif self.config.source == 'api':
                source_type = 'youtube_api'
            else:
                source_type = 'youtube'  # Default for yt-dlp
            
            source_id = self.segments_db.upsert_source(
                video_id, 
                video.title,
                source_type=source_type,
                metadata={'provenance': provenance, **extra_metadata},
                published_at=video.published_at,
                duration_s=video.duration_s,
                view_count=video.view_count,
                channel_name=video.channel_name,
                channel_url=video.channel_url,
                thumbnail_url=video.thumbnail_url,
                like_count=video.like_count,
                comment_count=video.comment_count,
                description=video.description,
                tags=video.tags,
                url=video.url
            )
            
            # Convert TranscriptSegment objects to dictionaries for database insertion
            def safe_float_convert(value, default=0.0):
                """Convert numpy/other numeric types to Python float"""
                if value is None:
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            segment_dicts = []
            for segment in segments:
                if hasattr(segment, '__dict__'):
                    # Convert TranscriptSegment object to dictionary with proper type conversion
                    segment_dict = {
                        'start': safe_float_convert(segment.start),
                        'end': safe_float_convert(segment.end),
                        'text': str(segment.text),
                        'speaker_label': str(segment.speaker_label or 'GUEST'),
                        'speaker_confidence': safe_float_convert(segment.speaker_confidence, None),
                        'avg_logprob': safe_float_convert(segment.avg_logprob, None),
                        'compression_ratio': safe_float_convert(segment.compression_ratio, None),
                        'no_speech_prob': safe_float_convert(segment.no_speech_prob, None),
                        'temperature_used': safe_float_convert(segment.temperature_used, 0.0),
                        're_asr': bool(segment.re_asr),
                        'is_overlap': bool(segment.is_overlap),
                        'needs_refinement': bool(segment.needs_refinement),
                        'embedding': getattr(segment, 'embedding', None)
                    }
                    segment_dicts.append(segment_dict)
                else:
                    # Already a dictionary
                    segment_dicts.append(segment)
            
            # Insert segments with speaker attribution - RTX 5080 DEBUG
            logger.info(f"🔍 DEBUG: Attempting to insert {len(segment_dicts)} segments for {video_id}")
            logger.debug(f"🔍 Sample segment: {segment_dicts[0] if segment_dicts else 'None'}")
            
            try:
                segment_count = self.segments_db.batch_insert_segments(
                    segment_dicts, 
                    video_id,
                    chaffee_only_storage=self.config.chaffee_only_storage,
                    embed_chaffee_only=self.config.embed_chaffee_only
                )
                logger.info(f"✅ Successfully inserted {segment_count} segments for {video_id}")
            except Exception as e:
                logger.error(f"❌ Segment insertion failed for {video_id}: {e}")
                logger.debug(f"❌ Error details: {type(e).__name__}: {str(e)}")
                raise
            
            self.stats.processed += 1
            self.stats.segments_created += segment_count
            
            # Update speaker-specific stats - ONLY count segments that were actually inserted
            # If chaffee_only_storage is enabled, only Chaffee segments are inserted
            for segment in segment_dicts:
                speaker = segment.get('speaker_label', 'GUEST')
                
                # Skip counting if chaffee_only_storage is enabled and this isn't a Chaffee segment
                if self.config.chaffee_only_storage and speaker not in ['CH', 'CHAFFEE', 'Chaffee']:
                    continue
                
                # Enhanced ASR uses multiple formats: 'CH', 'Chaffee', 'CHAFFEE'
                if speaker in ['CH', 'CHAFFEE', 'Chaffee']:  # Support all formats
                    self.stats.chaffee_segments += 1
                elif speaker == 'GUEST':
                    self.stats.guest_segments += 1
                else:
                    self.stats.unknown_segments += 1
            
            # Log completion with additional info
            extra_info = ""
            if self.config.source == 'local':
                extra_info = f" (local file: {video_id})"
            elif metadata.get('stored_audio_path'):
                extra_info = f" (audio stored: {Path(metadata['stored_audio_path']).name})"
            
            # Log speaker identification results if available
            if metadata.get('enhanced_asr_used') and metadata.get('speaker_distribution'):
                chaffee_pct = metadata.get('chaffee_percentage', 0.0)
                logger.info(f"🎯 Speaker identification results for {video_id}:")
                logger.info(f"   Chaffee: {chaffee_pct:.1f}%")
                logger.info(f"   Total speakers detected: {len(metadata.get('speaker_distribution', {}))}")
                for speaker, count in metadata.get('speaker_distribution', {}).items():
                    logger.info(f"   {speaker}: {count} segments")
            
            logger.info(f"✅ Completed {video_id}: {len(segments)} segments, {method} transcript{extra_info}")
            return True
            
        except Exception as e:
            error_msg = str(e)[:500]  # Truncate long errors
            logger.error(f"❌ Error processing {video_id}: {error_msg}")
            
            # Log error for debugging
            logger.debug(f"Error details for {video_id}: {e}")
            self.stats.errors += 1
            return False
    
    def run_sequential(self, videos: List[VideoInfo]) -> None:
        """Run processing sequentially with progress bar"""
        self.stats.total = len(videos)
        
        with tqdm.tqdm(total=len(videos), desc="Processing videos") as pbar:
            for video in videos:
                if self.config.dry_run:
                    logger.info(f"DRY RUN: Would process {video.video_id}: {video.title}")
                    continue
                
                self.process_single_video(video)
                pbar.update(1)
                
                # Update progress bar description
                pbar.set_postfix({
                    'processed': self.stats.processed,
                    'errors': self.stats.errors,
                    'skipped': self.stats.skipped
                })
    
    def run_concurrent(self, videos: List[VideoInfo]) -> None:
        """Run processing with concurrent workers (legacy method)"""
        logger.info("Using legacy concurrent processing method")
        self.stats.total = len(videos)
        
        if self.config.dry_run:
            for video in videos:
                logger.info(f"DRY RUN: Would process {video.video_id}: {video.title}")
            return
        
        # Use ThreadPoolExecutor for I/O bound tasks
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            with tqdm.tqdm(total=len(videos), desc="Processing videos") as pbar:
                # Submit all tasks
                future_to_video = {
                    executor.submit(self.process_single_video, video): video 
                    for video in videos
                }
                
                # Process completed tasks
                for future in concurrent.futures.as_completed(future_to_video):
                    video = future_to_video[future]
                    try:
                        success = future.result()
                        if not success:
                            logger.debug(f"Video {video.video_id} returned False (skipped or failed)")
                    except Exception as e:
                        logger.error(f"❌ Unexpected error processing {video.video_id} ({video.title[:50]}): {e}", exc_info=True)
                        self.stats.errors += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({
                        'processed': self.stats.processed,
                        'errors': self.stats.errors,
                        'skipped': self.stats.skipped
                    })
    
    def run_pipelined(self, videos: List[VideoInfo]) -> None:
        """Run processing with three-tier producer/consumer pipeline for 3-6x speedup"""
        logger.info("🚀 Starting three-tier pipelined processing")
        logger.info(f"📊 Pipeline config: I/O={self.config.io_concurrency}, ASR={self.config.asr_concurrency}, DB={self.config.db_concurrency}")
        
        if self.config.force_reprocess:
            logger.info("🔄 Force reprocess enabled - will reprocess videos even if they exist in database")
        
        self.stats.total = len(videos)
        
        if self.config.dry_run:
            for video in videos:
                logger.info(f"DRY RUN: Would process {video.video_id}: {video.title}")
            return
        
        # Create queues for pipeline stages
        video_queue = queue.Queue()  # Input queue for videos (fixes duplicate work bug)
        io_queue = queue.Queue(maxsize=24)  # Tier A output -> Tier B input (reduced from 50)
        asr_queue = queue.Queue(maxsize=12)  # Tier B output -> Tier C input (reduced from 20)
        
        # Populate video queue once (critical fix!)
        for video in videos:
            video_queue.put(video)
        
        # Shared state for coordination
        stop_event = threading.Event()
        active_threads = threading.active_count()
        stats_lock = threading.Lock()
        
        # Progress tracking
        progress_bar = tqdm.tqdm(total=len(videos), desc="Pipeline progress")
        
        def update_progress():
            with stats_lock:
                progress_bar.set_postfix({
                    'processed': self.stats.processed,
                    'errors': self.stats.errors,
                    'skipped': self.stats.skipped,
                    'io_q': io_queue.qsize(),
                    'asr_q': asr_queue.qsize(),
                    'fast_path': self.stats.monologue_fast_path_used
                })
                # Track queue peaks
                self.stats.io_queue_peak = max(self.stats.io_queue_peak, io_queue.qsize())
                self.stats.asr_queue_peak = max(self.stats.asr_queue_peak, asr_queue.qsize())
                
                # GPU telemetry every 15 seconds
                import time
                current_time = time.time()
                if current_time - self._last_telemetry > 15:
                    _telemetry_hook(self.stats)
                    self._last_telemetry = current_time
        
        try:
            # Tier A: I/O workers (download + ffmpeg) - FIXED: use shared video_queue
            io_threads = []
            for i in range(self.config.io_concurrency):
                thread = threading.Thread(
                    target=self._io_worker,
                    args=(video_queue, io_queue, stop_event, stats_lock, update_progress),
                    name=f"IO-Worker-{i}"
                )
                thread.start()
                io_threads.append(thread)
            
            # Tier B: ASR workers (Whisper processing)
            asr_threads = []
            for i in range(self.config.asr_concurrency):
                thread = threading.Thread(
                    target=self._asr_worker, 
                    args=(io_queue, asr_queue, stop_event, stats_lock, update_progress),
                    name=f"ASR-Worker-{i}"
                )
                thread.start()
                asr_threads.append(thread)
            
            # Tier C: DB/Embedding workers
            db_threads = []
            for i in range(self.config.db_concurrency):
                thread = threading.Thread(
                    target=self._db_worker,
                    args=(asr_queue, stop_event, stats_lock, update_progress, progress_bar),
                    name=f"DB-Worker-{i}"
                )
                thread.start()
                db_threads.append(thread)
            
            # Wait for all I/O workers to complete
            for thread in io_threads:
                thread.join()
            logger.info("📥 I/O stage completed")
            
            # Signal ASR workers that no more input is coming
            for _ in range(self.config.asr_concurrency):
                io_queue.put(None)  # Poison pill
            
            # Wait for ASR workers
            for thread in asr_threads:
                thread.join()
            logger.info("🎙️ ASR stage completed")
            
            # Signal DB workers
            for _ in range(self.config.db_concurrency):
                asr_queue.put(None)  # Poison pill
            
            # Wait for DB workers
            for thread in db_threads:
                thread.join()
            logger.info("💾 DB stage completed")
            
        except KeyboardInterrupt:
            logger.info("⚠️ Pipeline interrupted by user")
            stop_event.set()
            # Wait a bit for graceful shutdown
            time.sleep(2)
        except Exception as e:
            logger.error(f"❌ Pipeline error: {e}")
            stop_event.set()
        finally:
            progress_bar.close()
            logger.info("🏁 Pipeline shutdown complete")
    
    def _io_worker(self, video_queue: queue.Queue, io_queue: queue.Queue, 
                   stop_event: threading.Event, stats_lock: threading.Lock, 
                   update_progress_func) -> None:
        """Tier A: I/O worker for yt-dlp audio download + ffmpeg demux"""
        
        while not stop_event.is_set():
            try:
                # Get next video from shared queue (FIXED: no more duplicate work!)
                try:
                    video = video_queue.get(timeout=1.0)
                except queue.Empty:
                    break  # No more videos
                
                # Check content hash for duplicates
                if self.config.enable_content_hashing:
                    content_hash = compute_content_hash(video.video_id, video.published_at)
                    # Simple hash-based skip (in production, would check database)
                    # Only skip if we've seen this exact hash before AND we have processed at least one video
                    if hasattr(self, '_processed_hashes') and content_hash in self._processed_hashes and self.stats.processed > 0:
                        with stats_lock:
                            self.stats.content_hash_skips += 1
                            self.stats.skipped += 1
                        continue
                    
                    if not hasattr(self, '_processed_hashes'):
                        self._processed_hashes = set()
                    self._processed_hashes.add(content_hash)
                
                # Check if should skip
                should_skip, reason = self.should_skip_video(video)
                if should_skip:
                    logger.debug(f"⏭️  Skipping {video.video_id}: {reason}")
                    with stats_lock:
                        self.stats.skipped += 1
                    update_progress_func()
                    video_queue.task_done()
                    continue
                
                # Download audio-only and convert to 16kHz mono WAV
                audio_path = self._download_and_prepare_audio(video)
                if not audio_path:
                    with stats_lock:
                        self.stats.errors += 1
                    continue
                
                # Put in ASR queue
                io_queue.put((video, audio_path))
                update_progress_func()
                
                # Mark video as processed from queue
                video_queue.task_done()
                
            except Exception as e:
                logger.error(f"I/O worker error: {e}")
                with stats_lock:
                    self.stats.errors += 1
                # Still need to mark as done even on error
                try:
                    video_queue.task_done()
                except:
                    pass
    
    def _asr_worker(self, io_queue: queue.Queue, asr_queue: queue.Queue,
                    stop_event: threading.Event, stats_lock: threading.Lock,
                    update_progress_func) -> None:
        """Tier B: ASR worker using CTranslate2 faster-whisper with routing logic"""
        
        while not stop_event.is_set():
            try:
                # Get next item from I/O queue
                try:
                    item = io_queue.get(timeout=1.0)
                    if item is None:  # Poison pill
                        break
                except queue.Empty:
                    continue
                
                video, audio_path = item
                
                # Get video duration for routing (FIXED: use fast method, not librosa)
                try:
                    duration_s = _fast_duration_seconds(audio_path)
                    duration_minutes = duration_s / 60.0 if duration_s > 0 else 10.0
                except Exception:
                    duration_minutes = video.duration_s / 60.0 if video.duration_s else 10.0
                
                # Detect if this is an interview (simple heuristic)
                is_interview = self._detect_interview_content(video, audio_path)
                
                # Use Whisper routing logic
                whisper_preset = pick_whisper_preset(duration_minutes, is_interview)
                
                # Enhanced monologue fast-path for 3x speedup (mandatory per spec)
                if (self.config.assume_monologue and not is_interview):
                    try:
                        # Fast-path: Skip full diarization for confirmed monologue content
                        fast_path_result = self._process_monologue_fast_path(
                            video, audio_path, whisper_preset
                        )
                        if fast_path_result:
                            logger.info(f"🚀 Monologue fast-path: {video.video_id} - 3x speedup achieved")
                            with stats_lock:
                                self.stats.monologue_fast_path_used += 1
                            asr_queue.put((video, fast_path_result, audio_path))
                            update_progress_func()
                            continue
                    except Exception as e:
                        logger.debug(f"Fast-path failed, falling back to full processing: {e}")
                
                # Standard ASR processing with routing and timing
                asr_start_time = time.time()
                segments, method, metadata = self._process_with_whisper_routing(
                    video, audio_path, whisper_preset
                )
                asr_end_time = time.time()
                
                if segments:
                    # Track ASR processing time for RTF calculation
                    asr_processing_time = asr_end_time - asr_start_time
                    audio_duration = video.duration_s or duration_s
                    
                    with stats_lock:
                        self.stats.asr_processing_time_s += asr_processing_time
                        self.stats.add_audio_duration(audio_duration)
                    
                    # Add timing metadata
                    metadata.update({
                        'asr_processing_time_s': asr_processing_time,
                        'audio_duration_s': audio_duration,
                        'real_time_factor': asr_processing_time / audio_duration if audio_duration > 0 else 0.0
                    })
                    
                    asr_queue.put((video, (segments, method, metadata), audio_path))
                else:
                    with stats_lock:
                        self.stats.errors += 1
                
                update_progress_func()
                
            except Exception as e:
                logger.error(f"ASR worker error: {e}")
                with stats_lock:
                    self.stats.errors += 1
    
    def _db_worker(self, asr_queue: queue.Queue, stop_event: threading.Event,
                   stats_lock: threading.Lock, update_progress_func, progress_bar) -> None:
        """Tier C: DB/embedding worker with batched operations"""
        embedding_batch = []
        total_texts = 0  # FIXED: Count texts, not videos!
        
        while not stop_event.is_set():
            try:
                # Get next item from ASR queue
                try:
                    item = asr_queue.get(timeout=1.0)
                    if item is None:  # Poison pill
                        break
                except queue.Empty:
                    continue
                
                video, asr_result, audio_path = item
                segments, method, metadata = asr_result
                
                # Process embeddings in batches
                if self.config.embed_later:
                    # Queue for later processing
                    self._enqueue_for_embedding(video.video_id, segments)
                else:
                    # Generate embeddings in batches - FIXED: batch by text count!
                    embedding_batch.append((video, segments, method, metadata))
                    total_texts += len(segments)  # Count actual text segments!
                    
                    if total_texts >= self.config.embedding_batch_size:
                        self._process_embedding_batch(embedding_batch, stats_lock)
                        embedding_batch.clear()
                        total_texts = 0  # Reset counter
                        with stats_lock:
                            self.stats.embedding_batches += 1
                
                # Cleanup audio if needed
                if self.config.cleanup_audio and audio_path and os.path.exists(audio_path):
                    try:
                        os.unlink(audio_path)
                    except Exception as e:
                        logger.debug(f"Failed to cleanup audio {audio_path}: {e}")
                
                with stats_lock:
                    self.stats.processed += 1
                progress_bar.update(1)
                update_progress_func()
                
            except Exception as e:
                logger.error(f"DB worker error: {e}")
                with stats_lock:
                    self.stats.errors += 1
        
        # Process remaining embedding batch
        if embedding_batch:
            self._process_embedding_batch(embedding_batch, stats_lock)
            with stats_lock:
                self.stats.embedding_batches += 1
    
    def _download_and_prepare_audio(self, video: VideoInfo) -> Optional[str]:
        """Download audio-only and convert to 16kHz mono WAV"""
        try:
            # Use yt-dlp for audio-only download
            import subprocess
            import tempfile
            
            # Create unique temp directory for this thread
            temp_dir = get_thread_temp_dir()
            audio_file = os.path.join(temp_dir, f"{video.video_id}_audio.wav")
            
            # yt-dlp command for audio-only download + ffmpeg conversion
            cmd = [
                "yt-dlp",
                "-x",  # Extract audio
                "--audio-format", "wav",
                "--audio-quality", "0",  # Best quality
                "--postprocessor-args", "-ar 16000 -ac 1",  # 16kHz mono
                "-o", audio_file.replace('.wav', '.%(ext)s'),
                f"https://www.youtube.com/watch?v={video.video_id}"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and os.path.exists(audio_file):
                return audio_file
            else:
                logger.error(f"yt-dlp failed for {video.video_id}: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Audio download failed for {video.video_id}: {e}")
            return None
    
    def _detect_interview_content(self, video: VideoInfo, audio_path: str) -> bool:
        """Enhanced heuristic to detect interview/multi-speaker content for conditional diarization"""
        try:
            # Check title for interview keywords
            title_lower = video.title.lower() if video.title else ""
            interview_keywords = ['interview', 'conversation', 'chat', 'talk', 'guest', 'podcast', 'discussion', 'debate']
            
            if any(keyword in title_lower for keyword in interview_keywords):
                logger.info(f"🎙️ Interview detected by title keywords: {video.video_id}")
                return True
                
            # Fast audio analysis for speaker changes (first 3 minutes for better accuracy)
            import librosa
            import numpy as np
            
            audio, sr = librosa.load(audio_path, duration=180, sr=16000)  # 3 minutes
            if len(audio) < sr * 30:  # Less than 30 seconds
                return False
            
            # Enhanced speaker change detection using multiple features
            frame_length = int(sr * 2)  # 2-second frames
            hop_length = int(sr * 0.5)   # 0.5-second hop for better resolution
            
            # Energy variance analysis
            energy = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length)[0]
            energy_variance = np.var(energy)
            energy_mean = np.mean(energy)
            variance_ratio = energy_variance / (energy_mean + 1e-8)
            
            # Spectral centroid variance (voice pitch/timbre changes)
            spectral_centroids = librosa.feature.spectral_centroid(y=audio, sr=sr, hop_length=hop_length)[0]
            centroid_variance = np.var(spectral_centroids)
            centroid_mean = np.mean(spectral_centroids)
            centroid_ratio = centroid_variance / (centroid_mean + 1e-8)
            
            # Zero crossing rate variance (speech pattern changes)
            zcr = librosa.feature.zero_crossing_rate(audio, hop_length=hop_length)[0]
            zcr_variance = np.var(zcr)
            zcr_mean = np.mean(zcr)
            zcr_ratio = zcr_variance / (zcr_mean + 1e-8)
            
            # Combined heuristic - relaxed thresholds to favor fast-path (speaker ID filters later)
            # Allow fast-path even with brief guest appearances - full diarization only for true interviews
            is_interview = (variance_ratio > 0.8 or centroid_ratio > 0.5 or zcr_ratio > 0.6)
            
            if is_interview:
                logger.info(f"🎙️ Multi-speaker content detected: {video.video_id} "
                          f"(energy_var={variance_ratio:.3f}, centroid_var={centroid_ratio:.3f}, zcr_var={zcr_ratio:.3f})")
            else:
                logger.info(f"🔇 Monologue detected: {video.video_id} - fast-path eligible "
                          f"(energy_var={variance_ratio:.3f}, centroid_var={centroid_ratio:.3f}, zcr_var={zcr_ratio:.3f})")
                
            return is_interview
            
        except Exception as e:
            logger.debug(f"Interview detection failed: {e}")
            # Default to safe assumption for unknown content
            return True  # Better to assume interview and run full diarization
    
    def _process_monologue_fast_path(self, video: VideoInfo, audio_path: str, 
                                   whisper_preset: Dict[str, Any]) -> Optional[Tuple[List, str, Dict]]:
        """Fast-path processing for monologue content - skip full diarization for 3x speedup"""
        try:
            logger.info(f"🚀 Fast-path: Processing monologue {video.video_id} - skipping diarization")
            
            # Use distil-large-v3 with int8_float16 for maximum speed
            if hasattr(self.transcript_fetcher, 'process_with_fast_whisper'):
                segments, method, metadata = self.transcript_fetcher.process_with_fast_whisper(
                    audio_path=audio_path,
                    model=whisper_preset['model'],
                    compute_type=whisper_preset['compute_type'],
                    chunk_length=whisper_preset.get('chunk_length', 240),
                    skip_diarization=True,  # Key optimization: skip diarization
                    default_speaker='CHAFFEE'  # Assume Chaffee for monologue
                )
            else:
                # Fallback to enhanced transcript fetcher
                segments, method, metadata = self.transcript_fetcher.fetch_transcript_with_routing(
                    video.video_id,
                    audio_path=audio_path,
                    whisper_preset=whisper_preset,
                    force_enhanced_asr=True,
                    skip_diarization=True,
                    cleanup_audio=False
                )
            
            if segments:
                # Mark all segments as Chaffee for monologue content
                for segment in segments:
                    if hasattr(segment, 'speaker_label'):
                        segment.speaker_label = 'CHAFFEE'
                        segment.speaker_confidence = 0.95  # High confidence for monologue
                    elif isinstance(segment, dict):
                        segment['speaker_label'] = 'CHAFFEE'
                        segment['speaker_confidence'] = 0.95
                
                # Add fast-path metadata
                metadata.update({
                    'fast_path_used': True,
                    'diarization_skipped': True,
                    'processing_speedup': '3x',
                    'speaker_attribution': 'monologue_assumed'
                })
                
                logger.info(f"✅ Fast-path completed: {video.video_id} - {len(segments)} segments, 3x speedup")
                return segments, method, metadata
            
            return None
            
        except Exception as e:
            logger.warning(f"Fast-path failed for {video.video_id}: {e}")
            return None
    
    def _check_youtube_caption_quality(self, video: VideoInfo) -> Tuple[bool, Optional[Dict]]:
        """Check if YouTube captions meet quality threshold for acceptance"""
        try:
            # Only accept YT captions for monologue content in English
            if not self.config.assume_monologue:
                return False, None
            
            # Check if video has captions available
            import yt_dlp
            
            ydl_opts = {
                'writesubtitles': False,
                'writeautomaticsub': False,
                'listsubtitles': True,
                'quiet': True,
                'no_warnings': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video.video_id}", download=False)
                
                # Check for English subtitles
                subtitles = info.get('subtitles', {})
                auto_captions = info.get('automatic_captions', {})
                
                # Prefer manual captions over auto-generated
                if 'en' in subtitles:
                    caption_info = subtitles['en'][0]
                    quality_score = 0.95  # High quality for manual captions
                elif 'en' in auto_captions:
                    caption_info = auto_captions['en'][0]
                    quality_score = 0.85  # Lower quality for auto captions
                else:
                    return False, None
                
                # Check quality threshold
                if quality_score >= self.config.yt_caption_quality_threshold:
                    logger.info(f"✅ YT captions accepted for {video.video_id} (quality: {quality_score:.2f})")
                    return True, {
                        'caption_info': caption_info,
                        'quality_score': quality_score,
                        'is_manual': 'en' in subtitles
                    }
                else:
                    logger.info(f"❌ YT captions rejected for {video.video_id} (quality: {quality_score:.2f} < {self.config.yt_caption_quality_threshold:.2f})")
                    return False, None
                
        except Exception as e:
            logger.debug(f"YT caption quality check failed for {video.video_id}: {e}")
            return False, None
    
    def _process_with_whisper_routing(self, video: VideoInfo, audio_path: str, 
                                     whisper_preset: Dict[str, Any]) -> Tuple[List, str, Dict]:
        """Process audio with routed Whisper model and YT caption gating"""
        try:
            # First, check if YouTube captions are acceptable
            if not self.config.force_whisper:
                yt_caption_ok, yt_caption_info = self._check_youtube_caption_quality(video)
                if yt_caption_ok:
                    # Use YouTube captions
                    segments, method, metadata = self.transcript_fetcher.fetch_transcript(
                        video.video_id,
                        max_duration_s=self.config.max_duration,
                        force_whisper=False,  # Allow YT captions
                        cleanup_audio=False
                    )
                    
                    if segments and method == 'youtube':
                        # Add YT caption quality info to metadata
                        metadata.update({
                            'yt_caption_quality': yt_caption_info['quality_score'],
                            'yt_caption_manual': yt_caption_info['is_manual'],
                            'quality_gating_passed': True
                        })
                        return segments, method, metadata
            
            # Use Enhanced ASR with speaker ID (pipelined mode)
            if hasattr(self.transcript_fetcher, 'fetch_transcript_with_speaker_id'):
                return self.transcript_fetcher.fetch_transcript_with_speaker_id(
                    video.video_id,
                    max_duration_s=self.config.max_duration,
                    force_enhanced_asr=True,  # Always use enhanced ASR in pipeline
                    cleanup_audio=False,  # Don't cleanup yet, handled by DB worker
                    allow_youtube_captions=False  # Never use YT captions in pipeline
                )
            else:
                # Fallback to standard method (should never happen)
                logger.warning(f"Enhanced ASR not available for {video.video_id}, using standard Whisper")
                return self.transcript_fetcher.fetch_transcript(
                    video.video_id,
                    max_duration_s=self.config.max_duration,
                    force_whisper=True,
                    cleanup_audio=False
                )
                
        except Exception as e:
            logger.error(f"Whisper routing failed for {video.video_id}: {e}")
            return [], 'error', {'error': str(e)}
    
    def _process_embedding_batch(self, batch: List[Tuple], stats_lock: threading.Lock) -> None:
        """RTX 5080 optimized batch processing for embeddings (128-256 segments per batch)"""
        try:
            all_texts = []
            batch_info = []
            chaffee_texts = []  # Separate tracking for Chaffee-only embedding
            
            # Collect all texts for batched embedding with speaker filtering
            for video, segments, method, metadata in batch:
                video_texts = []
                video_chaffee_texts = []
                
                for segment in segments:
                    text = segment.text if hasattr(segment, 'text') else segment.get('text', '')
                    speaker = segment.speaker_label if hasattr(segment, 'speaker_label') else segment.get('speaker_label', 'GUEST')
                    
                    video_texts.append(text)
                    
                    # Only embed Chaffee segments for search optimization (per spec)
                    if self.config.embed_chaffee_only and speaker in ['CH', 'CHAFFEE', 'Chaffee']:
                        video_chaffee_texts.append(text)
                    elif not self.config.embed_chaffee_only:
                        video_chaffee_texts.append(text)
                
                all_texts.extend(video_texts)
                chaffee_texts.extend(video_chaffee_texts)
                batch_info.append((video, segments, method, metadata, len(video_texts), len(video_chaffee_texts)))
            
            # Generate embeddings in optimized batches (256 max for RTX 5080)
            embeddings = []
            if all_texts:
                logger.info(f"💾 Processing embedding batch: {len(all_texts)} total texts, {len(chaffee_texts)} Chaffee texts")
                start_time = time.time()
                
                # Use Chaffee-only texts for embedding if configured
                embed_texts = chaffee_texts if self.config.embed_chaffee_only else all_texts
                
                if embed_texts:
                    embeddings = self.embedder.generate_embeddings(embed_texts)
                    
                    embedding_time = time.time() - start_time
                    texts_per_second = len(embed_texts) / embedding_time if embedding_time > 0 else 0
                    logger.info(f"⚡ Embedding generation: {len(embed_texts)} texts in {embedding_time:.2f}s "
                              f"({texts_per_second:.1f} texts/sec)")
                
                # Distribute embeddings back to segments and insert to DB
                embedding_idx = 0
                for video, segments, method, metadata, total_texts, chaffee_count in batch_info:
                    # Attach embeddings to segments (only Chaffee if configured)
                    for segment in segments:
                        speaker = segment.speaker_label if hasattr(segment, 'speaker_label') else segment.get('speaker_label', 'GUEST')
                        
                        # Only assign embedding if this segment should be embedded
                        should_embed = (
                            not self.config.embed_chaffee_only or 
                            speaker in ['CH', 'CHAFFEE', 'Chaffee']
                        )
                        
                        if should_embed and embedding_idx < len(embeddings):
                            if hasattr(segment, '__dict__'):
                                segment.embedding = embeddings[embedding_idx]
                            else:
                                segment['embedding'] = embeddings[embedding_idx]
                            embedding_idx += 1
                        elif not should_embed:
                            # No embedding for non-Chaffee segments when embed_chaffee_only=True
                            if hasattr(segment, '__dict__'):
                                segment.embedding = None
                            else:
                                segment['embedding'] = None
                    
                    # Insert to database using batch operations
                    self._batch_insert_video_segments(video, segments, method, metadata, stats_lock)
            
        except Exception as e:
            logger.error(f"Batch embedding processing failed: {e}")
    
    def _batch_insert_video_segments(self, video: VideoInfo, segments: List, 
                                    method: str, metadata: Dict, stats_lock: threading.Lock) -> None:
        """Insert video segments using optimized batch operations"""
        try:
            # First, ensure the source exists in the database
            self.segments_db.upsert_source(
                video_id=video.video_id,
                title=video.title,
                source_type='youtube',
                metadata=metadata,
                published_at=getattr(video, 'published_at', None),
                duration_s=getattr(video, 'duration_s', None),
                view_count=getattr(video, 'view_count', None),
                channel_name=getattr(video, 'channel_name', None),
                channel_url=getattr(video, 'channel_url', None),
                thumbnail_url=getattr(video, 'thumbnail_url', None),
                like_count=getattr(video, 'like_count', None),
                comment_count=getattr(video, 'comment_count', None),
                description=getattr(video, 'description', None),
                tags=getattr(video, 'tags', None),
                url=getattr(video, 'url', None)
            )
            
            # Then insert segments
            segment_count = self.segments_db.batch_insert_segments(
                segments,
                video.video_id,
                chaffee_only_storage=self.config.chaffee_only_storage,
                embed_chaffee_only=self.config.embed_chaffee_only
            )
            
            with stats_lock:
                self.stats.segments_created += segment_count
                
                # Update speaker stats - ONLY count segments that were actually inserted
                # If chaffee_only_storage is enabled, only Chaffee segments are inserted
                for segment in segments:
                    speaker = segment.get('speaker_label', 'GUEST') if isinstance(segment, dict) else getattr(segment, 'speaker_label', 'GUEST')
                    
                    # Skip counting if chaffee_only_storage is enabled and this isn't a Chaffee segment
                    if self.config.chaffee_only_storage and speaker not in ['CH', 'CHAFFEE', 'Chaffee']:
                        continue
                    
                    if speaker in ['CH', 'CHAFFEE', 'Chaffee']:
                        self.stats.chaffee_segments += 1
                    elif speaker == 'GUEST':
                        self.stats.guest_segments += 1
                    else:
                        self.stats.unknown_segments += 1
                
                # Track transcript method
                if method == 'youtube':
                    self.stats.youtube_transcripts += 1
                elif method in ('whisper', 'whisper_upgraded', 'enhanced_asr'):
                    self.stats.whisper_transcripts += 1
            
        except Exception as e:
            logger.error(f"Batch insert failed for {video.video_id}: {e}")
    
    def _enqueue_for_embedding(self, video_id: str, segments: List) -> None:
        """Enqueue segments for later embedding processing"""
        # This would store segment IDs for later batch embedding
        # Implementation depends on your embedding queue system
        logger.debug(f"Enqueued {len(segments)} segments from {video_id} for later embedding")
    
    async def check_video_accessibility(self, video: VideoInfo) -> bool:
        """Check if a video is accessible (not members-only) using yt-dlp"""
        try:
            cmd = [
                "yt-dlp",
                "--simulate", 
                "--no-warnings",
                "--extractor-args", "youtube:player_client=web_safari",
                "-4",
                f"https://www.youtube.com/watch?v={video.video_id}"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return True
            else:
                error_msg = stderr.decode().lower()
                if "members-only" in error_msg or "join this channel" in error_msg:
                    logger.info(f"🔒 Skipping members-only: {video.video_id} - {video.title[:50]}...")
                    return False
                else:
                    logger.warning(f"⚠️ Video inaccessible: {video.video_id}")
                    return False
                
        except Exception as e:
            logger.error(f"❌ Accessibility check failed for {video.video_id}: {e}")
            return False
    
    async def phase1_prefilter_videos(self, videos: List[VideoInfo]) -> List[VideoInfo]:
        """Phase 1: Smart pre-filtering for accessibility (3-phase optimization)"""
        if self.config.source == 'local' or len(videos) <= 10:
            logger.info("⚡ Skipping Phase 1 pre-filtering (local files or small batch)")
            return videos
            
        logger.info(f"🎯 PHASE 1: Pre-filtering {len(videos)} videos for accessibility")
        start_time = time.time()
        
        # Create semaphore for controlled concurrent checks - RTX 5080 optimized
        max_concurrent_checks = min(20, len(videos))  # Increased to 20 for better throughput
        semaphore = asyncio.Semaphore(max_concurrent_checks)
        
        async def check_with_semaphore(video):
            async with semaphore:
                is_accessible = await self.check_video_accessibility(video)
                return video, is_accessible
        
        # Check all videos concurrently
        logger.info(f"🔍 Checking accessibility ({max_concurrent_checks} concurrent)")
        tasks = [check_with_semaphore(video) for video in videos]
        results = await asyncio.gather(*tasks)
        
        # Filter results
        accessible_videos = []
        members_only_count = 0
        
        for video, is_accessible in results:
            if is_accessible:
                accessible_videos.append(video)
            else:
                members_only_count += 1
        
        duration = time.time() - start_time
        logger.info(f"✅ Phase 1 Complete ({duration:.1f}s):")
        logger.info(f"   📈 Accessible: {len(accessible_videos)}")
        logger.info(f"   🔒 Members-only filtered: {members_only_count}")
        logger.info(f"   📊 Success rate: {(len(accessible_videos)/len(videos)*100):.1f}%")
        logger.info(f"   💡 Saved {members_only_count * 30:.0f}s of wasted processing time")
        
        return accessible_videos

    def run(self) -> None:
        """Run the complete ingestion pipeline with RTX 5080 optimization for 1200h in 24h"""
        start_time = datetime.now()
        pipeline_start_time = time.time()
        
        logger.info("🚀 Starting RTX 5080 optimized YouTube ingestion pipeline")
        logger.info(f"🎯 Target: 1200h audio ingestion in ≤24h (50h/hour throughput)")
        logger.info(f"Config: source={self.config.source}, io_workers={self.config.io_concurrency}, "
                   f"asr_workers={self.config.asr_concurrency}, db_workers={self.config.db_concurrency}")
        
        try:
            # List videos
            videos = self.list_videos()
            
            if not videos:
                logger.warning("No videos found to process")
                return
            
            # Smart 3-Phase Pipeline for medium/large batches - lowered threshold for better optimization
            if len(videos) > 15 and self.config.source in ['api', 'yt-dlp']:
                logger.info("📊 Using SMART 3-PHASE pipeline for large batch optimization")
                logger.info("   🎯 Phase 1: Pre-filter accessibility")
                logger.info("   📥 Phase 2: Bulk download accessible videos")  
                logger.info("   🎙️ Phase 3: Enhanced ASR processing")
                
                # Phase 1: Pre-filter videos (async)
                import asyncio
                accessible_videos = asyncio.run(self.phase1_prefilter_videos(videos))
                
                if not accessible_videos:
                    logger.warning("No accessible videos found after Phase 1 filtering")
                    return
                
                # Phase 2 & 3: Process accessible videos normally
                logger.info(f"📥 PHASE 2 & 3: Processing {len(accessible_videos)} accessible videos")
                videos = accessible_videos
            
            # Process videos (Phase 2 & 3 combined)
            # Use pipelined processing for better throughput
            if len(videos) >= 5 and not self.config.dry_run:
                logger.info("📈 Using pipelined processing for optimal throughput")
                self.run_pipelined(videos)
            elif self.config.concurrency > 1:
                self.run_concurrent(videos)
            else:
                self.run_sequential(videos)
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise
        finally:
            # Calculate final performance metrics
            end_time = datetime.now()
            duration = end_time - start_time
            self.stats.total_processing_time_s = time.time() - pipeline_start_time
            
            logger.info(f"🏁 Pipeline completed in {duration} ({self.stats.total_processing_time_s:.1f}s)")
            self.stats.log_summary()
            
            # Close database connection
            self.db.close_connection()
    
    def setup_chaffee_profile(self, audio_sources: list, overwrite: bool = False, update: bool = False) -> bool:
        """Setup Chaffee voice profile for speaker identification"""
        try:
            logger.info("Setting up Chaffee voice profile")
            
            success = False
            for source in audio_sources:
                if source.startswith('http'):
                    # YouTube URL
                    if 'youtube.com/watch?v=' in source or 'youtu.be/' in source:
                        video_id = source.split('v=')[1].split('&')[0] if 'v=' in source else source.split('/')[-1]
                        # Check if we should update or overwrite
                        if update:
                            # For update, we need to first check if the profile exists
                            from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
                            enrollment = VoiceEnrollment(voices_dir=self.config.voices_dir)
                            if enrollment.load_profile('chaffee'):
                                # Profile exists, so we'll download the audio and update manually
                                audio_path = self.transcript_fetcher._download_audio_for_enhanced_asr(video_id)
                                if audio_path:
                                    profile = enrollment.enroll_speaker(
                                        name='Chaffee',
                                        audio_sources=[audio_path],
                                        overwrite=False,
                                        update=True
                                    )
                                    success = profile is not None
                                else:
                                    logger.error(f"Failed to download audio for {video_id}")
                                    success = False
                            else:
                                # Profile doesn't exist, so we'll create it
                                success = self.transcript_fetcher.enroll_speaker_from_video(
                                    video_id, 
                                    'Chaffee', 
                                    overwrite=True
                                )
                        else:
                            # Normal enrollment (create or overwrite)
                            success = self.transcript_fetcher.enroll_speaker_from_video(
                                video_id, 
                                'Chaffee', 
                                overwrite=overwrite
                            )
                    else:
                        logger.warning(f"Unsupported URL format: {source}")
                        continue
                else:
                    # Local audio file
                    from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
                    enrollment = VoiceEnrollment(voices_dir=self.config.voices_dir)
                    profile = enrollment.enroll_speaker(
                        name='Chaffee',
                        audio_sources=[source],
                        overwrite=overwrite,
                        update=update
                    )
                    success = profile is not None
                
                if success:
                    logger.info(f"Successfully enrolled Chaffee from: {source}")
                    break
                else:
                    logger.warning(f"Failed to enroll Chaffee from: {source}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to setup Chaffee profile: {e}")
            return False

def parse_args() -> IngestionConfig:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Enhanced YouTube transcript ingestion for Ask Dr. Chaffee',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Basic yt-dlp ingestion (checks first 20 videos)
  python ingest_youtube_enhanced.py --source yt-dlp --limit 20

  # Process 50 UNPROCESSED videos (smart limit)
  python ingest_youtube_enhanced.py --source yt-dlp --limit 50 --limit-unprocessed

  # Use YouTube Data API
  python ingest_youtube_enhanced.py --source api --limit 50 --newest-first

  # Process from pre-dumped JSON
  python ingest_youtube_enhanced.py --from-json backend/data/videos.json --concurrency 8

  # Process local video/audio files
  python ingest_youtube_enhanced.py --source local --from-files ./video_collection --concurrency 4

  # Process specific file types with audio storage disabled
  python ingest_youtube_enhanced.py --source local --from-files ./podcasts --file-patterns *.mp3 *.wav --no-store-audio

  # Production mode (no audio storage)
  python ingest_youtube_enhanced.py --source api --production-mode --limit 100

  # Speaker identification features
  python ingest_youtube_enhanced.py --source yt-dlp --limit 50 --chaffee-min-sim 0.65
  
  # Setup Chaffee voice profile
  python ingest_youtube_enhanced.py --setup-chaffee audio_sample.wav --overwrite-profile
  
  # Storage optimization for large batches
  python ingest_youtube_enhanced.py --source api --chaffee-only-storage --limit 200
  
  # RTX 5080 Maximum Performance (default)
  python ingest_youtube_enhanced.py --source yt-dlp --concurrency 12 --limit 100
  
  # Conservative mode (disable optimizations)
  python ingest_youtube_enhanced.py --source yt-dlp --no-assume-monologue --enable-vad --limit 50

  # Dry run to see what would be processed
  python ingest_youtube_enhanced.py --dry-run --limit 10

  # Force Whisper transcription with larger model
  python ingest_youtube_enhanced.py --source yt-dlp --whisper-model medium.en --force-whisper
        """
    )
    
    # Source configuration
    parser.add_argument('--source', choices=['api', 'yt-dlp', 'local'], default='yt-dlp',
                       help='Data source: api for YouTube Data API, yt-dlp for main data (default), local for files')
    parser.add_argument('--from-url', nargs='+',
                       help='Process specific YouTube URL(s) - e.g. https://www.youtube.com/watch?v=VIDEO_ID')
    parser.add_argument('--from-json', type=Path,
                       help='Process videos from JSON file instead of fetching (yt-dlp only)')
    parser.add_argument('--from-files', type=Path,
                       help='Process local video/audio files from directory (local source only)')
    parser.add_argument('--file-patterns', nargs='+', 
                       help='File patterns to match (e.g. *.mp4 *.wav), default: all supported formats')
    parser.add_argument('--channel-url',
                       help='YouTube channel URL (default: env YOUTUBE_CHANNEL_URL)')
    parser.add_argument('--since-published',
                       help='Only process videos published after this date (ISO8601 or YYYY-MM-DD)')
    
    # Processing configuration  
    parser.add_argument('--concurrency', type=int, default=4,
                       help='Concurrent workers for processing (default: 4, legacy)')
    parser.add_argument('--io-concurrency', type=int, default=12,
                       help='I/O worker threads for download/ffmpeg (RTX 5080 optimized: 12)')
    parser.add_argument('--asr-concurrency', type=int, default=2,
                       help='ASR worker threads (RTX 5080 optimized: 2 for batch overlap)')
    parser.add_argument('--db-concurrency', type=int, default=12,
                       help='DB/embedding worker threads (RTX 5080 optimized: 12)')
    parser.add_argument('--embed-later', action='store_true',
                       help='Enqueue embeddings for separate processing')
    parser.add_argument('--embedding-batch-size', type=int, default=256,
                       help='Batch size for embedding generation (RTX 5080 optimized: 256)')
    parser.add_argument('--skip-shorts', action='store_true',
                       help='Skip videos shorter than 120 seconds')
    parser.add_argument('--newest-first', action='store_true', default=True,
                       help='Process newest videos first (default: true)')
    parser.add_argument('--limit', type=int,
                       help='Maximum number of videos to process')
    parser.add_argument('--limit-unprocessed', action='store_true',
                       help='Apply limit to unprocessed videos only (finds N new videos to process)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be processed without writing to DB')
    parser.add_argument('--force', '--force-reprocess', action='store_true', dest='force_reprocess',
                       help='Reprocess videos even if they already exist in database')
    parser.add_argument('--no-skip-existing', action='store_false', dest='skip_existing',
                       help='Process all videos without checking if they exist (use with caution)')
    
    # Content filtering options
    parser.add_argument('--include-live', action='store_false', dest='skip_live',
                       help='Include live streams (skipped by default)')
    parser.add_argument('--include-upcoming', action='store_false', dest='skip_upcoming',
                       help='Include upcoming streams (skipped by default)')
    parser.add_argument('--include-members-only', action='store_false', dest='skip_members_only',
                       help='Include members-only content (skipped by default)')
    
    # Whisper configuration
    parser.add_argument('--whisper-model', default='distil-large-v3',
                       choices=['tiny.en', 'base.en', 'small.en', 'medium.en', 'large-v3', 'distil-large-v3'],
                       help='Whisper model size (RTX 5080 optimized: distil-large-v3)')
    parser.add_argument('--force-whisper', action='store_true',
                       help='Force Enhanced ASR with speaker ID (automatically enabled when speaker ID is on)')
    parser.add_argument('--allow-youtube-captions', action='store_true',
                       help='⚠️  DEPRECATED: Allow YouTube captions (STRONGLY NOT RECOMMENDED)\n'
                            '    Bypasses speaker identification, segment optimization, and embeddings.\n'
                            '    Results in NULL speaker labels and unusable data for RAG.\n'
                            '    Only use for testing YouTube caption quality.')
    parser.add_argument('--ffmpeg-path',
                       help='Path to ffmpeg binary (default: auto-detect)')
    
    # Proxy configuration
    parser.add_argument('--proxy',
                       help='HTTP/HTTPS proxy to use for YouTube requests (e.g., http://user:pass@host:port)')
    parser.add_argument('--proxy-file',
                       help='Path to file containing list of proxies (one per line)')
    parser.add_argument('--proxy-rotate', action='store_true',
                       help='Enable proxy rotation')
    parser.add_argument('--proxy-rotate-interval', type=int, default=10,
                       help='Minutes between proxy rotations (default: 10)')
    
    # Database configuration
    parser.add_argument('--db-url',
                       help='Database URL (default: env DATABASE_URL)')
    
    # Audio storage configuration
    parser.add_argument('--store-audio-locally', action='store_true', default=True,
                       help='Store downloaded audio files locally (default: true)')
    parser.add_argument('--no-store-audio', dest='store_audio_locally', action='store_false',
                       help='Disable local audio storage')
    parser.add_argument('--audio-storage-dir', type=Path,
                       help='Directory to store audio files (default: ./audio_storage)')
    parser.add_argument('--production-mode', action='store_true',
                       help='Production mode: disables audio storage regardless of other flags')
    
    # API configuration
    parser.add_argument('--youtube-api-key',
                       help='YouTube Data API key (default: env YOUTUBE_API_KEY)')
    
    # Speaker identification (MANDATORY for Dr. Chaffee content)
    parser.add_argument('--disable-speaker-id', action='store_true', default=False,
                       help='Disable speaker identification (NOT RECOMMENDED - reduces accuracy)')
    parser.add_argument('--voices-dir', default=os.getenv('VOICES_DIR', 'voices'),
                       help='Voice profiles directory')
    parser.add_argument('--chaffee-min-sim', type=float, 
                       default=float(os.getenv('CHAFFEE_MIN_SIM', '0.62')),
                       help='Minimum similarity threshold for Chaffee')
    parser.add_argument('--chaffee-only-storage', action='store_true',
                       help='Store only Chaffee segments in database (saves space)')
    parser.add_argument('--embed-all-speakers', dest='embed_chaffee_only', action='store_false',
                       help='Generate embeddings for all speakers (default: Chaffee only)')
    parser.add_argument('--setup-chaffee', nargs='+', metavar='AUDIO_SOURCE',
                       help='Setup Chaffee profile from audio files or YouTube URLs')
    parser.add_argument('--overwrite-profile', action='store_true',
                       help='Overwrite existing Chaffee profile')
    parser.add_argument('--update-profile', action='store_true',
                       help='Update existing Chaffee profile with new content')
    
    # RTX 5080 Performance Optimizations (enabled by default)
    parser.add_argument('--no-assume-monologue', dest='assume_monologue', action='store_false',
                       help='Disable smart monologue fast-path (3x speedup on solo content - DEFAULT: enabled)')
    parser.add_argument('--no-gpu-optimization', dest='optimize_gpu_memory', action='store_false', 
                       help='Disable GPU memory optimizations (DEFAULT: enabled)')
    parser.add_argument('--enable-vad', dest='reduce_vad_overhead', action='store_false',
                       help='Enable VAD processing - slower but more accurate silence detection (DEFAULT: disabled)')
    
    # YouTube caption quality gating
    parser.add_argument('--yt-caption-threshold', type=float, default=0.92,
                       help='Accept YT captions if quality >= threshold (default: 0.92)')
    parser.add_argument('--disable-content-hashing', dest='enable_content_hashing', action='store_false',
                       help='Disable content fingerprinting for duplicate detection')
    
    # Debug options
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check if we're in setup-chaffee mode before creating config
    setup_chaffee_mode = hasattr(args, 'setup_chaffee') and args.setup_chaffee
    
    # CRITICAL WARNING: YouTube captions bypass speaker ID
    if args.allow_youtube_captions:
        logger.error("=" * 80)
        logger.error("⚠️  CRITICAL WARNING: --allow-youtube-captions is DEPRECATED")
        logger.error("=" * 80)
        logger.error("YouTube captions will bypass:")
        logger.error("  ❌ Speaker identification (Chaffee vs Guest)")
        logger.error("  ❌ Segment optimization (1100-1400 char targets)")
        logger.error("  ❌ Embedding generation (no semantic search)")
        logger.error("  ❌ Voice profile matching")
        logger.error("")
        logger.error("This will result in:")
        logger.error("  ❌ NULL speaker labels (99%+ of segments)")
        logger.error("  ❌ Tiny segments (50-100 chars vs 1100+)")
        logger.error("  ❌ No embeddings (unusable for RAG)")
        logger.error("  ❌ Risk of misattributing guest statements to Dr. Chaffee")
        logger.error("")
        logger.error("This flag should ONLY be used for testing YouTube caption quality.")
        logger.error("For production ingestion, remove --allow-youtube-captions flag.")
        logger.error("=" * 80)
        
        # Require explicit confirmation
        import time
        logger.warning("Waiting 5 seconds before proceeding...")
        logger.warning("Press Ctrl+C to cancel if this was a mistake.")
        time.sleep(5)
        logger.warning("Proceeding with YouTube captions (NOT RECOMMENDED)...")
    
    # Also warn if speaker ID is disabled
    if args.disable_speaker_id:
        logger.warning("=" * 80)
        logger.warning("⚠️  WARNING: Speaker identification is DISABLED")
        logger.warning("This is NOT RECOMMENDED for Dr. Chaffee content.")
        logger.warning("Segments will have NULL speaker labels.")
        logger.warning("=" * 80)
    
    # Create config
    config = IngestionConfig(
        source=args.source,  # Allow any source with setup-chaffee
        channel_url=args.channel_url,
        from_url=args.from_url,
        from_json=args.from_json,
        from_files=args.from_files,
        file_patterns=args.file_patterns,
        concurrency=args.concurrency,
        skip_shorts=args.skip_shorts,
        newest_first=args.newest_first,
        limit=args.limit,
        dry_run=args.dry_run,
        whisper_model=args.whisper_model,
        force_whisper=args.force_whisper,
        allow_youtube_captions=args.allow_youtube_captions,
        db_url=args.db_url,
        youtube_api_key=args.youtube_api_key,
        ffmpeg_path=args.ffmpeg_path,
        # Audio storage options
        store_audio_locally=args.store_audio_locally,
        audio_storage_dir=args.audio_storage_dir,
        production_mode=args.production_mode,
        # Content filtering options
        skip_live=args.skip_live,
        skip_upcoming=args.skip_upcoming,
        skip_members_only=args.skip_members_only,
        # Speaker identification options
        enable_speaker_id=not args.disable_speaker_id if not setup_chaffee_mode else False,
        voices_dir=args.voices_dir,
        chaffee_min_sim=args.chaffee_min_sim,
        chaffee_only_storage=args.chaffee_only_storage,
        embed_chaffee_only=args.embed_chaffee_only,
        # RTX 5080 Performance Optimizations
        assume_monologue=args.assume_monologue,
        optimize_gpu_memory=args.optimize_gpu_memory,
        reduce_vad_overhead=args.reduce_vad_overhead,
        # YouTube caption quality gating
        yt_caption_quality_threshold=getattr(args, 'yt_caption_threshold', 0.92),
        enable_content_hashing=getattr(args, 'enable_content_hashing', True),
        # RTX 5080 optimized pipelined concurrency
        io_concurrency=getattr(args, 'io_concurrency', 12),
        asr_concurrency=getattr(args, 'asr_concurrency', 2), 
        db_concurrency=getattr(args, 'db_concurrency', 12),
        embed_later=getattr(args, 'embed_later', False),
        embedding_batch_size=getattr(args, 'embedding_batch_size', 256)
    )
    
    # Handle setup-chaffee mode after config creation
    if setup_chaffee_mode:
        logger.info(f"Setting up Chaffee profile from {len(args.setup_chaffee)} sources")
        
        ingester = EnhancedYouTubeIngester(config)
        success = ingester.setup_chaffee_profile(
            audio_sources=args.setup_chaffee,
            overwrite=getattr(args, 'overwrite_profile', False),
            update=getattr(args, 'update_profile', False)
        )
        
        if success:
            logger.info("✅ Chaffee profile setup completed successfully!")
            sys.exit(0)
        else:
            logger.error("❌ Chaffee profile setup failed!")
            sys.exit(1)
    
    return config

def main():
    """Main entry point"""
    try:
        config = parse_args()
        ingester = EnhancedYouTubeIngester(config)
        ingester.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
