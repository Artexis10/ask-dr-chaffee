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

# Add parent directory to path for proper imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        
        enrollment = VoiceEnrollment(voices_dir=args.voices_dir)
        
        # Collect audio sources
        audio_sources = []
        if args.audio:
            audio_sources.extend(args.audio)
        if args.url:
            audio_sources.extend(args.url)
        
        if not audio_sources:
            print("[ERROR] No audio sources provided. Use --audio or --url")
            return 1
        
        print(f"[SPEAKER] Enrolling speaker: {args.name}")
        print(f"[FILES] Audio sources: {len(audio_sources)}")
        
        profile_metadata = enrollment.enroll_speaker(
            name=args.name,
            audio_sources=audio_sources,
            overwrite=args.overwrite,
            update=args.update,
            min_duration=args.min_duration
        )
        
        if profile_metadata:
            print(f"[SUCCESS] Successfully enrolled speaker: {args.name}")
            print(f"   [STATS] Embeddings: {profile_metadata['num_embeddings']}")
            print(f"   [TIME]  Duration: {profile_metadata['total_duration_seconds']:.1f}s")
            print(f"   [TARGET] Recommended threshold: {profile_metadata['recommended_threshold']:.3f}")
            return 0
        else:
            print(f"[ERROR] Failed to enroll speaker: {args.name}")
            return 1
            
    except ImportError as e:
        print(f"[ERROR] Missing dependencies: {e}")
        print("[PACKAGE] Install required packages: pip install speechbrain librosa soundfile")
        return 1
    except Exception as e:
        print(f"[ERROR] Enrollment failed: {e}")
        return 1

def list_voices_command(args):
    """Handle list voices command"""
    try:
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        
        enrollment = VoiceEnrollment(voices_dir=args.voices_dir)
        profiles = enrollment.list_profiles()
        
        if profiles:
            print("[SPEAKER] Enrolled speakers:")
            for profile_name in profiles:
                profile = enrollment.load_profile(profile_name.lower())
                if profile:
                    print(f"   • {profile_name}")
                    print(f"     Created: {profile.created_at[:10]}")  # Just date
                    print(f"     Embeddings: {profile.metadata['num_embeddings']}")
                    print(f"     Threshold: {profile.metadata['recommended_threshold']:.3f}")
        else:
            print("[EMPTY] No enrolled speakers found.")
            print(f"[TIP] Use 'asr.py enroll --name <name> --audio <files>' to enroll speakers")
        
        return 0
        
    except Exception as e:
        print(f"[ERROR] Failed to list voices: {e}")
        return 1

def voice_info_command(args):
    """Handle voice info command"""
    try:
        from backend.scripts.common.voice_enrollment_optimized import VoiceEnrollment
        
        enrollment = VoiceEnrollment(voices_dir=args.voices_dir)
        profile_info = enrollment.get_profile_info(args.name)
        
        if profile_info:
            print(f"[SPEAKER] Speaker: {profile_info['name']}")
            print(f"[DATE] Created: {profile_info.get('created_at', 'Unknown')}")
            print(f"[STATS] Embeddings: {profile_info['embedding_count']}")
            
            # Load the full profile to get more details
            try:
                profile_path = os.path.join(args.voices_dir, f"{args.name.lower()}.json")
                if os.path.exists(profile_path):
                    with open(profile_path, 'r') as f:
                        import json
                        profile_data = json.load(f)
                        
                        # Get metadata safely
                        metadata = profile_data.get('metadata', {})
                        total_duration = metadata.get('total_duration_seconds', 0)
                        recommended_threshold = metadata.get('recommended_threshold', 0.7)
                        model = metadata.get('model', 'Unknown')
                        audio_sources = profile_data.get('audio_sources', [])
                        
                        print(f"[TIME]  Total duration: {total_duration:.1f}s")
                        print(f"[TARGET] Recommended threshold: {recommended_threshold:.3f}")
                        print(f"[TOOL] Model: {model}")
                        print(f"[FILES] Audio sources ({len(audio_sources)}):")            
                        for i, source in enumerate(audio_sources, 1):
                            print(f"   {i}. {source}")
            except Exception as e:
                print(f"[WARNING] Could not load detailed profile info: {e}")
            
            return 0
        else:
            print(f"[ERROR] Speaker '{args.name}' not found.")
            return 1
            
    except Exception as e:
        print(f"[ERROR] Failed to get voice info: {e}")
        return 1

