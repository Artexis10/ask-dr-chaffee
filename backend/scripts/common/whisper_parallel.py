#!/usr/bin/env python3
"""
Parallel Whisper transcription using ProcessPoolExecutor to bypass GIL
"""

import os
import logging
import tempfile
from typing import List, Tuple, Optional
import concurrent.futures
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TranscriptSegment:
    """Single transcript segment with timing"""
    start_time: float
    end_time: float
    text: str

def transcribe_audio_worker(audio_file_path: str, model_size: str = "small.en") -> List[TranscriptSegment]:
    """
    Worker function for ProcessPoolExecutor - transcribes a single audio file
    Must be picklable (no complex objects)
    """
    try:
        # Import inside worker to avoid serialization issues
        import faster_whisper
        
        # Initialize model in this process
        model = faster_whisper.WhisperModel(
            model_size,
            device="cuda",
            compute_type="float16"
        )
        
        logger.info(f"Worker transcribing: {audio_file_path}")
        
        # Transcribe
        segments, info = model.transcribe(
            audio_file_path,
            language="en",
            vad_filter=False,  # Disable aggressive VAD
            beam_size=5,
            word_timestamps=True
        )
        
        # Convert to simple data structures
        result_segments = []
        for segment in segments:
            result_segments.append(TranscriptSegment(
                start_time=segment.start,
                end_time=segment.end,
                text=segment.text.strip()
            ))
        
        logger.info(f"Worker completed: {len(result_segments)} segments from {audio_file_path}")
        return result_segments
        
    except Exception as e:
        logger.error(f"Worker transcription failed for {audio_file_path}: {e}")
        return []

class ParallelWhisperTranscriber:
    """Parallel Whisper transcription using ProcessPoolExecutor"""
    
    def __init__(self, max_workers: int = 12, model_size: str = "small.en"):
        self.max_workers = max_workers
        self.model_size = model_size
        self.executor = None
    
    def __enter__(self):
        self.executor = concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.executor:
            self.executor.shutdown(wait=True)
    
    def transcribe_batch(self, audio_files: List[str]) -> List[Tuple[str, List[TranscriptSegment]]]:
        """
        Transcribe multiple audio files in parallel
        Returns list of (audio_file, segments) tuples
        """
        if not self.executor:
            raise RuntimeError("ParallelWhisperTranscriber must be used as context manager")
        
        logger.info(f"Starting parallel transcription of {len(audio_files)} files")
        
        # Submit all jobs
        future_to_file = {
            self.executor.submit(transcribe_audio_worker, audio_file, self.model_size): audio_file
            for audio_file in audio_files
        }
        
        results = []
        for future in concurrent.futures.as_completed(future_to_file):
            audio_file = future_to_file[future]
            try:
                segments = future.result()
                results.append((audio_file, segments))
                logger.info(f"Completed transcription: {audio_file} -> {len(segments)} segments")
            except Exception as e:
                logger.error(f"Failed transcription: {audio_file} -> {e}")
                results.append((audio_file, []))
        
        return results
    
    def transcribe_single(self, audio_file: str) -> List[TranscriptSegment]:
        """Transcribe a single audio file"""
        results = self.transcribe_batch([audio_file])
        if results:
            return results[0][1]
        return []

# Convenience function for single file transcription
def transcribe_audio_parallel(audio_file: str, max_workers: int = 12) -> List[TranscriptSegment]:
    """Transcribe single audio file using parallel worker"""
    with ParallelWhisperTranscriber(max_workers=max_workers) as transcriber:
        return transcriber.transcribe_single(audio_file)

if __name__ == "__main__":
    # Test the parallel transcriber
    import sys
    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        segments = transcribe_audio_parallel(audio_file, max_workers=4)
        print(f"Transcribed {len(segments)} segments:")
        for seg in segments[:3]:  # Show first 3
            print(f"  {seg.start_time:.1f}s-{seg.end_time:.1f}s: {seg.text}")
