#!/usr/bin/env python3

import os
import sys
import tempfile
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_real_youtube_audio():
    """Test voice enrollment with actual YouTube audio"""
    try:
        print("Testing with real YouTube audio...")
        
        # Download the same video audio that was just processed
        from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
        
        fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=True,
            voices_dir="backend/voices"
        )
        
        video_id = "3zW8BG4wYt0"
        print(f"Downloading audio for video: {video_id}")
        
        # Download the audio file
        audio_path = fetcher._download_audio_for_enhanced_asr(video_id)
        
        if not audio_path or not os.path.exists(audio_path):
            print("ERROR: Failed to download audio")
            return False
            
        print(f"Downloaded audio: {audio_path}")
        print(f"File size: {os.path.getsize(audio_path)} bytes")
        
        # Test voice enrollment on this real audio
        from backend.scripts.common.voice_enrollment import VoiceEnrollment
        
        enrollment = VoiceEnrollment(voices_dir="backend/voices")
        
        print("\nTesting embedding extraction from real YouTube audio...")
        embeddings = enrollment._extract_embeddings_from_audio(audio_path)
        
        print(f"Extracted {len(embeddings)} embeddings from real YouTube audio")
        
        if len(embeddings) == 0:
            print("ERROR: No embeddings extracted from real YouTube audio!")
            print("This explains why Dr. Chaffee isn't being detected.")
            
            # Let's check the audio properties
            import librosa
            import numpy as np
            
            audio, sr = librosa.load(audio_path, sr=16000)
            print(f"\nAudio analysis:")
            print(f"  Duration: {len(audio) / sr:.1f} seconds")
            print(f"  Sample rate: {sr} Hz")
            print(f"  Max amplitude: {np.max(np.abs(audio)):.6f}")
            print(f"  Mean amplitude: {np.mean(np.abs(audio)):.6f}")
            print(f"  RMS energy: {np.sqrt(np.mean(audio**2)):.6f}")
            
            # Test the sliding window manually
            window_size = 5 * sr
            stride = int(2.5 * sr)
            
            segments_above_threshold = 0
            segments_below_threshold = 0
            
            for start in range(0, min(len(audio) - window_size + 1, 10 * stride), stride):
                end = start + window_size
                segment = audio[start:end]
                energy = np.mean(np.abs(segment))
                
                if energy < 0.001:
                    segments_below_threshold += 1
                else:
                    segments_above_threshold += 1
                    
                if segments_above_threshold + segments_below_threshold <= 5:  # First 5 segments
                    print(f"  Segment {segments_above_threshold + segments_below_threshold}: energy={energy:.6f} ({'SKIP' if energy < 0.001 else 'PROCESS'})")
            
            print(f"\nFirst 10 segments analysis:")
            print(f"  Above threshold (>=0.001): {segments_above_threshold}")
            print(f"  Below threshold (<0.001): {segments_below_threshold}")
            
            if segments_above_threshold == 0:
                print("ERROR: All segments below energy threshold!")
                print("SOLUTION: Lower the energy threshold or check audio quality")
            
            return False
        else:
            print("SUCCESS: Real YouTube audio produces embeddings!")
            
            # Test similarity with Dr. Chaffee's profile
            chaffee_profile = enrollment.load_profile("chaffee")
            if chaffee_profile is not None:
                print(f"\nTesting similarity with Dr. Chaffee's profile...")
                
                similarities = []
                for i, embedding in enumerate(embeddings[:5]):  # Test first 5
                    sim = enrollment.compute_similarity(embedding, chaffee_profile)
                    similarities.append(sim)
                    print(f"  Embedding {i+1}: similarity = {sim:.3f}")
                
                max_sim = max(similarities) if similarities else 0
                avg_sim = sum(similarities) / len(similarities) if similarities else 0
                
                print(f"\nSimilarity stats:")
                print(f"  Max similarity: {max_sim:.3f}")
                print(f"  Average similarity: {avg_sim:.3f}")
                
                # Check against the profile's threshold
                profile_info = enrollment.get_profile_info("chaffee")
                if profile_info:
                    threshold = profile_info['threshold']
                    print(f"  Dr. Chaffee's threshold: {threshold:.3f}")
                    
                    if max_sim >= threshold:
                        print(f"SUCCESS: Dr. Chaffee detected (max_sim {max_sim:.3f} >= threshold {threshold:.3f})!")
                        return True
                    else:
                        print(f"ISSUE: Dr. Chaffee not detected (max_sim {max_sim:.3f} < threshold {threshold:.3f})")
                        print(f"SOLUTION: Lower threshold to ~{max_sim * 0.8:.3f} or retrain profile")
                        return False
                else:
                    print("ERROR: Could not get Dr. Chaffee's profile info")
                    return False
            else:
                print("ERROR: Could not load Dr. Chaffee's profile")
                return False
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up audio file
        if 'audio_path' in locals() and audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
                print(f"Cleaned up: {audio_path}")
            except:
                print(f"Could not clean up: {audio_path}")

if __name__ == "__main__":
    print("TESTING REAL YOUTUBE AUDIO FOR SPEAKER IDENTIFICATION")
    print("=" * 70)
    
    success = test_real_youtube_audio()
    
    print("=" * 70)
    if success:
        print("SUCCESS: Dr. Chaffee detection works with real YouTube audio!")
    else:
        print("ISSUE: Dr. Chaffee detection needs adjustment for real YouTube audio")
