#!/usr/bin/env python3
"""
MULTI-MODEL PARALLEL TRANSCRIPTION - TRUE RTX 5080 UTILIZATION
Load 8-12 Whisper models simultaneously for maximum GPU saturation
"""

import os
import sys
import time
import logging
import tempfile
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Tuple, Optional
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class TranscriptResult:
    video_id: str
    audio_file: str
    segments: List[dict]
    duration: float
    model_id: int
    processing_time: float

class MultiModelTranscriber:
    """Multiple Whisper models running in parallel"""
    
    def __init__(self, num_models: int = 12, model_size: str = "base"):
        self.num_models = num_models
        self.model_size = model_size
        self.models = {}
        self.model_locks = {}
        self.results = []
        
    def initialize_models(self):
        """Initialize multiple Whisper models on GPU"""
        logger.info(f"🔥 Initializing {self.num_models} parallel Whisper models ({self.model_size})...")
        
        try:
            import faster_whisper
            
            for i in range(self.num_models):
                logger.info(f"Loading model {i+1}/{self.num_models}...")
                
                # Each model gets its own CUDA context
                model = faster_whisper.WhisperModel(
                    self.model_size,
                    device="cuda",
                    compute_type="float16",
                    # Use different device indices or let CUDA manage
                    device_index=0  # All on same GPU but different streams
                )
                
                self.models[i] = model
                self.model_locks[i] = threading.Lock()
                
            logger.info(f"✅ ALL {self.num_models} MODELS LOADED IN PARALLEL!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize models: {e}")
            return False
    
    def transcribe_with_model(self, model_id: int, video_id: str, audio_file: str) -> TranscriptResult:
        """Transcribe using a specific model"""
        start_time = time.time()
        
        try:
            with self.model_locks[model_id]:
                model = self.models[model_id]
                
                logger.info(f"🎯 Model {model_id}: Processing {video_id}")
                
                # Fast transcription settings
                segments, info = model.transcribe(
                    audio_file,
                    language="en",
                    beam_size=1,  # Fastest
                    word_timestamps=False,  # Faster
                    vad_filter=False  # Disable VAD for speed
                )
                
                segments_list = [
                    {
                        "start": seg.start,
                        "end": seg.end, 
                        "text": seg.text.strip()
                    }
                    for seg in segments
                ]
                
                processing_time = time.time() - start_time
                
                result = TranscriptResult(
                    video_id=video_id,
                    audio_file=audio_file,
                    segments=segments_list,
                    duration=info.duration,
                    model_id=model_id,
                    processing_time=processing_time
                )
                
                logger.info(f"✅ Model {model_id}: {video_id} -> {len(segments_list)} segments in {processing_time:.1f}s")
                return result
                
        except Exception as e:
            logger.error(f"❌ Model {model_id}: Failed {video_id} -> {e}")
            return TranscriptResult(
                video_id=video_id,
                audio_file=audio_file,
                segments=[],
                duration=0,
                model_id=model_id,
                processing_time=time.time() - start_time
            )
    
    def process_audio_files(self, audio_files: List[Tuple[str, str]]) -> List[TranscriptResult]:
        """Process multiple audio files using all models in parallel"""
        logger.info(f"🚀 PROCESSING {len(audio_files)} FILES WITH {self.num_models} PARALLEL MODELS")
        
        results = []
        
        # Use ThreadPoolExecutor to run all models simultaneously
        with ThreadPoolExecutor(max_workers=self.num_models) as executor:
            # Submit all files to available models
            future_to_info = {}
            
            for i, (video_id, audio_file) in enumerate(audio_files):
                model_id = i % self.num_models  # Round-robin assignment
                
                future = executor.submit(
                    self.transcribe_with_model,
                    model_id,
                    video_id,
                    audio_file
                )
                future_to_info[future] = (video_id, model_id)
            
            # Collect results as they complete
            for future in as_completed(future_to_info):
                video_id, model_id = future_to_info[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    logger.info(f"🎯 COMPLETED: {video_id} (Model {model_id}) - {len(result.segments)} segments")
                    
                except Exception as e:
                    logger.error(f"❌ FAILED: {video_id} (Model {model_id}) -> {e}")
        
        return results

def download_audio_files(video_ids: List[str], temp_dir: str) -> List[Tuple[str, str]]:
    """Download audio files quickly"""
    logger.info(f"📥 Downloading {len(video_ids)} audio files...")
    
    def download_single(video_id):
        try:
            cmd = [
                'yt-dlp',
                f'https://www.youtube.com/watch?v={video_id}',
                '-x', '--audio-format', 'wav',
                '--audio-quality', '0',
                '-o', f'{temp_dir}/{video_id}.%(ext)s',
                '--no-playlist',
                '--no-warnings'
            ]
            
            import subprocess
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                audio_file = f"{temp_dir}/{video_id}.wav"
                if os.path.exists(audio_file):
                    return (video_id, audio_file)
            return None
            
        except Exception as e:
            logger.error(f"Download failed {video_id}: {e}")
            return None
    
    # Download with high concurrency
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(download_single, video_ids))
    
    successful = [r for r in results if r is not None]
    logger.info(f"✅ Downloaded {len(successful)}/{len(video_ids)} audio files")
    return successful

def main():
    """Multi-model parallel transcription"""
    
    # Get video IDs from database
    try:
        import psycopg2
        from dotenv import load_dotenv
        load_dotenv()
        
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT video_id FROM ingest_state 
            WHERE status = 'pending' 
            ORDER BY updated_at DESC 
            LIMIT 24
        """)
        
        video_ids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Database error: {e}")
        # Test with Rick Roll
        video_ids = ["dQw4w9WgXcQ"] * 12
    
    if not video_ids:
        logger.error("No videos to process!")
        return
    
    logger.info(f"🎯 MULTI-MODEL PARALLEL PROCESSING: {len(video_ids)} videos")
    logger.info(f"🔥 Expected RTX 5080 utilization: 60-90%")
    
    # Initialize multi-model transcriber
    transcriber = MultiModelTranscriber(num_models=12, model_size="base")
    
    if not transcriber.initialize_models():
        logger.error("Failed to initialize models!")
        return
    
    with tempfile.TemporaryDirectory() as temp_dir:
        start_time = time.time()
        
        # Download audio files
        audio_files = download_audio_files(video_ids[:24], temp_dir)  # Limit to 24 for testing
        
        if not audio_files:
            logger.error("No audio files downloaded!")
            return
        
        # Process with multiple models in parallel
        logger.info("🚀 STARTING MULTI-MODEL PARALLEL TRANSCRIPTION!")
        
        results = transcriber.process_audio_files(audio_files)
        
        total_time = time.time() - start_time
        successful = [r for r in results if r.segments]
        
        logger.info(f"")
        logger.info(f"🏁 MULTI-MODEL PARALLEL PROCESSING COMPLETE!")
        logger.info(f"⏱️ Total time: {total_time:.1f}s")
        logger.info(f"✅ Successful: {len(successful)}/{len(audio_files)}")
        logger.info(f"🔥 Average processing time: {sum(r.processing_time for r in successful)/len(successful) if successful else 0:.1f}s per video")
        logger.info(f"🚀 Expected peak GPU utilization during processing: 60-90%")

if __name__ == "__main__":
    main()
