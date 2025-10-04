#!/usr/bin/env python3

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv
import json
from typing import List, Dict, Any

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_speaker_id_scenarios(video_ids: List[str], output_dir: str = "test_results"):
    """
    Test speaker identification on different content types
    
    Args:
        video_ids: List of YouTube video IDs to test
        output_dir: Directory to save test results
    """
    try:
        # Import required modules
        from backend.scripts.common.enhanced_asr import EnhancedASR
        from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig
        from backend.scripts.common.enhanced_transcript_fetch import EnhancedTranscriptFetcher
        from backend.scripts.common.asr_output_formats import ASROutputFormatter
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Create config with our settings
        config = EnhancedASRConfig()
        
        # Print configuration
        print(f"\n=== Configuration ===")
        print(f"Chaffee Min Sim: {config.chaffee_min_sim}")
        print(f"Guest Min Sim: {config.guest_min_sim}")
        print(f"Attribution Margin: {config.attr_margin}")
        print(f"Voices Dir: {config.voices_dir}")
        print(f"Whisper Model: {config.whisper.model}")
        
        # Initialize ASR system
        asr = EnhancedASR(config)
        
        # Initialize transcript fetcher
        fetcher = EnhancedTranscriptFetcher(
            enable_speaker_id=True,
            voices_dir=config.voices_dir
        )
        
        # Initialize output formatter
        formatter = ASROutputFormatter(unknown_label=config.unknown_label)
        
        # Test each video
        results = []
        for i, video_id in enumerate(video_ids, 1):
            print(f"\n=== Testing Video {i}/{len(video_ids)}: {video_id} ===")
            
            # Download audio
            audio_path = fetcher._download_audio_for_enhanced_asr(video_id)
            
            if not audio_path or not os.path.exists(audio_path):
                print(f"ERROR: Could not download audio for {video_id}")
                continue
                
            print(f"Downloaded audio: {audio_path}")
            
            # Transcribe with speaker ID
            print(f"Transcribing with speaker identification...")
            result = asr.transcribe_with_speaker_id(audio_path)
            
            if not result:
                print(f"ERROR: Transcription failed for {video_id}")
                continue
            
            # Generate summary
            try:
                summary = formatter.generate_summary_report(result)
                # Replace Unicode characters that might cause encoding issues
                summary = summary.replace('\u2713', 'v')
                print(f"\n{summary}")
            except UnicodeEncodeError:
                print("\nSummary contains characters that can't be displayed in the current console encoding")
                print(f"Speaker distribution: {result.metadata.get('speaker_distribution', {})}")
                print(f"Chaffee percentage: {result.metadata.get('chaffee_percentage', 0)}%")
            
            # Save results
            json_path = os.path.join(output_dir, f"{video_id}_result.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(formatter.to_json(result, pretty=True))
            
            # Save SRT for convenience
            srt_path = os.path.join(output_dir, f"{video_id}_subtitles.srt")
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(formatter.to_srt(result))
            
            # Extract speaker stats
            speaker_stats = {
                "video_id": video_id,
                "chaffee_percentage": result.metadata.get("summary", {}).get("chaffee_percentage", 0),
                "speaker_distribution": result.metadata.get("summary", {}).get("speaker_time_percentages", {}),
                "segments_count": len(result.segments) if hasattr(result, 'segments') else 0
            }
            
            results.append(speaker_stats)
            
            # Clean up
            try:
                os.unlink(audio_path)
                print(f"Cleaned up: {audio_path}")
            except:
                pass
        
        # Save overall results
        overall_path = os.path.join(output_dir, "overall_results.json")
        with open(overall_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        # Print overall summary
        print("\n=== Overall Results ===")
        for result in results:
            print(f"Video {result['video_id']}:")
            # Convert numpy values to regular floats for cleaner output
            chaffee_pct = float(result['chaffee_percentage']) if result['chaffee_percentage'] else 0.0
            print(f"  Chaffee: {chaffee_pct:.1f}%")
            
            # Convert speaker distribution to regular floats
            clean_dist = {}
            for speaker, pct in result['speaker_distribution'].items():
                clean_dist[speaker] = float(pct) if pct else 0.0
            print(f"  Distribution: {clean_dist}")
            print(f"  Segments: {result['segments_count']}")
        
        print(f"\nDetailed results saved to: {output_dir}")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description="Test speaker identification on different content types")
    parser.add_argument("video_ids", nargs="+", help="YouTube video IDs to test")
    parser.add_argument("--output-dir", default="test_results", help="Directory to save test results")
    
    args = parser.parse_args()
    
    success = test_speaker_id_scenarios(args.video_ids, args.output_dir)
    
    if success:
        print("\nTesting completed successfully!")
    else:
        print("\nTesting failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
