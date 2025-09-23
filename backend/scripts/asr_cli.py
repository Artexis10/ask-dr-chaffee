#!/usr/bin/env python3
"""
Main CLI interface for Enhanced ASR system with speaker identification
Provides unified access to voice enrollment, transcription, and output formatting
"""

import os
import sys
import logging
import argparse
from pathlib import Path

# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def enroll_command(args):
    """Handle voice enrollment command"""
    try:
        from backend.scripts.common.voice_enrollment import VoiceEnrollment
        
        enrollment = VoiceEnrollment(voices_dir=args.voices_dir)
        
        # Collect audio sources
        audio_sources = []
        if args.audio:
            audio_sources.extend(args.audio)
        if args.url:
            audio_sources.extend(args.url)
        
        if not audio_sources:
            print("❌ No audio sources provided. Use --audio or --url")
            return 1
        
        print(f"🎤 Enrolling speaker: {args.name}")
        print(f"📁 Audio sources: {len(audio_sources)}")
        
        profile = enrollment.enroll_speaker(
            name=args.name,
            audio_sources=audio_sources,
            overwrite=args.overwrite,
            min_duration=args.min_duration
        )
        
        if profile:
            print(f"✅ Successfully enrolled speaker: {args.name}")
            print(f"   📊 Embeddings: {profile.metadata['num_embeddings']}")
            print(f"   ⏱️  Duration: {profile.metadata['total_duration_seconds']:.1f}s")
            print(f"   🎯 Recommended threshold: {profile.metadata['recommended_threshold']:.3f}")
            return 0
        else:
            print(f"❌ Failed to enroll speaker: {args.name}")
            return 1
            
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("📦 Install required packages: pip install speechbrain librosa soundfile")
        return 1
    except Exception as e:
        print(f"❌ Enrollment failed: {e}")
        return 1

def list_voices_command(args):
    """Handle list voices command"""
    try:
        from backend.scripts.common.voice_enrollment import VoiceEnrollment
        
        enrollment = VoiceEnrollment(voices_dir=args.voices_dir)
        profiles = enrollment.list_profiles()
        
        if profiles:
            print("🎤 Enrolled speakers:")
            for profile_name in profiles:
                profile = enrollment.load_profile(profile_name.lower())
                if profile:
                    print(f"   • {profile_name}")
                    print(f"     Created: {profile.created_at[:10]}")  # Just date
                    print(f"     Embeddings: {profile.metadata['num_embeddings']}")
                    print(f"     Threshold: {profile.metadata['recommended_threshold']:.3f}")
        else:
            print("📭 No enrolled speakers found.")
            print(f"💡 Use 'asr.py enroll --name <name> --audio <files>' to enroll speakers")
        
        return 0
        
    except Exception as e:
        print(f"❌ Failed to list voices: {e}")
        return 1

def voice_info_command(args):
    """Handle voice info command"""
    try:
        from backend.scripts.common.voice_enrollment import VoiceEnrollment
        
        enrollment = VoiceEnrollment(voices_dir=args.voices_dir)
        profile = enrollment.load_profile(args.name)
        
        if profile:
            print(f"🎤 Speaker: {profile.name}")
            print(f"📅 Created: {profile.created_at}")
            print(f"📊 Embeddings: {profile.metadata['num_embeddings']}")
            print(f"⏱️  Total duration: {profile.metadata['total_duration_seconds']:.1f}s")
            print(f"🎯 Recommended threshold: {profile.metadata['recommended_threshold']:.3f}")
            print(f"🔧 Model: {profile.metadata['model']}")
            print(f"📁 Audio sources ({len(profile.audio_sources)}):")
            for i, source in enumerate(profile.audio_sources, 1):
                print(f"   {i}. {source}")
            return 0
        else:
            print(f"❌ Speaker '{args.name}' not found.")
            return 1
            
    except Exception as e:
        print(f"❌ Failed to get voice info: {e}")
        return 1

