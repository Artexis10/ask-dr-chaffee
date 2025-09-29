#!/usr/bin/env python3
"""
Test diarization and speaker identification with pyannote
"""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_diarization():
    """Test diarization and speaker identification with pyannote"""
    try:
        # Import necessary modules
        from backend.scripts.common.enhanced_asr import EnhancedASR
        from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig
        from backend.scripts.common.downloader import create_downloader
        
        # Create downloader
        downloader = create_downloader()
        
        # Create ASR config with appropriate settings
        config = EnhancedASRConfig(
            overrides={
                'chaffee_min_sim': '0.62',
                'guest_min_sim': '0.82',
                'attr_margin': '0.05',
                'assume_monologue': 'false'  # This is an interview, so don't assume monologue
            }
        )
        
        # Create Enhanced ASR
        asr = EnhancedASR(config)
        
        # Define test video - use an interview video with a guest
        video_id = "I0phGC4HmrU"  # Interview video with guest
        
        # Download audio if needed
        audio_dir = Path("audio_storage")
        audio_dir.mkdir(exist_ok=True)
        
        audio_path = audio_dir / f"{video_id}.wav"
        if not audio_path.exists():
            logger.info(f"Downloading audio for {video_id}")
            downloaded_path = downloader.download_audio(video_id)
            
            # Copy to audio_storage
            import shutil
            shutil.copy(downloaded_path, audio_path)
            
        logger.info(f"Using audio file: {audio_path}")
        
        # Test diarization directly
        logger.info("Testing diarization...")
        diarization_segments = asr._perform_diarization(str(audio_path))
        
        if diarization_segments:
            logger.info(f"Diarization found {len(diarization_segments)} segments")
            # Count unique speakers
            unique_speakers = len(set(s[2] for s in diarization_segments))
            logger.info(f"Unique speakers detected: {unique_speakers}")
            
            # Show first few segments
            for i, (start, end, speaker_id) in enumerate(diarization_segments[:10]):
                logger.info(f"Segment {i}: {start:.2f}s - {end:.2f}s -> Speaker {speaker_id}")
        else:
            logger.error("Diarization failed")
            return False
            
        # Test speaker identification
        logger.info("Testing speaker identification...")
        speaker_segments = asr._identify_speakers(str(audio_path), diarization_segments)
        
        if speaker_segments:
            logger.info(f"Speaker identification found {len(speaker_segments)} segments")
            # Count by speaker
            speaker_counts = {}
            for segment in speaker_segments:
                speaker = segment.speaker
                speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
                
            logger.info(f"Speaker distribution: {speaker_counts}")
            
            # Show first few segments
            for i, segment in enumerate(speaker_segments[:10]):
                logger.info(f"Segment {i}: {segment.start:.2f}s - {segment.end:.2f}s -> {segment.speaker} (conf: {segment.confidence:.3f})")
        else:
            logger.error("Speaker identification failed")
            return False
            
        # Test full transcription with speaker identification
        logger.info("Testing full transcription with speaker identification")
        result = asr.transcribe_with_speaker_id(str(audio_path))
        
        if not result:
            logger.error("Transcription failed")
            return False
                
        # Count speaker labels
        speaker_counts = {}
        for segment in result.segments:
            speaker = segment.get('speaker', 'Unknown')
            speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
                
        logger.info(f"Final speaker distribution: {speaker_counts}")
        
        # Show first few segments
        for i, segment in enumerate(result.segments[:5]):
            logger.info(f"Segment {i}: {segment.get('speaker', 'Unknown')} - {segment.get('text', '')[:50]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing diarization: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_diarization()
