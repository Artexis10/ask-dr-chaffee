#!/usr/bin/env python3
"""
Output format generators for Enhanced ASR results
Supports JSON, SRT, and VTT formats with speaker attribution
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import asdict
from datetime import timedelta

logger = logging.getLogger(__name__)

def format_timestamp_srt(seconds: float) -> str:
    """Format timestamp for SRT format (HH:MM:SS,mmm)"""
    td = timedelta(seconds=seconds)
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs = td.seconds % 60
    milliseconds = int(td.microseconds / 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def format_timestamp_vtt(seconds: float) -> str:
    """Format timestamp for VTT format (HH:MM:SS.mmm)"""
    td = timedelta(seconds=seconds)
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs = td.seconds % 60
    milliseconds = int(td.microseconds / 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"

class ASROutputFormatter:
    """Format Enhanced ASR results into various output formats"""
    
    def __init__(self, unknown_label: str = "Unknown"):
        self.unknown_label = unknown_label
    
    def to_json(self, result, include_metadata: bool = True, pretty: bool = True) -> str:
        """Export to JSON format with full metadata"""
        try:
            output_data = result.to_dict() if hasattr(result, 'to_dict') else result
            
            if not include_metadata and 'metadata' in output_data:
                del output_data['metadata']
            
            indent = 2 if pretty else None
            return json.dumps(output_data, indent=indent, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to format as JSON: {e}")
            return "{}"
    
    def to_srt(self, result, include_speaker_prefix: bool = True) -> str:
        """Export to SRT format with optional speaker prefixes"""
        try:
            srt_content = []
            
            # Use segments for SRT output
            segments = result.segments if hasattr(result, 'segments') else result.get('segments', [])
            
            for i, segment in enumerate(segments, 1):
                start_time = format_timestamp_srt(segment['start'])
                end_time = format_timestamp_srt(segment['end'])
                text = segment['text'].strip()
                
                # Add speaker prefix if available and not unknown
                if include_speaker_prefix and 'speaker' in segment:
                    speaker = segment['speaker']
                    if speaker and speaker != self.unknown_label:
                        text = f"{speaker}: {text}"
                
                # SRT format: index, timestamp, text, blank line
                srt_content.append(f"{i}")
                srt_content.append(f"{start_time} --> {end_time}")
                srt_content.append(text)
                srt_content.append("")  # Blank line
            
            return "\n".join(srt_content)
            
        except Exception as e:
            logger.error(f"Failed to format as SRT: {e}")
            return ""
    
    def to_vtt(self, result, include_speaker_prefix: bool = True, include_cues: bool = True) -> str:
        """Export to VTT format with optional speaker prefixes and cue styling"""
        try:
            vtt_content = ["WEBVTT", ""]
            
            # Add speaker styles if using cues
            if include_cues:
                vtt_content.extend([
                    "STYLE",
                    "::cue(.chaffee) { color: #2196F3; font-weight: bold; }",
                    "::cue(.guest) { color: #FF9800; }",
                    "::cue(.unknown) { color: #999; font-style: italic; }",
                    ""
                ])
            
            # Use segments for VTT output
            segments = result.segments if hasattr(result, 'segments') else result.get('segments', [])
            
            for segment in segments:
                start_time = format_timestamp_vtt(segment['start'])
                end_time = format_timestamp_vtt(segment['end'])
                text = segment['text'].strip()
                
                # Determine speaker class for styling
                speaker_class = ""
                speaker_prefix = ""
                
                if 'speaker' in segment and segment['speaker']:
                    speaker = segment['speaker']
                    
                    if speaker != self.unknown_label:
                        if include_speaker_prefix:
                            speaker_prefix = f"{speaker}: "
                        
                        if include_cues:
                            if speaker.lower() == 'chaffee':
                                speaker_class = " class=\"chaffee\""
                            else:
                                speaker_class = " class=\"guest\""
                    else:
                        if include_cues:
                            speaker_class = " class=\"unknown\""
                
                # VTT cue format
                cue_id = f"cue-{len(vtt_content)}"
                vtt_content.append(f"{cue_id}")
                vtt_content.append(f"{start_time} --> {end_time}{speaker_class}")
                vtt_content.append(f"{speaker_prefix}{text}")
                vtt_content.append("")  # Blank line
            
            return "\n".join(vtt_content)
            
        except Exception as e:
            logger.error(f"Failed to format as VTT: {e}")
            return "WEBVTT\n"
    
    def to_text_with_speakers(self, result, include_timestamps: bool = False) -> str:
        """Export to plain text with speaker labels"""
        try:
            text_lines = []
            
            segments = result.segments if hasattr(result, 'segments') else result.get('segments', [])
            
            current_speaker = None
            paragraph_lines = []
            
            for segment in segments:
                speaker = segment.get('speaker', self.unknown_label)
                text = segment['text'].strip()
                
                # Start new paragraph when speaker changes
                if speaker != current_speaker:
                    # Finish previous paragraph
                    if paragraph_lines:
                        text_lines.append(" ".join(paragraph_lines))
                        text_lines.append("")  # Blank line between speakers
                        paragraph_lines = []
                    
                    # Start new paragraph with speaker label
                    current_speaker = speaker
                    if speaker and speaker != self.unknown_label:
                        if include_timestamps:
                            timestamp = f"[{segment['start']:.1f}s]"
                            text_lines.append(f"{speaker} {timestamp}:")
                        else:
                            text_lines.append(f"{speaker}:")
                    else:
                        if include_timestamps:
                            timestamp = f"[{segment['start']:.1f}s]"
                            text_lines.append(f"{timestamp}")
                
                # Add text to current paragraph
                paragraph_lines.append(text)
            
            # Add final paragraph
            if paragraph_lines:
                text_lines.append(" ".join(paragraph_lines))
            
            return "\n".join(text_lines)
            
        except Exception as e:
            logger.error(f"Failed to format as text: {e}")
            return ""
    
    def to_word_level_json(self, result) -> str:
        """Export word-level timing with speaker attribution"""
        try:
            words_data = []
            
            words = result.words if hasattr(result, 'words') else result.get('words', [])
            
            for word in words:
                word_data = {
                    'word': word.word if hasattr(word, 'word') else word.get('word', ''),
                    'start': word.start if hasattr(word, 'start') else word.get('start', 0),
                    'end': word.end if hasattr(word, 'end') else word.get('end', 0),
                    'confidence': word.confidence if hasattr(word, 'confidence') else word.get('confidence', 0),
                }
                
                # Add speaker info if available
                if hasattr(word, 'speaker') or 'speaker' in word:
                    speaker = word.speaker if hasattr(word, 'speaker') else word.get('speaker')
                    if speaker:
                        word_data['speaker'] = speaker
                        word_data['speaker_confidence'] = (
                            word.speaker_confidence if hasattr(word, 'speaker_confidence') 
                            else word.get('speaker_confidence', 0)
                        )
                        word_data['speaker_margin'] = (
                            word.speaker_margin if hasattr(word, 'speaker_margin')
                            else word.get('speaker_margin', 0)
                        )
                        word_data['is_overlap'] = (
                            word.is_overlap if hasattr(word, 'is_overlap')
                            else word.get('is_overlap', False)
                        )
                
                words_data.append(word_data)
            
            return json.dumps(words_data, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to format word-level JSON: {e}")
            return "[]"
    
    def generate_summary_report(self, result) -> str:
        """Generate a human-readable summary report"""
        try:
            lines = []
            lines.append("=== ASR TRANSCRIPTION SUMMARY ===")
            lines.append("")
            
            # Basic info
            metadata = result.metadata if hasattr(result, 'metadata') else result.get('metadata', {})
            
            if 'duration' in metadata:
                lines.append(f"Audio Duration: {metadata['duration']:.1f} seconds")
            
            if 'method' in metadata:
                lines.append(f"Processing Method: {metadata['method']}")
            
            if 'whisper_model' in metadata:
                lines.append(f"Whisper Model: {metadata['whisper_model']}")
            
            lines.append("")
            
            # Speaker statistics
            if 'summary' in metadata:
                summary = metadata['summary']
                
                lines.append("=== SPEAKER BREAKDOWN ===")
                
                if 'speaker_time_percentages' in summary:
                    for speaker, percentage in summary['speaker_time_percentages'].items():
                        lines.append(f"{speaker}: {percentage:.1f}% of audio")
                
                lines.append("")
                
                # Confidence statistics
                if 'confidence_stats' in summary:
                    lines.append("=== CONFIDENCE STATISTICS ===")
                    for speaker, stats in summary['confidence_stats'].items():
                        lines.append(f"{speaker}: avg={stats['avg']:.3f}, min={stats['min']:.3f}, max={stats['max']:.3f}")
                    lines.append("")
                
                # Warnings
                if 'unknown_segments' in summary and summary['unknown_segments'] > 0:
                    lines.append(f"⚠️  Warning: {summary['unknown_segments']} segments could not be attributed to known speakers")
                    lines.append("")
                
                # Chaffee-specific stats
                if 'chaffee_percentage' in summary:
                    chaffee_pct = summary['chaffee_percentage']
                    if chaffee_pct > 90:
                        lines.append(f"✓ High confidence: {chaffee_pct:.1f}% attributed to Dr. Chaffee")
                    elif chaffee_pct > 50:
                        lines.append(f"✓ Moderate confidence: {chaffee_pct:.1f}% attributed to Dr. Chaffee")
                    else:
                        lines.append(f"⚠️  Low Chaffee attribution: only {chaffee_pct:.1f}% of audio")
                    lines.append("")
            
            # Processing flags
            if metadata.get('monologue_fast_path'):
                lines.append("✓ Used monologue fast-path (high Chaffee confidence)")
            elif metadata.get('diarization_failed'):
                lines.append("⚠️  Speaker diarization failed")
            
            if metadata.get('word_alignment'):
                lines.append("✓ Word-level speaker alignment enabled")
            
            lines.append("")
            lines.append("=== END SUMMARY ===")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Failed to generate summary report: {e}")
            return "Summary generation failed"

def main():
    """CLI for testing output formats"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='ASR Output Format Converter')
    parser.add_argument('input_file', help='Input JSON file from Enhanced ASR')
    parser.add_argument('--format', choices=['json', 'srt', 'vtt', 'text', 'words', 'summary'], 
                       default='srt', help='Output format')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--no-speaker-prefix', action='store_true', help='Disable speaker prefixes')
    parser.add_argument('--no-cues', action='store_true', help='Disable VTT styling cues')
    parser.add_argument('--timestamps', action='store_true', help='Include timestamps in text format')
    parser.add_argument('--unknown-label', default='Unknown', help='Label for unknown speakers')
    
    args = parser.parse_args()
    
    try:
        # Load input file
        with open(args.input_file, 'r') as f:
            result_data = json.load(f)
        
        # Initialize formatter
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
            print(f"Unknown format: {args.format}")
            return 1
        
        # Write output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"Output written to: {args.output}")
        else:
            print(output)
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == '__main__':
    exit(main())
