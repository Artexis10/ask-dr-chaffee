#!/usr/bin/env python3
"""
Enhanced transcript fetching with speaker identification
Extends the existing TranscriptFetcher with Enhanced ASR capabilities
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Import existing transcript fetcher
from .transcript_fetch import TranscriptFetcher as BaseTranscriptFetcher
from .transcript_common import TranscriptSegment

class EnhancedTranscriptFetcher(BaseTranscriptFetcher):
    """
    Enhanced transcript fetcher with speaker identification capabilities
    Extends the existing TranscriptFetcher with Enhanced ASR integration
    """
    
    def __init__(self, 
                 yt_dlp_path: str = "yt-dlp", 
                 whisper_model: str = None, 
                 whisper_upgrade: str = None, 
                 ffmpeg_path: str = None, 
                 proxies: dict = None, 
                 api_key: str = None, 
                 credentials_path: str = None,
                 enable_preprocessing: bool = True,
                 # Enhanced ASR options
                 enable_speaker_id: bool = False,
                 voices_dir: str = None,
                 chaffee_min_sim: float = None,
                 guest_min_sim: float = None,
                 assume_monologue: bool = None):
        
        # Initialize base class
        super().__init__(
            yt_dlp_path=yt_dlp_path,
            whisper_model=whisper_model,
            whisper_upgrade=whisper_upgrade,
            ffmpeg_path=ffmpeg_path,
            proxies=proxies,
            api_key=api_key,
            credentials_path=credentials_path,
            enable_preprocessing=enable_preprocessing
        )
        
        # Enhanced ASR configuration
        self.enable_speaker_id = enable_speaker_id or os.getenv('ENABLE_SPEAKER_ID', 'false').lower() == 'true'
        self.voices_dir = voices_dir or os.getenv('VOICES_DIR', 'voices')
        
        # Speaker ID thresholds
        self.chaffee_min_sim = chaffee_min_sim or float(os.getenv('CHAFFEE_MIN_SIM', '0.82'))
        self.guest_min_sim = guest_min_sim or float(os.getenv('GUEST_MIN_SIM', '0.82'))
        self.assume_monologue = assume_monologue if assume_monologue is not None else os.getenv('ASSUME_MONOLOGUE', 'true').lower() == 'true'
        
        # Lazy-loaded Enhanced ASR components
        self._enhanced_asr = None
        self._voice_enrollment = None
        
        logger.info(f"Enhanced Transcript Fetcher initialized (speaker_id={self.enable_speaker_id})")
    
    def _get_enhanced_asr(self):
        """Lazy load Enhanced ASR system"""
        if self._enhanced_asr is None and self.enable_speaker_id:
            try:
                from .enhanced_asr import EnhancedASR, EnhancedASRConfig
                
                # Create config with current settings
                config = EnhancedASRConfig()
                config.chaffee_min_sim = self.chaffee_min_sim
                config.guest_min_sim = self.guest_min_sim
                config.assume_monologue = self.assume_monologue
                config.whisper_model = self.whisper_model
                config.voices_dir = self.voices_dir
                
                self._enhanced_asr = EnhancedASR(config)
                logger.info("Enhanced ASR system loaded")
                
            except ImportError as e:
                logger.warning(f"Enhanced ASR not available: {e}")
                logger.info("Install dependencies: pip install whisperx pyannote.audio speechbrain")
                self.enable_speaker_id = False
        
        return self._enhanced_asr
    
    def _get_voice_enrollment(self):
        """Lazy load voice enrollment system"""
        if self._voice_enrollment is None:
            try:
                from .voice_enrollment import VoiceEnrollment
                self._voice_enrollment = VoiceEnrollment(voices_dir=self.voices_dir)
            except ImportError as e:
                logger.warning(f"Voice enrollment not available: {e}")
        
        return self._voice_enrollment
    
    def _check_speaker_profiles_available(self) -> bool:
        """Check if any speaker profiles are available"""
        try:
            enrollment = self._get_voice_enrollment()
            if enrollment:
                profiles = enrollment.list_profiles()
                return len(profiles) > 0
        except Exception as e:
            logger.warning(f"Failed to check speaker profiles: {e}")
        
        return False
    
    def _convert_enhanced_result_to_segments(self, enhanced_result) -> Tuple[List[TranscriptSegment], Dict[str, Any]]:
        """Convert Enhanced ASR result to TranscriptSegment format"""
        try:
            segments = []
            metadata = enhanced_result.metadata.copy()
            
            # Convert segments with speaker information
            for segment_data in enhanced_result.segments:
                # Create TranscriptSegment with speaker info embedded in text
                text = segment_data['text'].strip()
                
                # Add speaker prefix if available and not unknown
                if ('speaker' in segment_data and 
                    segment_data['speaker'] and 
                    segment_data['speaker'] != enhanced_result.metadata.get('unknown_label', 'Unknown')):
                    
                    speaker = segment_data['speaker']
                    confidence = segment_data.get('speaker_confidence', 0.0)
                    
                    # For database storage, we can embed speaker info in metadata
                    # but keep text clean for readability
                    segment = TranscriptSegment(
                        start=segment_data['start'],
                        end=segment_data['end'],
                        text=text
                    )
                    
                    # Add speaker metadata to the segment object if supported
                    if hasattr(segment, 'metadata'):
                        segment.metadata = {
                            'speaker': speaker,
                            'speaker_confidence': confidence,
                            'has_speaker_id': True
                        }
                    
                else:
                    segment = TranscriptSegment(
                        start=segment_data['start'],
                        end=segment_data['end'], 
                        text=text
                    )
                
                segments.append(segment)
            
            # Add enhanced ASR metadata
            metadata.update({
                'enhanced_asr_used': True,
                'speaker_identification': True,
                'processing_method': enhanced_result.metadata.get('method', 'enhanced_asr')
            })
            
            # Include summary if available
            if 'summary' in enhanced_result.metadata:
                summary = enhanced_result.metadata['summary']
                metadata.update({
                    'chaffee_percentage': summary.get('chaffee_percentage', 0.0),
                    'speaker_distribution': summary.get('speaker_time_percentages', {}),
                    'unknown_segments': summary.get('unknown_segments', 0)
                })
            
            logger.info(f"Converted Enhanced ASR result: {len(segments)} segments with speaker ID")
            return segments, metadata
            
        except Exception as e:
            logger.error(f"Failed to convert Enhanced ASR result: {e}")
            # Fallback to basic segments without speaker info
            segments = []
            for segment_data in enhanced_result.segments:
                segment = TranscriptSegment(
                    start=segment_data['start'],
                    end=segment_data['end'],
                    text=segment_data['text'].strip()
                )
                segments.append(segment)
            
            return segments, {'enhanced_asr_used': True, 'conversion_error': str(e)}
    
    def fetch_transcript_with_speaker_id(
        self, 
        video_id: str, 
        max_duration_s: Optional[int] = None,
        force_enhanced_asr: bool = False,
        cleanup_audio: bool = True,
        enable_silence_removal: bool = False
    ) -> Tuple[Optional[List[TranscriptSegment]], str, Dict[str, Any]]:
        """
        Fetch transcript with optional speaker identification
        
        Args:
            video_id: YouTube video ID or local audio file path
            max_duration_s: Maximum duration for processing
            force_enhanced_asr: Skip YouTube transcripts and use Enhanced ASR
            cleanup_audio: Clean up temporary audio files
            enable_silence_removal: Enable audio preprocessing
            
        Returns:
            (segments, method, metadata) where method indicates processing used
        """
        metadata = {"video_id": video_id, "preprocessing_flags": {}}
        
        # Check if Enhanced ASR is available and should be used
        use_enhanced_asr = (
            self.enable_speaker_id and 
            (force_enhanced_asr or self._check_speaker_profiles_available())
        )
        
        if use_enhanced_asr:
            enhanced_asr = self._get_enhanced_asr()
            if not enhanced_asr:
                logger.warning("Enhanced ASR requested but not available, falling back to standard method")
                use_enhanced_asr = False
        
        # Try YouTube transcript first (unless forced to use Enhanced ASR)
        if not force_enhanced_asr and not use_enhanced_asr:
            youtube_segments = self.fetch_youtube_transcript(video_id)
            if youtube_segments:
                metadata.update({"source": "youtube", "segment_count": len(youtube_segments)})
                return youtube_segments, 'youtube', metadata
        
        # If we have speaker profiles and Enhanced ASR available, use it
        if use_enhanced_asr and self._check_speaker_profiles_available():
            logger.info(f"Using Enhanced ASR with speaker identification for {video_id}")
            
            try:
                # Download audio if video_id looks like a YouTube ID
                if len(video_id) == 11 and video_id.isalnum():
                    # YouTube video ID - need to download audio first
                    audio_path = self._download_audio_for_enhanced_asr(video_id)
                    if not audio_path:
                        logger.error("Failed to download audio for Enhanced ASR")
                        return self._fallback_to_standard_whisper(video_id, metadata)
                else:
                    # Assume it's a local file path
                    audio_path = video_id
                    if not os.path.exists(audio_path):
                        logger.error(f"Audio file not found: {audio_path}")
                        return None, 'failed', metadata
                
                # Process with Enhanced ASR
                enhanced_asr = self._get_enhanced_asr()
                result = enhanced_asr.transcribe_with_speaker_id(audio_path)
                
                if result:
                    segments, enhanced_metadata = self._convert_enhanced_result_to_segments(result)
                    metadata.update(enhanced_metadata)
                    
                    # Cleanup if we downloaded the audio
                    if cleanup_audio and len(video_id) == 11:
                        try:
                            os.unlink(audio_path)
                        except:
                            pass
                    
                    method = 'enhanced_asr'
                    if result.metadata.get('monologue_fast_path'):
                        method = 'enhanced_asr_monologue'
                    
                    logger.info(f"Enhanced ASR completed: {len(segments)} segments with speaker ID")
                    return segments, method, metadata
                else:
                    logger.warning("Enhanced ASR failed, falling back to standard Whisper")
                    return self._fallback_to_standard_whisper(video_id, metadata)
                    
            except Exception as e:
                logger.error(f"Enhanced ASR processing failed: {e}")
                return self._fallback_to_standard_whisper(video_id, metadata)
        
        # Fallback to standard transcript fetching
        logger.info("Using standard transcript fetching (no speaker ID)")
        return super().fetch_transcript(
            video_id, 
            max_duration_s=max_duration_s,
            force_whisper=force_enhanced_asr,
            cleanup_audio=cleanup_audio,
            enable_silence_removal=enable_silence_removal
        )
    
    def _download_audio_for_enhanced_asr(self, video_id: str) -> Optional[str]:
        """Download audio file for Enhanced ASR processing"""
        try:
            import tempfile
            import subprocess
            
            # Create temporary directory for download
            temp_dir = tempfile.mkdtemp()
            output_template = os.path.join(temp_dir, f'{video_id}.%(ext)s')
            
            # Use yt-dlp to download audio - use webm format and let yt-dlp handle conversion
            cmd = [
                self.yt_dlp_path,
                '--format', 'bestaudio',
                '--no-playlist',
                '--ignore-errors',
                '-o', output_template,
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            
            if self.ffmpeg_path:
                cmd.extend(['--ffmpeg-location', self.ffmpeg_path])
            
            if self.proxies:
                if isinstance(self.proxies, dict) and 'http' in self.proxies:
                    cmd.extend(['--proxy', self.proxies['http']])
                elif isinstance(self.proxies, str):
                    cmd.extend(['--proxy', self.proxies])
            
            logger.info(f"Running yt-dlp command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            logger.info(f"yt-dlp stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"yt-dlp stderr: {result.stderr}")
            
            if result.returncode == 0:
                # Find the actual output file (various audio formats)
                for ext in ['.webm', '.mp4', '.m4a', '.mp3', '.wav', '.opus']:
                    potential_path = os.path.join(temp_dir, f"{video_id}{ext}")
                    if os.path.exists(potential_path):
                        logger.info(f"Audio downloaded successfully: {potential_path}")
                        return potential_path
                
                # List all files in temp directory for debugging
                files_in_dir = os.listdir(temp_dir)
                logger.error(f"Audio download succeeded but file not found. Files in {temp_dir}: {files_in_dir}")
                
                # Clean up temp directory
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None
            else:
                logger.error(f"Audio download failed: {result.stderr}")
                # Clean up temp directory
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None
                
        except Exception as e:
            logger.error(f"Failed to download audio for Enhanced ASR: {e}")
            # Clean up temp directory if it exists
            if 'temp_dir' in locals():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            return None
    
    def _fallback_to_standard_whisper(self, video_id: str, metadata: Dict[str, Any]) -> Tuple[Optional[List[TranscriptSegment]], str, Dict[str, Any]]:
        """Fallback to standard Whisper processing"""
        logger.info("Falling back to standard Whisper transcription")
        
        try:
            segments, method, whisper_metadata = super().fetch_transcript(
                video_id, 
                force_whisper=True,
                cleanup_audio=True
            )
            
            # Merge metadata
            metadata.update(whisper_metadata)
            metadata['enhanced_asr_fallback'] = True
            
            return segments, "whisper", metadata
            
        except Exception as e:
            logger.error(f"Standard Whisper fallback also failed: {e}")
            metadata['error'] = str(e)
            return None, 'failed', metadata
    
    def enroll_speaker_from_video(
        self, 
        video_id: str, 
        speaker_name: str, 
        overwrite: bool = False,
        min_duration: float = 30.0
    ) -> bool:
        """
        Enroll a speaker using audio from a YouTube video
        
        Args:
            video_id: YouTube video ID
            speaker_name: Name for the speaker profile
            overwrite: Whether to overwrite existing profile
            min_duration: Minimum audio duration required
            
        Returns:
            True if enrollment successful, False otherwise
        """
        try:
            enrollment = self._get_voice_enrollment()
            if not enrollment:
                logger.error("Voice enrollment system not available")
                return False
            
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            
            profile = enrollment.enroll_speaker(
                name=speaker_name,
                audio_sources=[youtube_url],
                overwrite=overwrite,
                min_duration=min_duration
            )
            
            return profile is not None
            
        except Exception as e:
            logger.error(f"Failed to enroll speaker from video {video_id}: {e}")
            return False
    
    def get_speaker_profiles(self) -> List[str]:
        """Get list of available speaker profiles"""
        try:
            enrollment = self._get_voice_enrollment()
            if enrollment:
                return enrollment.list_profiles()
        except Exception as e:
            logger.warning(f"Failed to get speaker profiles: {e}")
        
        return []
    
    def get_enhanced_asr_status(self) -> Dict[str, Any]:
        """Get status of Enhanced ASR system"""
        status = {
            'enabled': self.enable_speaker_id,
            'available': False,
            'voice_profiles': [],
            'config': {
                'chaffee_min_sim': self.chaffee_min_sim,
                'guest_min_sim': self.guest_min_sim,
                'assume_monologue': self.assume_monologue,
                'voices_dir': self.voices_dir
            }
        }
        
        if self.enable_speaker_id:
            try:
                enhanced_asr = self._get_enhanced_asr()
                status['available'] = enhanced_asr is not None
                status['voice_profiles'] = self.get_speaker_profiles()
            except Exception as e:
                status['error'] = str(e)
        
        return status

def main():
    """CLI for testing enhanced transcript fetching"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced transcript fetching with speaker ID')
    parser.add_argument('video_id', help='YouTube video ID or audio file path')
    parser.add_argument('--enable-speaker-id', action='store_true', help='Enable speaker identification')
    parser.add_argument('--force-enhanced-asr', action='store_true', help='Force Enhanced ASR usage')
    parser.add_argument('--voices-dir', default='voices', help='Voice profiles directory')
    parser.add_argument('--output', help='Output file for results')
    parser.add_argument('--format', choices=['segments', 'json', 'summary'], default='segments')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format='%(levelname)s: %(message)s')
    
    # Initialize enhanced fetcher
    fetcher = EnhancedTranscriptFetcher(
        enable_speaker_id=args.enable_speaker_id,
        voices_dir=args.voices_dir
    )
    
    # Show status
    if args.verbose:
        status = fetcher.get_enhanced_asr_status()
        print(f"Enhanced ASR Status: {status}")
    
    # Fetch transcript
    segments, method, metadata = fetcher.fetch_transcript_with_speaker_id(
        args.video_id,
        force_enhanced_asr=args.force_enhanced_asr
    )
    
    if segments:
        print(f"\nTranscript fetched using {method} ({len(segments)} segments)")
        
        if args.format == 'segments':
            for i, segment in enumerate(segments[:5]):
                speaker_info = ""
                if hasattr(segment, 'metadata') and segment.metadata:
                    if 'speaker' in segment.metadata:
                        speaker = segment.metadata['speaker']
                        conf = segment.metadata.get('speaker_confidence', 0.0)
                        speaker_info = f" [{speaker}: {conf:.2f}]"
                
                print(f"  {segment.start:.1f}s - {segment.end:.1f}s: {segment.text}{speaker_info}")
            
            if len(segments) > 5:
                print(f"  ... and {len(segments) - 5} more segments")
        
        elif args.format == 'json':
            import json
            output_data = {
                'method': method,
                'segments': [{'start': s.start, 'end': s.end, 'text': s.text} for s in segments],
                'metadata': metadata
            }
            print(json.dumps(output_data, indent=2))
        
        elif args.format == 'summary':
            print(f"\nProcessing Summary:")
            print(f"Method: {method}")
            print(f"Segments: {len(segments)}")
            if 'chaffee_percentage' in metadata:
                print(f"Chaffee: {metadata['chaffee_percentage']:.1f}%")
            if 'speaker_distribution' in metadata:
                print("Speaker distribution:")
                for speaker, percentage in metadata['speaker_distribution'].items():
                    print(f"  {speaker}: {percentage:.1f}%")
        
        # Save output if requested
        if args.output:
            if args.format == 'json':
                with open(args.output, 'w') as f:
                    json.dump(output_data, f, indent=2)
            else:
                with open(args.output, 'w') as f:
                    for segment in segments:
                        f.write(f"{segment.start:.1f}\t{segment.end:.1f}\t{segment.text}\n")
            print(f"Results saved to: {args.output}")
    
    else:
        print("Failed to fetch transcript")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