def transcribe_command(args):
    """Handle transcription command"""
    try:
        from backend.scripts.common.enhanced_asr import EnhancedASR, EnhancedASRConfig
        
        print(f"🎙️  Starting enhanced ASR transcription: {args.audio_file}")
        
        # Create config with CLI overrides
        config = EnhancedASRConfig()
        
        if args.chaffee_min_sim is not None:
            config.chaffee_min_sim = args.chaffee_min_sim
        if args.guest_min_sim is not None:
            config.guest_min_sim = args.guest_min_sim
        if args.attr_margin is not None:
            config.attr_margin = args.attr_margin
        if args.overlap_bonus is not None:
            config.overlap_bonus = args.overlap_bonus
        if args.assume_monologue:
            config.assume_monologue = True
        if args.no_word_alignment:
            config.align_words = False
        if args.unknown_label:
            config.unknown_label = args.unknown_label
        if args.voices_dir:
            config.voices_dir = args.voices_dir
        if args.whisper_model:
            config.whisper_model = args.whisper_model
        
        print(f"⚙️  Configuration:")
        print(f"   🎯 Chaffee threshold: {config.chaffee_min_sim:.3f}")
        print(f"   👥 Guest threshold: {config.guest_min_sim:.3f}")
        print(f"   📏 Attribution margin: {config.attr_margin:.3f}")
        print(f"   🔄 Assume monologue: {config.assume_monologue}")
        print(f"   📝 Word alignment: {config.align_words}")
        
        # Initialize ASR system
        asr = EnhancedASR(config)
        
        # Perform transcription
        result = asr.transcribe_with_speaker_id(args.audio_file)
        
        if not result:
            print("❌ Transcription failed")
            return 1
        
        # Handle output
        from backend.scripts.common.asr_output_formats import ASROutputFormatter
        formatter = ASROutputFormatter(unknown_label=config.unknown_label)
        
        if args.format == 'json':
            output = formatter.to_json(result, pretty=True)
        elif args.format == 'srt':
            output = formatter.to_srt(result, include_speaker_prefix=not args.no_speaker_prefix)
        elif args.format == 'vtt':
            output = formatter.to_vtt(result, 
                                   include_speaker_prefix=not args.no_speaker_prefix,
                                   include_cues=not args.no_cues)
        elif args.format == 'text':
            output = formatter.to_text_with_speakers(result, include_timestamps=args.timestamps)
        elif args.format == 'summary':
            output = formatter.generate_summary_report(result)
        else:
            print(f"❌ Unknown format: {args.format}")
            return 1
        
        # Save or print output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"✅ Results saved to: {args.output}")
        else:
            print("\n" + "="*50)
            print(output)
        
        # Always show summary
        if args.format != 'summary':
            print("\n" + "="*50)
            print(formatter.generate_summary_report(result))
        
        return 0
        
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("📦 Install required packages: pip install whisperx pyannote.audio speechbrain")
        return 1
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

