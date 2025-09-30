#!/usr/bin/env python3
"""
Multi-Model Whisper Manager for Maximum RTX 5080 Utilization
"""

import logging
import threading
import time
import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class MultiModelWhisperManager:
    """
    Manages multiple Whisper models for maximum GPU utilization
    Thread-safe round-robin assignment of models to transcription tasks
    """
    
    def __init__(self, num_models: int = 2, model_size: str = None):
        # Use environment variable or default to large-v3
        self.model_size = model_size or os.getenv('WHISPER_MODEL_ENHANCED', 'large-v3')
        self.num_models = num_models
        # model_size is set above
        self.models = {}
        self.model_locks = {}
        self.model_assignment_lock = threading.Lock()
        self.next_model_id = 0
        self.initialized = False
        
    def initialize_models(self):
        """Initialize all Whisper models on GPU"""
        if self.initialized:
            return True
            
        logger.info(f"🔥 Loading {self.num_models} parallel Whisper models ({self.model_size})...")
        
        try:
            import faster_whisper
            
            for i in range(self.num_models):
                logger.info(f"Loading model {i+1}/{self.num_models}...")
                
                # Get compute type from environment or default to float16
                compute_type = os.getenv('WHISPER_COMPUTE', 'float16')
                device = os.getenv('WHISPER_DEVICE', 'cuda')
                
                logger.info(f"Loading model {i+1}/{self.num_models} ({self.model_size}) on {device} with {compute_type}")
                
                model = faster_whisper.WhisperModel(
                    self.model_size,
                    device=device,
                    compute_type=compute_type
                )
                
                self.models[i] = model
                self.model_locks[i] = threading.Lock()
            
            self.initialized = True
            logger.info(f"✅ ALL {self.num_models} MODELS LOADED - GPU READY FOR MAXIMUM UTILIZATION!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize multi-model Whisper: {e}")
            return False
    
    def get_next_model_id(self) -> int:
        """Get next available model ID using round-robin"""
        with self.model_assignment_lock:
            model_id = self.next_model_id
            self.next_model_id = (self.next_model_id + 1) % self.num_models
            return model_id
    
    def transcribe_with_multi_model(self, audio_path: Path, model_name: str = None) -> Tuple[List, Dict[str, Any]]:
        """
        Transcribe using an available model from the pool
        This replaces the single-model transcription in transcript_fetch.py
        """
        if not self.initialized:
            if not self.initialize_models():
                raise RuntimeError("Failed to initialize multi-model Whisper")
        
        # Get next available model
        model_id = self.get_next_model_id()
        start_time = time.time()
        
        try:
            with self.model_locks[model_id]:
                model = self.models[model_id]
                
                logger.info(f"🎯 Model {model_id}: Transcribing {audio_path.name}")
                
                # CRITICAL FIX: Convert Path to native OS string format to avoid utf_8_encode errors
                # On Windows, faster-whisper's internal C libraries expect native string format
                import os
                if isinstance(audio_path, Path):
                    # Use os.fspath() which is the official way to convert Path to OS-native string
                    audio_path_str = os.fspath(audio_path)
                else:
                    audio_path_str = str(audio_path)
                
                # DEBUG: Log the type and representation
                logger.debug(f"🐛 Model {model_id}: audio_path type={type(audio_path)}, audio_path_str type={type(audio_path_str)}, isinstance bytes={isinstance(audio_path_str, bytes)}")
                logger.debug(f"🐛 Model {model_id}: audio_path_str repr={repr(audio_path_str)}")
                
                # Ensure it's a proper string, not bytes
                if isinstance(audio_path_str, bytes):
                    logger.warning(f"⚠️ Model {model_id}: audio_path_str IS BYTES, decoding...")
                    audio_path_str = audio_path_str.decode('utf-8', errors='replace')
                
                # Final type check
                if not isinstance(audio_path_str, str):
                    raise TypeError(f"audio_path_str must be str, got {type(audio_path_str)}: {repr(audio_path_str)}")
                
                # Optimized transcription settings for maximum throughput
                logger.info(f"🎯 Model {model_id}: Starting transcription for {os.path.basename(audio_path_str)}")
                segments, info = model.transcribe(
                    audio_path_str,  # Use the properly converted string
                    language="en",
                    beam_size=1,          # Fastest beam search
                    word_timestamps=False, # Skip word-level timing for speed
                    vad_filter=False,     # No VAD filtering
                    temperature=0.0,      # Deterministic output
                    no_speech_threshold=0.6  # Skip very quiet segments
                )
                logger.info(f"🎯 Model {model_id}: Transcription completed, processing segments...")
                
                # Convert to transcript segments (compatible with existing code)
                from .transcript_common import TranscriptSegment
                transcript_segments = []
                
                # FIX: Process segments with timeout and chunked processing
                try:
                    segment_count = 0
                    max_segments = 3000  # Reasonable limit to prevent infinite processing
                    
                    for i, segment in enumerate(segments):
                        if i >= max_segments:
                            logger.warning(f"🎯 Model {model_id}: Reached segment limit ({max_segments}), stopping")
                            break
                            
                        # Ensure text is a proper string (avoid bytes on Windows)
                        text_value = segment.text.decode('utf-8', errors='replace') if isinstance(segment.text, bytes) else str(segment.text)
                        text_value = text_value.strip()
                        if len(text_value) > 3:  # Filter very short segments
                            ts = TranscriptSegment(
                                start=segment.start,
                                end=segment.end,
                                text=text_value
                            )
                            transcript_segments.append(ts)
                            segment_count += 1
                            
                        # Progress logging every 100 segments
                        if (i + 1) % 100 == 0:
                            logger.info(f"🎯 Model {model_id}: Processed {i + 1} segments, {segment_count} valid")
                    
                    logger.info(f"🎯 Model {model_id}: Completed with {segment_count} valid segments from {i + 1 if 'i' in locals() else 0} total")
                    
                except Exception as e:
                    logger.error(f"❌ Model {model_id}: Segment processing failed: {e}")
                    raise
                
                processing_time = time.time() - start_time
                
                metadata = {
                    "model": self.model_size,
                    "model_id": model_id,
                    "multi_model_processing": True,
                    "processing_time": processing_time,
                    "segments_count": len(transcript_segments),
                    "detected_language": info.language,
                    "language_probability": info.language_probability,
                    "duration": info.duration
                }
                
                logger.info(f"✅ Model {model_id}: {audio_path.name} -> {len(transcript_segments)} segments in {processing_time:.1f}s")
                return transcript_segments, metadata
                
        except Exception as e:
            logger.error(f"❌ Model {model_id}: Failed {audio_path.name} -> {e}")
            # Return empty result with error metadata
            return [], {
                "model": self.model_size,
                "model_id": model_id,
                "error": str(e),
                "processing_time": time.time() - start_time
            }

# Global instance - shared across all threads
_global_multi_model_manager = None
_global_manager_lock = threading.Lock()

def get_multi_model_manager(num_models: int = 2, model_size: str = None) -> MultiModelWhisperManager:
    """Get or create the global multi-model manager"""
    global _global_multi_model_manager
    
    with _global_manager_lock:
        if _global_multi_model_manager is None:
            _global_multi_model_manager = MultiModelWhisperManager(num_models, model_size)
        return _global_multi_model_manager
