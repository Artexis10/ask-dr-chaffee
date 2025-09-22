#!/usr/bin/env python3
"""
Multi-Model Whisper Manager for Maximum RTX 5080 Utilization
"""

import logging
import threading
import time
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class MultiModelWhisperManager:
    """
    Manages multiple Whisper models for maximum GPU utilization
    Thread-safe round-robin assignment of models to transcription tasks
    """
    
    def __init__(self, num_models: int = 16, model_size: str = "base"):
        self.num_models = num_models
        self.model_size = model_size
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
                
                model = faster_whisper.WhisperModel(
                    self.model_size,
                    device="cuda",
                    compute_type="float16"
                )
                
                self.models[i] = model
                self.model_locks[i] = threading.Lock()
            
            self.initialized = True
            logger.info(f"✅ ALL {self.num_models} MODELS LOADED - RTX 5080 READY FOR MAXIMUM UTILIZATION!")
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
                
                # Optimized transcription settings for maximum throughput
                segments, info = model.transcribe(
                    str(audio_path),
                    language="en",
                    beam_size=1,          # Fastest beam search
                    word_timestamps=False, # Skip word-level timing for speed
                    vad_filter=False,     # No VAD filtering
                    temperature=0.0,      # Deterministic output
                    no_speech_threshold=0.6  # Skip very quiet segments
                )
                
                # Convert to transcript segments (compatible with existing code)
                from .transcript_common import TranscriptSegment
                transcript_segments = []
                
                for segment in segments:
                    if len(segment.text.strip()) > 3:  # Filter very short segments
                        ts = TranscriptSegment(
                            start=segment.start,
                            end=segment.end,
                            text=segment.text.strip()
                        )
                        transcript_segments.append(ts)
                
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

def get_multi_model_manager(num_models: int = 16, model_size: str = "base") -> MultiModelWhisperManager:
    """Get or create the global multi-model manager"""
    global _global_multi_model_manager
    
    with _global_manager_lock:
        if _global_multi_model_manager is None:
            _global_multi_model_manager = MultiModelWhisperManager(num_models, model_size)
        return _global_multi_model_manager