def convert_command(args):
    """Handle format conversion command"""
    try:
        import json
        from backend.scripts.common.asr_output_formats import ASROutputFormatter
        
        # Load input file
        with open(args.input_file, 'r') as f:
            result_data = json.load(f)
        
        formatter = ASROutputFormatter(unknown_label=args.unknown_label)
        
        # Generate output
        if args.format == 'json':
            output = formatter.to_json(result_data, pretty=True)
        elif args.format == 'srt':
            output = formatter.to_srt(result_data, include_speaker_prefix=not args.no_speaker_prefix)
        elif args.format == 'vtt':
            output = formatter.to_vtt(result_data, 
                                   include_speaker_prefix=not args.no_speaker_prefix,
                                   include_cues=not args.no_cues)
        elif args.format == 'text':
            output = formatter.to_text_with_speakers(result_data, include_timestamps=args.timestamps)
        elif args.format == 'words':
            output = formatter.to_word_level_json(result_data)
        elif args.format == 'summary':
            output = formatter.generate_summary_report(result_data)
        else:
            print(f"❌ Unknown format: {args.format}")
            return 1
        
        # Write output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"✅ Output written to: {args.output}")
        else:
            print(output)
        
        return 0
        
    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        return 1

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Enhanced ASR System with Speaker Identification',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enroll Dr. Chaffee with audio files
  python asr_cli.py enroll --name Chaffee --audio audio1.wav audio2.wav
  
  # Enroll from YouTube videos
  python asr_cli.py enroll --name Chaffee --url "https://youtube.com/watch?v=..."
  
  # List enrolled speakers
  python asr_cli.py list-voices
  
  # Transcribe audio with speaker identification
  python asr_cli.py transcribe interview.wav --output results.json
  
  # Transcribe and generate SRT with speaker prefixes
  python asr_cli.py transcribe interview.wav --format srt --output subtitles.srt
  
  # Convert JSON results to different formats
  python asr_cli.py convert results.json --format vtt --output subtitles.vtt
        """
    )
    
    # Global options
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--voices-dir', default='voices', help='Directory for voice profiles')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Enroll command
    enroll_parser = subparsers.add_parser('enroll', help='Enroll a new speaker')
    enroll_parser.add_argument('--name', required=True, help='Speaker name (e.g., Chaffee)')
    enroll_parser.add_argument('--audio', nargs='+', help='Audio file paths')
    enroll_parser.add_argument('--url', nargs='+', help='YouTube URLs')
    enroll_parser.add_argument('--overwrite', action='store_true', help='Overwrite existing profile')
    enroll_parser.add_argument('--min-duration', type=float, default=30.0, help='Minimum audio duration (seconds)')
    
    # List voices command
    list_parser = subparsers.add_parser('list-voices', help='List enrolled speakers')
    
    # Voice info command
    info_parser = subparsers.add_parser('voice-info', help='Show speaker profile information')
    info_parser.add_argument('name', help='Speaker name')
    
    # Transcribe command
    transcribe_parser = subparsers.add_parser('transcribe', help='Transcribe audio with speaker identification')
    transcribe_parser.add_argument('audio_file', help='Path to audio file')
    transcribe_parser.add_argument('--output', '-o', help='Output file path')
    transcribe_parser.add_argument('--format', choices=['json', 'srt', 'vtt', 'text', 'summary'], 
                                 default='json', help='Output format')
    
    # Transcription options
    transcribe_parser.add_argument('--chaffee-min-sim', type=float, help='Minimum similarity for Chaffee')
    transcribe_parser.add_argument('--guest-min-sim', type=float, help='Minimum similarity for guests')
    transcribe_parser.add_argument('--attr-margin', type=float, help='Attribution margin threshold')
    transcribe_parser.add_argument('--overlap-bonus', type=float, help='Overlap threshold bonus')
    transcribe_parser.add_argument('--assume-monologue', action='store_true', help='Assume monologue (Chaffee only)')
    transcribe_parser.add_argument('--no-word-alignment', action='store_true', help='Disable word alignment')
    transcribe_parser.add_argument('--unknown-label', help='Label for unknown speakers')
    transcribe_parser.add_argument('--whisper-model', help='Whisper model to use')
    
    # Output options
    transcribe_parser.add_argument('--no-speaker-prefix', action='store_true', help='Disable speaker prefixes')
    transcribe_parser.add_argument('--no-cues', action='store_true', help='Disable VTT styling cues')
    transcribe_parser.add_argument('--timestamps', action='store_true', help='Include timestamps in text format')
    
    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert ASR results to different formats')
    convert_parser.add_argument('input_file', help='Input JSON file from transcription')
    convert_parser.add_argument('--format', choices=['json', 'srt', 'vtt', 'text', 'words', 'summary'], 
                               required=True, help='Output format')
    convert_parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    convert_parser.add_argument('--no-speaker-prefix', action='store_true', help='Disable speaker prefixes')
    convert_parser.add_argument('--no-cues', action='store_true', help='Disable VTT styling cues')
    convert_parser.add_argument('--timestamps', action='store_true', help='Include timestamps in text format')
    convert_parser.add_argument('--unknown-label', default='Unknown', help='Label for unknown speakers')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Route to appropriate command handler
    if args.command == 'enroll':
        return enroll_command(args)
    elif args.command == 'list-voices':
        return list_voices_command(args)
    elif args.command == 'voice-info':
        return voice_info_command(args)
    elif args.command == 'transcribe':
        return transcribe_command(args)
    elif args.command == 'convert':
        return convert_command(args)
    else:
        print(f"❌ Unknown command: {args.command}")
        return 1

if __name__ == '__main__':
    exit(main())