def transcribe_command(args):
    """Handle transcription command"""
    try:
        from backend.scripts.common.enhanced_asr import EnhancedASR
        from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig
        
        print(f"[MIC]  Starting enhanced ASR transcription: {args.audio_file}")
        
        # Create config with CLI overrides using new system
        overrides = {}
        
        # New Whisper configuration options
        if hasattr(args, 'model') and args.model:
            overrides['model'] = args.model
        elif args.whisper_model:  # Legacy compatibility
            overrides['model'] = args.whisper_model
        
        if hasattr(args, 'device') and args.device:
            overrides['device'] = args.device
        if hasattr(args, 'compute_type') and args.compute_type:
            overrides['compute_type'] = args.compute_type
        if hasattr(args, 'beam_size') and args.beam_size:
            overrides['beam_size'] = args.beam_size
        if hasattr(args, 'chunk_length') and args.chunk_length:
            overrides['chunk_length'] = args.chunk_length
        if hasattr(args, 'disable_vad') and args.disable_vad:
            overrides['vad_filter'] = False
        if hasattr(args, 'language') and args.language:
            overrides['language'] = args.language
        if hasattr(args, 'task') and args.task:
            overrides['task'] = args.task
        if hasattr(args, 'domain_prompt') and args.domain_prompt:
            overrides['initial_prompt'] = args.domain_prompt
        if hasattr(args, 'disable_two_pass') and args.disable_two_pass:
            overrides['enable_two_pass'] = False
        if hasattr(args, 'disable_alignment') and args.disable_alignment:
            overrides['enable_alignment'] = False
        
        # Legacy speaker ID options (maintain backward compatibility)
        if args.chaffee_min_sim is not None:
            overrides['chaffee_min_sim'] = args.chaffee_min_sim
        if args.guest_min_sim is not None:
            overrides['guest_min_sim'] = args.guest_min_sim
        if args.attr_margin is not None:
            overrides['attr_margin'] = args.attr_margin
        if args.overlap_bonus is not None:
            overrides['overlap_bonus'] = args.overlap_bonus
        if args.assume_monologue:
            overrides['assume_monologue'] = True
        if args.no_word_alignment:
            overrides['align_words'] = False
        if args.unknown_label:
            overrides['unknown_label'] = args.unknown_label
        if args.voices_dir:
            overrides['voices_dir'] = args.voices_dir
        
        config = EnhancedASRConfig(**overrides)
        
        print(f"[CONFIG]  Enhanced ASR Configuration:")
        print(f"   [MODEL]  Whisper model: {config.whisper.model}")
        print(f"   [DEVICE] Device: {config.whisper.device}")
        print(f"   [COMPUTE] Compute type: {config.whisper.compute_type}")
        print(f"   [BEAM]   Beam size: {config.whisper.beam_size}")
        print(f"   [QA]     Two-pass QA: {config.quality.enable_two_pass}")
        print(f"   [TARGET] Chaffee threshold: {config.chaffee_min_sim:.3f}")
        print(f"   [GUESTS] Guest threshold: {config.guest_min_sim:.3f}")
        print(f"   [MARGIN] Attribution margin: {config.attr_margin:.3f}")
        print(f"   [SYNC]   Assume monologue: {config.assume_monologue}")
        print(f"   [ALIGN]  Word alignment: {config.align_words}")
        
        # Initialize ASR system
        asr = EnhancedASR(config)
        
        # Perform transcription using new run method
        result = asr.run(args.audio_file)
        
        if not result:
            print("[ERROR] Transcription failed")
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
            print(f"[ERROR] Unknown format: {args.format}")
            return 1
        
        # Save or print output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"[SUCCESS] Results saved to: {args.output}")
        else:
            print("\n" + "="*50)
            print(output)
        
        # Always show summary
        if args.format != 'summary':
            print("\n" + "="*50)
            print(formatter.generate_summary_report(result))
        
        return 0
        
    except ImportError as e:
        print(f"[ERROR] Missing dependencies: {e}")
        print("[PACKAGE] Install required packages: pip install whisperx pyannote.audio speechbrain")
        return 1
    except Exception as e:
        print(f"[ERROR] Transcription failed: {e}")
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
            print(f"[ERROR] Unknown format: {args.format}")
            return 1
        
        # Write output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"[SUCCESS] Output written to: {args.output}")
        else:
            print(output)
        
        return 0
        
    except Exception as e:
        print(f"[ERROR] Conversion failed: {e}")
        return 1

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Enhanced ASR System with Large-v3 Whisper and Speaker Identification',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enroll Dr. Chaffee with audio files
  python asr_cli.py enroll --name Chaffee --audio audio1.wav audio2.wav
  
  # Enroll from YouTube videos
  python asr_cli.py enroll --name Chaffee --url "https://youtube.com/watch?v=..."
  
  # List enrolled speakers
  python asr_cli.py list-voices
  
  # Enhanced transcription with large-v3 model (default)
  python asr_cli.py transcribe interview.wav --output results.json
  
  # High-quality transcription with custom settings
  python asr_cli.py transcribe lecture.wav --model large-v3 --beam-size 8 --chunk-length 45
  
  # Fast transcription for real-time processing
  python asr_cli.py transcribe stream.wav --model small.en --compute-type int8 --disable-two-pass
  
  # Generate SRT with speaker prefixes
  python asr_cli.py transcribe interview.wav --format srt --output subtitles.srt
  
  # Custom domain prompt for better medical terminology
  python asr_cli.py transcribe medical.wav --domain-prompt "ketogenesis statins cholesterol LDL"
  
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
    enroll_parser.add_argument('--update', action='store_true', help='Update existing profile with new audio')
    enroll_parser.add_argument('--min-duration', type=float, default=30.0, help='Minimum audio duration (seconds)')
    
    # List voices command
    list_parser = subparsers.add_parser('list-voices', help='List enrolled speakers')
    
    # Voice info command
    info_parser = subparsers.add_parser('voice-info', help='Show speaker profile information')
    info_parser.add_argument('name', help='Speaker name')
    
    # Transcribe command with enhanced options
    transcribe_parser = subparsers.add_parser('transcribe', help='Transcribe audio with enhanced ASR and speaker identification')
    transcribe_parser.add_argument('audio_file', help='Path to audio file')
    transcribe_parser.add_argument('--output', '-o', help='Output file path')
    transcribe_parser.add_argument('--format', choices=['json', 'srt', 'vtt', 'text', 'summary'], 
                                 default='json', help='Output format')
    
    # New enhanced ASR options
    transcribe_parser.add_argument('--model', help='Whisper model (large-v3, large-v3-turbo, distil-large-v3, etc.)')
    transcribe_parser.add_argument('--device', choices=['cuda', 'cpu'], help='Processing device')
    transcribe_parser.add_argument('--compute-type', choices=['float16', 'int8_float16', 'int8'], 
                                 help='Compute precision for GPU processing')
    transcribe_parser.add_argument('--beam-size', type=int, help='Beam search size (default: 6 for quality)')
    transcribe_parser.add_argument('--chunk-length', type=int, help='Audio chunk length in seconds (default: 45)')
    transcribe_parser.add_argument('--disable-vad', action='store_true', help='Disable voice activity detection')
    transcribe_parser.add_argument('--language', default='en', help='Audio language (default: en)')
    transcribe_parser.add_argument('--task', choices=['transcribe', 'translate'], default='transcribe', 
                                 help='Whisper task (default: transcribe)')
    transcribe_parser.add_argument('--domain-prompt', help='Domain-specific prompt for better accuracy')
    transcribe_parser.add_argument('--disable-two-pass', action='store_true', 
                                 help='Disable two-pass quality assurance for low-confidence segments')
    transcribe_parser.add_argument('--disable-alignment', action='store_true', 
                                 help='Disable word-level alignment (faster but less precise timing)')
    
    # Legacy speaker identification options (backward compatibility)
    transcribe_parser.add_argument('--chaffee-min-sim', type=float, help='Minimum similarity for Chaffee attribution')
    transcribe_parser.add_argument('--guest-min-sim', type=float, help='Minimum similarity for guest attribution')
    transcribe_parser.add_argument('--attr-margin', type=float, help='Attribution margin threshold')
    transcribe_parser.add_argument('--overlap-bonus', type=float, help='Overlap threshold bonus')
    transcribe_parser.add_argument('--assume-monologue', action='store_true', help='Assume monologue (Chaffee only) for faster processing')
    transcribe_parser.add_argument('--no-word-alignment', action='store_true', help='Disable word alignment (legacy, use --disable-alignment instead)')
    transcribe_parser.add_argument('--unknown-label', help='Label for unknown speakers')
    transcribe_parser.add_argument('--whisper-model', help='Whisper model to use (legacy, use --model instead)')
    
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
        print(f"[ERROR] Unknown command: {args.command}")
        return 1

if __name__ == '__main__':
    exit(main())
