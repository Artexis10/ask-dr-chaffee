#!/usr/bin/env python3
"""
PIPELINE SEPARATED PROCESSING - Solve the I/O bottleneck
Phase 1: Download all audio files (CPU/I/O intensive)  
Phase 2: Batch process all audio through GPU (GPU intensive)
"""

import os
import sys
import time
import subprocess
import logging
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_audio_batch(video_ids, temp_dir):
    """Phase 1: Download all audio files in parallel"""
    logger.info(f"🔄 PHASE 1: Downloading {len(video_ids)} audio files...")
    
    def download_single(video_id):
        try:
            cmd = [
                'yt-dlp',
                f'https://www.youtube.com/watch?v={video_id}',
                '-x', '--audio-format', 'wav',
                '--audio-quality', '0',
                '-o', f'{temp_dir}/{video_id}.%(ext)s',
                '--no-playlist'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                audio_file = f"{temp_dir}/{video_id}.wav"
                if os.path.exists(audio_file):
                    return video_id, audio_file
            return video_id, None
        except Exception as e:
            logger.error(f"Download failed for {video_id}: {e}")
            return video_id, None
    
    # Download with high concurrency (I/O bound)
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(download_single, video_ids))
    
    successful = [(vid, path) for vid, path in results if path]
    logger.info(f"✅ PHASE 1 COMPLETE: {len(successful)}/{len(video_ids)} audio files downloaded")
    return successful

def gpu_batch_transcribe(audio_files, batch_size=8):
    """Phase 2: Pure GPU batch transcription"""
    logger.info(f"🔥 PHASE 2: GPU batch transcription of {len(audio_files)} files")
    
    # Use smaller model for maximum throughput
    cmd_base = [
        sys.executable, '-c', '''
import faster_whisper
import sys
import json

audio_files = sys.argv[1].split(",")
model = faster_whisper.WhisperModel("base", device="cuda", compute_type="float16")

results = {}
for audio_file in audio_files:
    try:
        segments, info = model.transcribe(audio_file, language="en", beam_size=1)  # Fast settings
        segments_list = [{"start": seg.start, "end": seg.end, "text": seg.text} for seg in segments]
        results[audio_file] = {"segments": segments_list, "duration": info.duration}
        print(f"✅ Transcribed: {audio_file} -> {len(segments_list)} segments")
    except Exception as e:
        results[audio_file] = {"error": str(e)}
        print(f"❌ Failed: {audio_file} -> {e}")

print("RESULTS:", json.dumps(results))
''']
    
    all_results = {}
    
    # Process in batches to maximize GPU utilization
    for i in range(0, len(audio_files), batch_size):
        batch = audio_files[i:i+batch_size]
        batch_paths = [path for _, path in batch]
        
        logger.info(f"🚀 GPU Batch {i//batch_size + 1}: Processing {len(batch_paths)} files")
        
        try:
            cmd = cmd_base + [",".join(batch_paths)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0 and "RESULTS:" in result.stdout:
                json_str = result.stdout.split("RESULTS:")[1].strip()
                batch_results = json.loads(json_str)
                all_results.update(batch_results)
            else:
                logger.error(f"Batch failed: {result.stderr}")
                
        except Exception as e:
            logger.error(f"GPU batch error: {e}")
    
    logger.info(f"🎯 PHASE 2 COMPLETE: {len(all_results)} files processed")
    return all_results

def main():
    """Pipeline separated processing"""
    
    # Get actual video IDs from database
    logger.info("📋 Getting pending video IDs from database...")
    
    try:
        import psycopg2
        from dotenv import load_dotenv
        load_dotenv()
        
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        # Get first 50 pending videos for testing
        cursor.execute("""
            SELECT video_id FROM ingest_state 
            WHERE status = 'pending' 
            ORDER BY updated_at DESC 
            LIMIT 50
        """)
        
        video_ids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        if not video_ids:
            logger.error("No pending videos found!")
            return
            
    except Exception as e:
        logger.error(f"Database error: {e}")
        # Fallback to test videos
        video_ids = ["dQw4w9WgXcQ", "JGwWNGJdvx8", "fJ9rUzIMcZQ"] * 5
    
    logger.info(f"🎯 PIPELINE PROCESSING: {len(video_ids)} videos")
    logger.info("📊 Expected improvement: 2-3x faster due to I/O/GPU separation")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        start_time = time.time()
        
        # PHASE 1: Download all audio (I/O intensive, high concurrency)
        audio_files = download_audio_batch(video_ids, temp_dir)
        phase1_time = time.time() - start_time
        
        # PHASE 2: Pure GPU processing (GPU intensive, optimal batching)
        phase2_start = time.time()
        results = gpu_batch_transcribe(audio_files, batch_size=8)
        phase2_time = time.time() - phase2_start
        
        total_time = time.time() - start_time
        
        logger.info(f"")
        logger.info(f"🏁 PIPELINE PROCESSING COMPLETE")
        logger.info(f"📊 Phase 1 (Download): {phase1_time:.1f}s")
        logger.info(f"🔥 Phase 2 (GPU): {phase2_time:.1f}s") 
        logger.info(f"⏱️ Total time: {total_time:.1f}s")
        logger.info(f"✅ Success rate: {len(results)}/{len(video_ids)} = {len(results)/len(video_ids)*100:.1f}%")
        logger.info(f"🚀 Expected GPU utilization during Phase 2: 60-90%")

if __name__ == "__main__":
    main()
