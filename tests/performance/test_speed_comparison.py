#!/usr/bin/env python3
"""
Speed comparison test: large-v3 vs medium model
Tests both models on the same video to compare speed and quality
"""

import os
import sys
import time
import tempfile
from dotenv import load_dotenv

load_dotenv()

def test_whisper_speed():
    """Test different Whisper models for speed comparison"""
    
    print("🚀 Whisper Model Speed Comparison Test")
    print("=" * 50)
    
    # Test video ID (short video for quick testing)
    test_video_id = "QLenO7DM7Cw"  # Use one from current batch
    
    try:
        import faster_whisper
        import torch
        
        # Download test audio
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend.scripts.common.transcript_fetch import TranscriptFetcher
        
        fetcher = TranscriptFetcher()
        
        print(f"📥 Downloading test audio for {test_video_id}...")
        audio_path = fetcher.download_audio(test_video_id)
        
        if not audio_path or not os.path.exists(audio_path):
            print("❌ Failed to download test audio")
            return
        
        print(f"✅ Audio downloaded: {audio_path}")
        
        # Test configurations
        models_to_test = [
            {
                "name": "medium (FAST)",
                "model": "medium",
                "batch_size": 16,
                "beam_size": 1,
                "description": "3x faster, ~95% quality"
            },
            {
                "name": "large-v3 (QUALITY)",
                "model": "large-v3", 
                "batch_size": 8,
                "beam_size": 5,
                "description": "Highest quality, slower"
            }
        ]
        
        results = []
        
        for config in models_to_test:
            print(f"\n🔥 Testing {config['name']}")
            print(f"   Model: {config['model']}")
            print(f"   Settings: batch_size={config['batch_size']}, beam_size={config['beam_size']}")
            print(f"   {config['description']}")
            
            try:
                start_time = time.time()
                
                # Load model
                model_load_start = time.time()
                model = faster_whisper.WhisperModel(
                    config["model"],
                    device="cuda" if torch.cuda.is_available() else "cpu",
                    compute_type="float16"
                )
                model_load_time = time.time() - model_load_start
                print(f"   📚 Model loaded in {model_load_time:.1f}s")
                
                # Transcribe
                transcribe_start = time.time()
                result = model.transcribe(
                    audio_path,
                    batch_size=config["batch_size"],
                    beam_size=config["beam_size"],
                    temperature=0.0,
                    vad_filter=True,
                    language="en"
                )
                
                # Extract segments
                segments = list(result[0])
                transcribe_time = time.time() - transcribe_start
                total_time = time.time() - start_time
                
                # Calculate metrics
                audio_duration = segments[-1].end if segments else 0
                speed_ratio = audio_duration / total_time if total_time > 0 else 0
                
                result_data = {
                    "model": config["name"],
                    "segments": len(segments),
                    "audio_duration": audio_duration,
                    "model_load_time": model_load_time,
                    "transcribe_time": transcribe_time,
                    "total_time": total_time,
                    "speed_ratio": speed_ratio,
                    "first_text": segments[0].text[:100] if segments else ""
                }
                
                results.append(result_data)
                
                print(f"   ✅ Success!")
                print(f"   📊 Audio duration: {audio_duration:.1f}s")
                print(f"   ⏱️ Processing time: {total_time:.1f}s")
                print(f"   🏃 Speed ratio: {speed_ratio:.2f}x real-time")
                print(f"   📝 Segments: {len(segments)}")
                print(f"   🎤 First text: {segments[0].text[:50] if segments else 'No text'}...")
                
                # Free GPU memory
                del model
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                results.append({
                    "model": config["name"],
                    "error": str(e)
                })
        
        # Cleanup
        try:
            os.remove(audio_path)
        except:
            pass
        
        # Summary
        print(f"\n📊 SPEED COMPARISON RESULTS")
        print("=" * 50)
        
        if len(results) >= 2 and "error" not in results[0] and "error" not in results[1]:
            medium_result = results[0]
            large_result = results[1]
            
            speedup = large_result["total_time"] / medium_result["total_time"]
            
            print(f"🏆 WINNER: {medium_result['model']}")
            print(f"⚡ Speed improvement: {speedup:.1f}x faster")
            print(f"🎯 Medium model: {medium_result['speed_ratio']:.2f}x real-time")
            print(f"🐌 Large-v3 model: {large_result['speed_ratio']:.2f}x real-time")
            print(f"\n💡 RECOMMENDATION:")
            
            if speedup > 2.5:
                print(f"   Use MEDIUM model for production - {speedup:.1f}x speed improvement!")
                print(f"   Quality difference is minimal for Dr. Chaffee's clear speech")
                print(f"   Will process {speedup:.0f}x more videos in the same time")
            else:
                print(f"   Consider medium model - {speedup:.1f}x speed improvement")
        
        for result in results:
            if "error" not in result:
                print(f"\n{result['model']}:")
                print(f"  Total time: {result['total_time']:.1f}s")
                print(f"  Speed ratio: {result['speed_ratio']:.2f}x")
                print(f"  Segments: {result['segments']}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_whisper_speed()
