#!/usr/bin/env python3
"""
Enhanced ASR system with speaker identification and diarization
Integrates faster-whisper → WhisperX → pyannote pipeline with voice profiles
"""

import os
import json
import logging
import tempfile
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import torch
import librosa
import soundfile as sf
from datetime import datetime
import psutil
import gc

logger = logging.getLogger(__name__)

@dataclass
class WordSegment:
    """Word-level segment with speaker attribution"""
    word: str
    start: float
    end: float
    confidence: float
    speaker: Optional[str] = None
    speaker_confidence: Optional[float] = None
    speaker_margin: Optional[float] = None
    is_overlap: bool = False

@dataclass
class SpeakerSegment:
    """Speaker segment with attribution and confidence"""
    start: float
    end: float
    speaker: str
    confidence: float
    margin: float
    embedding: Optional[List[float]] = None
    is_overlap: bool = False
    cluster_id: Optional[int] = None

@dataclass
class TranscriptionResult:
    """Complete transcription result with speaker attribution"""
    text: str
    segments: List[Dict[str, Any]]  # Sentence-level segments
    words: List[WordSegment]
    speakers: List[SpeakerSegment]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'text': self.text,
            'segments': self.segments,
            'words': [asdict(w) for w in self.words],
            'speakers': [asdict(s) for s in self.speakers],
            'metadata': self.metadata
        }
    
    def get_low_confidence_segments(self, 
                                  avg_logprob_threshold: float = -0.35,
                                  compression_ratio_threshold: float = 2.4) -> List[Dict[str, Any]]:
        """Identify segments with low confidence for reprocessing"""
        low_conf_segments = []
        for segment in self.segments:
            avg_logprob = segment.get('avg_logprob', 0.0)
            compression_ratio = segment.get('compression_ratio', 1.0)
            
            if (avg_logprob <= avg_logprob_threshold or 
                compression_ratio >= compression_ratio_threshold):
                low_conf_segments.append(segment)
        
        return low_conf_segments

# Import the new configuration system
from .enhanced_asr_config import EnhancedASRConfig

class EnhancedASR:
    """Enhanced ASR system with speaker identification"""
    
    def __init__(self, config: Optional[EnhancedASRConfig] = None):
        self.config = config or EnhancedASRConfig()
        self._whisper_model = None
        self._whisperx_model = None
        self._diarization_pipeline = None
        self._voice_enrollment = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        
        logger.info(f"Enhanced ASR initialized on {self._device}")
    
    def _get_whisper_model(self):
        """Lazy load Whisper model"""
        if self._whisper_model is None:
            try:
                import faster_whisper
                
                logger.info(f"Loading Whisper model: {self.config.whisper_model}")
                self._whisper_model = faster_whisper.WhisperModel(
                    self.config.whisper_model,
                    device=self._device,
                    compute_type="float16" if self._device == "cuda" else "int8"
                )
                
            except ImportError:
                raise ImportError("faster-whisper not available. Install with: pip install faster-whisper")
        
        return self._whisper_model
    
    def _get_whisperx_model(self):
        """Lazy load WhisperX model for word alignment"""
        if self._whisperx_model is None:
            try:
                import whisperx
                
                logger.info("Loading WhisperX alignment model")
                self._whisperx_model = whisperx.load_align_model(
                    language_code="en", 
                    device=self._device
                )
                
            except ImportError:
                raise ImportError("WhisperX not available. Install with: pip install whisperx")
        
        return self._whisperx_model
    
    def _get_diarization_pipeline(self):
        """Lazy load diarization pipeline"""
        if self._diarization_pipeline is None:
            try:
                # Debug environment variables
                logger.info("=== Diarization Environment Variables ===")
                logger.info(f"USE_SIMPLE_DIARIZATION={os.getenv('USE_SIMPLE_DIARIZATION', 'true')}")
                logger.info(f"DIARIZE={os.getenv('DIARIZE', 'false')}")
                logger.info(f"MIN_SPEAKERS={os.getenv('MIN_SPEAKERS', 'None')}")
                logger.info(f"MAX_SPEAKERS={os.getenv('MAX_SPEAKERS', 'None')}")
                logger.info(f"HUGGINGFACE_HUB_TOKEN={os.getenv('HUGGINGFACE_HUB_TOKEN', 'None')[:5] if os.getenv('HUGGINGFACE_HUB_TOKEN') else 'None'}...")
                
                # Check if we should use simple diarization
                use_simple = os.getenv('USE_SIMPLE_DIARIZATION', 'true').lower() == 'true'
                
                if use_simple:
                    # Use our simple diarization that doesn't require authentication
                    logger.info("Using simple energy-based diarization (no HuggingFace auth required)")
                    from backend.scripts.common.simple_diarization import simple_energy_based_diarization
                    self._diarization_pipeline = simple_energy_based_diarization
                else:
                    # Use pyannote diarization (requires authentication)
                    from pyannote.audio import Pipeline
                    
                    logger.info(f"Loading diarization pipeline: {self.config.diarization_model}")
                    self._diarization_pipeline = Pipeline.from_pretrained(
                        self.config.diarization_model,
                        use_auth_token=os.getenv('HUGGINGFACE_HUB_TOKEN')  # Required for some models
                    )
                    
                    if self._device == "cuda":
                        self._diarization_pipeline = self._diarization_pipeline.to(torch.device("cuda"))
                
            except ImportError:
                raise ImportError("pyannote.audio not available. Install with: pip install pyannote.audio")
            except Exception as e:
                logger.error(f"Failed to load diarization pipeline: {e}")
                logger.info("Using simple energy-based diarization as fallback")
                from backend.scripts.common.simple_diarization import simple_energy_based_diarization
                self._diarization_pipeline = simple_energy_based_diarization
        
        return self._diarization_pipeline
    
    def _get_voice_enrollment(self):
        """Lazy load voice enrollment system"""
        if self._voice_enrollment is None:
            from .voice_enrollment import VoiceEnrollment
            self._voice_enrollment = VoiceEnrollment(voices_dir=self.config.voices_dir)
        
        return self._voice_enrollment
    
    def _check_monologue_fast_path(self, audio_path: str) -> Optional[TranscriptionResult]:
        """Check if we can use monologue fast-path (Chaffee only)"""
        if not self.config.assume_monologue:
            return None
        
        try:
            # Load Chaffee profile
            enrollment = self._get_voice_enrollment()
            chaffee_profile = enrollment.load_profile("chaffee")
            
            if not chaffee_profile:
                logger.warning("Chaffee profile not found, skipping monologue fast-path")
                return None
            
            # Extract a few embeddings from the audio to test
            embeddings = enrollment._extract_embeddings_from_audio(audio_path)
            
            if not embeddings:
                return None
            
            # Test first few embeddings
            test_embeddings = embeddings[:3]  # Test first 15 seconds
            similarities = []
            
            for emb in test_embeddings:
                sim = enrollment.compute_similarity(emb, chaffee_profile)
                similarities.append(sim)
            
            avg_similarity = np.mean(similarities)
            threshold = self.config.chaffee_min_sim + 0.03  # Higher threshold for fast-path
            
            if avg_similarity >= threshold:
                logger.info(f"Monologue fast-path triggered: avg_sim={avg_similarity:.3f} >= {threshold:.3f}")
                
                # Transcribe without diarization
                result = self._transcribe_whisper_only(audio_path)
                if result:
                    # Label everything as Chaffee
                    for segment in result.segments:
                        segment['speaker'] = 'Chaffee'
                        segment['speaker_confidence'] = avg_similarity
                    
                    for word in result.words:
                        word.speaker = 'Chaffee'
                        word.speaker_confidence = avg_similarity
                    
                    result.metadata['monologue_fast_path'] = True
                    result.metadata['chaffee_similarity'] = avg_similarity
                    
                    return result
            
            logger.info(f"Monologue test failed: avg_sim={avg_similarity:.3f} < {threshold:.3f}")
            return None
            
        except Exception as e:
            logger.warning(f"Monologue fast-path check failed: {e}")
            return None
    
    def _transcribe_whisper_only(self, audio_path: str) -> Optional[TranscriptionResult]:
        """Transcribe using Whisper only (no diarization)"""
        try:
            model = self._get_whisper_model()
            
            # Transcribe with word timestamps
            segments, info = model.transcribe(
                audio_path,
                language="en",
                word_timestamps=True,
                vad_filter=True,
                beam_size=5
            )
            
            # Convert segments
            result_segments = []
            words = []
            full_text = ""
            
            for segment in segments:
                segment_dict = {
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text.strip(),
                    'speaker': None,  # Will be filled by caller
                    'speaker_confidence': None
                }
                result_segments.append(segment_dict)
                full_text += segment.text
                
                # Extract words if available
                if hasattr(segment, 'words') and segment.words:
                    for word in segment.words:
                        words.append(WordSegment(
                            word=word.word,
                            start=word.start,
                            end=word.end,
                            confidence=getattr(word, 'probability', 0.0)
                        ))
            
            metadata = {
                'whisper_model': self.config.whisper_model,
                'language': info.language if hasattr(info, 'language') else 'en',
                'duration': info.duration if hasattr(info, 'duration') else 0.0,
                'method': 'whisper_only'
            }
            
            return TranscriptionResult(
                text=full_text.strip(),
                segments=result_segments,
                words=words,
                speakers=[],
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Whisper-only transcription failed: {e}")
            return None
    
    def _perform_diarization(self, audio_path: str) -> Optional[List[Tuple[float, float, int]]]:
        """Perform speaker diarization"""
        try:
            # Get the configured diarization pipeline
            diarization_pipeline = self._get_diarization_pipeline()
            
            logger.info("Performing speaker diarization...")
            
            # Check if we're using simple diarization or pyannote
            use_simple = os.getenv('USE_SIMPLE_DIARIZATION', 'true').lower() == 'true'
            
            if use_simple:
                # Simple energy-based diarization
                segments = diarization_pipeline(audio_path)
            else:
                # pyannote diarization
                logger.info("Using pyannote diarization")
                
                # Set min and max speakers if configured
                min_speakers = self.config.alignment.min_speakers or 2  # Default to at least 2 speakers
                max_speakers = self.config.alignment.max_speakers
                
                logger.info(f"Diarization with min_speakers={min_speakers}, max_speakers={max_speakers}")
                
                # Run diarization with speaker count constraints
                logger.info(f"Running pyannote diarization with min_speakers={min_speakers}, max_speakers={max_speakers}")
                diarization = diarization_pipeline(
                    audio_path,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers
                )
                
                # Log diarization results
                logger.info(f"Diarization result type: {type(diarization)}")
                logger.info(f"Diarization result: {diarization}")
                
                # Convert pyannote format to our format
                segments = []
                for turn, _, speaker in diarization.itertracks(yield_label=True):
                    # Extract speaker ID from pyannote format (e.g., 'SPEAKER_0' -> 0)
                    try:
                        speaker_id = int(speaker.split('_')[1])
                        segments.append((turn.start, turn.end, speaker_id))
                    except (ValueError, IndexError):
                        logger.warning(f"Couldn't parse speaker ID from {speaker}, using 0")
                        segments.append((turn.start, turn.end, 0))
                
                # Sort by start time
                segments.sort(key=lambda x: x[0])
                
                # Log segments
                logger.info(f"Diarization found {len(segments)} segments with {len(set(s[2] for s in segments))} unique speakers")
                for i, (start, end, speaker_id) in enumerate(segments[:10]):
                    logger.info(f"Segment {i}: {start:.2f}-{end:.2f} -> Speaker {speaker_id}")
                if len(segments) > 10:
                    logger.info(f"... and {len(segments) - 10} more segments")
            
            logger.info(f"Diarization found {len(segments)} segments")
            return segments
            
        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            logger.warning("Diarization failed, using single unknown speaker")
            
            # Fallback: create a single segment for the entire audio
            try:
                import librosa
                duration = librosa.get_duration(path=audio_path)
                return [(0.0, duration, 0)]
            except:
                return [(0.0, 60.0, 0)]  # Arbitrary 60-second segment
    
    def _identify_speakers(self, audio_path: str, diarization_segments: List[Tuple[float, float, int]]) -> List[SpeakerSegment]:
        """Identify speakers using voice profiles"""
        try:
            # If no segments, return empty list
            if not diarization_segments:
                logger.warning("No diarization segments provided")
                return []
                
            enrollment = self._get_voice_enrollment()
            
            # Load all available profiles
            profile_names = enrollment.list_profiles()
            profiles = {}
            for name in profile_names:
                profile = enrollment.load_profile(name.lower())
                if profile is not None:  # Explicit None check
                    profiles[name.lower()] = profile
            
            if not profiles:
                logger.warning("No voice profiles available for speaker identification")
                return []
            
            logger.info(f"Identifying speakers using {len(profiles)} profiles: {list(profiles.keys())}")
            
            # Group segments by cluster ID
            clusters = {}
            for start, end, cluster_id in diarization_segments:
                if cluster_id not in clusters:
                    clusters[cluster_id] = []
                clusters[cluster_id].append((start, end))
            
            speaker_segments = []
            
            for cluster_id, segments in clusters.items():
                # Calculate total duration for this cluster
                total_duration = sum(end - start for start, end in segments)
                
                if total_duration < self.config.min_speaker_duration:
                    logger.info(f"Cluster {cluster_id} too short ({total_duration:.1f}s), marking as {self.config.unknown_label}")
                    # Add segments as unknown
                    for start, end in segments:
                        speaker_segments.append(SpeakerSegment(
                            start=start,
                            end=end,
                            speaker=self.config.unknown_label,
                            confidence=0.0,
                            margin=0.0,
                            cluster_id=cluster_id
                        ))
                    continue
                
                # Extract embeddings for this cluster (sample a few segments)
                cluster_embeddings = []
                sample_segments = segments[:3]  # Sample first 3 segments
                
                for start, end in sample_segments:
                    try:
                        # Extract audio segment
                        audio, sr = librosa.load(audio_path, sr=16000, offset=start, duration=end-start)
                        
                        if len(audio) > sr:  # At least 1 second
                            # Save to temp file for embedding extraction
                            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                                sf.write(tmp_file.name, audio, sr)
                                embeddings = enrollment._extract_embeddings_from_audio(tmp_file.name)
                                if embeddings:  # Check if embeddings were extracted
                                    cluster_embeddings.extend(embeddings)
                                os.unlink(tmp_file.name)
                    
                    except Exception as e:
                        logger.warning(f"Failed to extract embedding for cluster {cluster_id} segment {start}-{end}: {e}")
                
                if not cluster_embeddings:
                    logger.warning(f"No embeddings extracted for cluster {cluster_id}")
                    # Mark as unknown
                    for start, end in segments:
                        speaker_segments.append(SpeakerSegment(
                            start=start,
                            end=end,
                            speaker=self.config.unknown_label,
                            confidence=0.0,
                            margin=0.0,
                            cluster_id=cluster_id
                        ))
                    continue
                
                # Compute average embedding for cluster
                cluster_embedding = np.mean(cluster_embeddings, axis=0)
                
                # Compare against all profiles
                best_match = None
                best_similarity = 0.0
                similarities = {}
                
                # Debug info
                logger.info(f"Cluster {cluster_id}: Testing against {len(profiles)} profiles")
                
                for profile_name, profile in profiles.items():
                    # Fix NumPy array comparison issue
                    try:
                        # Ensure we get a scalar float
                        sim = float(enrollment.compute_similarity(cluster_embedding, profile))
                        similarities[profile_name] = sim
                        
                        logger.info(f"Cluster {cluster_id}: Similarity with {profile_name}: {sim:.3f}")
                        
                        # Simple float comparison
                        if sim > best_similarity:
                            best_similarity = sim
                            best_match = profile_name
                    except Exception as e:
                        logger.warning(f"Error computing similarity for {profile_name}: {e}")
                        similarities[profile_name] = 0.0
                
                # Determine speaker attribution
                speaker_name = self.config.unknown_label
                confidence = 0.0
                margin = 0.0
                
                if best_match:
                    # Get appropriate threshold
                    if best_match.lower() == 'chaffee':
                        threshold = self.config.chaffee_min_sim
                    else:
                        threshold = self.config.guest_min_sim
                    
                    # Check if similarity meets threshold
                    if best_similarity >= threshold:
                        # Check margin (difference from second-best)
                        sorted_sims = sorted(similarities.values(), reverse=True)
                        if len(sorted_sims) > 1:
                            margin = sorted_sims[0] - sorted_sims[1]
                        else:
                            margin = best_similarity  # Only one profile
                        
                        if margin >= self.config.attr_margin:
                            speaker_name = best_match.title()
                            confidence = best_similarity
                        else:
                            logger.info(f"Cluster {cluster_id}: Insufficient margin {margin:.3f} < {self.config.attr_margin:.3f}")
                    else:
                        logger.info(f"Cluster {cluster_id}: Best similarity {best_similarity:.3f} < threshold {threshold:.3f}")
                
                logger.info(f"Cluster {cluster_id} -> {speaker_name} (conf={confidence:.3f}, margin={margin:.3f})")
                
                # Create speaker segments
                for start, end in segments:
                    speaker_segments.append(SpeakerSegment(
                        start=start,
                        end=end,
                        speaker=speaker_name,
                        confidence=confidence,
                        margin=margin,
                        embedding=cluster_embedding.tolist(),
                        cluster_id=cluster_id
                    ))
            
            return speaker_segments
            
        except Exception as e:
            logger.error(f"Speaker identification failed: {e}")
            return []
    
    def _align_words_with_speakers(self, transcription_result: TranscriptionResult, speaker_segments: List[SpeakerSegment]) -> TranscriptionResult:
        """Align word-level timestamps with speaker segments"""
        if not self.config.align_words or not transcription_result.words:
            return transcription_result
        
        try:
            # Create speaker lookup table
            speaker_timeline = []
            for spk_seg in speaker_segments:
                speaker_timeline.append((spk_seg.start, spk_seg.end, spk_seg.speaker, spk_seg.confidence, spk_seg.margin))
            
            # Sort by start time
            speaker_timeline.sort(key=lambda x: x[0])
            
            # Assign speakers to words
            for word in transcription_result.words:
                word_start = word.start
                word_end = word.end
                
                # Find overlapping speaker segments
                overlapping_speakers = []
                for spk_start, spk_end, speaker, confidence, margin in speaker_timeline:
                    # Check for overlap
                    if not (word_end <= spk_start or word_start >= spk_end):
                        overlap_duration = min(word_end, spk_end) - max(word_start, spk_start)
                        overlapping_speakers.append((speaker, confidence, margin, overlap_duration))
                
                if overlapping_speakers:
                    # Sort by overlap duration (prefer longer overlaps)
                    overlapping_speakers.sort(key=lambda x: x[3], reverse=True)
                    
                    best_speaker, best_confidence, best_margin, _ = overlapping_speakers[0]
                    
                    # Check if this is an overlap situation (multiple speakers)
                    is_overlap = len(overlapping_speakers) > 1
                    
                    # Apply stricter thresholds during overlap
                    if is_overlap:
                        threshold_bonus = self.config.overlap_bonus
                        if best_speaker.lower() == 'chaffee':
                            required_threshold = self.config.chaffee_min_sim + threshold_bonus
                        else:
                            required_threshold = self.config.guest_min_sim + threshold_bonus
                        
                        if best_confidence < required_threshold:
                            best_speaker = self.config.unknown_label
                            best_confidence = 0.0
                            best_margin = 0.0
                    
                    word.speaker = best_speaker
                    word.speaker_confidence = best_confidence
                    word.speaker_margin = best_margin
                    word.is_overlap = is_overlap
                else:
                    word.speaker = self.config.unknown_label
            
            # Update sentence-level segments with speaker info
            for segment in transcription_result.segments:
                # Find words in this segment
                segment_words = [w for w in transcription_result.words 
                               if w.start >= segment['start'] and w.end <= segment['end']]
                
                if segment_words:
                    # Use majority speaker
                    speaker_counts = {}
                    confidence_sum = {}
                    
                    for word in segment_words:
                        if word.speaker and word.speaker != self.config.unknown_label:
                            speaker_counts[word.speaker] = speaker_counts.get(word.speaker, 0) + 1
                            confidence_sum[word.speaker] = confidence_sum.get(word.speaker, 0) + (word.speaker_confidence or 0)
                    
                    if speaker_counts:
                        majority_speaker = max(speaker_counts.keys(), key=lambda x: speaker_counts[x])
                        avg_confidence = confidence_sum[majority_speaker] / speaker_counts[majority_speaker]
                        
                        segment['speaker'] = majority_speaker
                        segment['speaker_confidence'] = avg_confidence
                    else:
                        segment['speaker'] = self.config.unknown_label
                        segment['speaker_confidence'] = 0.0
            
            return transcription_result
            
        except Exception as e:
            logger.error(f"Word-speaker alignment failed: {e}")
            return transcription_result
    
    def _perform_two_pass_qa(self, result: TranscriptionResult, audio_path: str) -> TranscriptionResult:
        """Perform two-pass quality assurance on low-confidence segments"""
        if not self.config.quality.enable_two_pass:
            return result
        
        # Identify low-confidence segments
        low_conf_segments = result.get_low_confidence_segments(
            self.config.quality.low_conf_avg_logprob,
            self.config.quality.low_conf_compression_ratio
        )
        
        if not low_conf_segments:
            logger.info("No low-confidence segments detected, skipping two-pass QA")
            return result
        
        logger.info(f"Found {len(low_conf_segments)} low-confidence segments, performing two-pass QA")
        
        # Prepare stricter parameters for retry
        retry_params = {
            'language': self.config.whisper.language,
            'task': self.config.whisper.task,
            'beam_size': self.config.quality.retry_beam_size,
            'word_timestamps': self.config.whisper.word_timestamps,
            'vad_filter': self.config.whisper.vad_filter,
            'temperature': self.config.quality.retry_temperature,
            'initial_prompt': self.config.whisper.initial_prompt,
            'chunk_length': self.config.whisper.chunk_length
        }
        
        improved_count = 0
        
        # Note: For now, we'll log the segments but not re-process individual segments
        # Full segment re-processing would require more complex audio manipulation
        logger.info(f"Two-pass QA identified {len(low_conf_segments)} segments for potential improvement")
        for segment in low_conf_segments:
            logger.debug(f"Low confidence: {segment['start']:.1f}-{segment['end']:.1f}s, "
                        f"logprob={segment.get('avg_logprob', 0.0):.3f}, "
                        f"compression={segment.get('compression_ratio', 1.0):.2f}")
        
        result.metadata['two_pass_qa'] = {
            'enabled': True,
            'low_conf_segments': len(low_conf_segments),
            'improved_segments': improved_count,
            'total_segments': len(result.segments)
        }
        
        return result
    
    def transcribe_with_speaker_id(self, audio_path: str, **kwargs) -> Optional[TranscriptionResult]:
        """
        Complete transcription with speaker identification
        
        Args:
            audio_path: Path to audio file
            **kwargs: Additional options to override config
            
        Returns:
            TranscriptionResult with speaker attribution
        """
        try:
            # Log configuration for debugging
            self.config.log_config()
            logger.info(f"Starting enhanced ASR transcription: {audio_path}")
            
            # Check monologue fast-path first
            if self.config.assume_monologue:
                fast_result = self._check_monologue_fast_path(audio_path)
                if fast_result:
                    logger.info("Used monologue fast-path")
                    # Apply two-pass QA even to fast-path results
                    fast_result = self._perform_two_pass_qa(fast_result, audio_path)
                    return fast_result
            
            # Full pipeline: Enhanced Whisper + Diarization + Speaker ID
            logger.info("Using full pipeline: Enhanced Whisper + Diarization + Speaker ID")
            
            # Step 1: Enhanced Whisper transcription with fallbacks
            transcription_result = self._transcribe_whisper_only(audio_path)
            if not transcription_result:
                logger.error("Enhanced Whisper transcription failed")
                return None
            
            # Step 2: Speaker diarization
            diarization_segments = self._perform_diarization(audio_path)
            if not diarization_segments:
                logger.warning("Diarization failed, using single unknown speaker")
                # Mark everything as unknown
                for segment in transcription_result.segments:
                    segment['speaker'] = self.config.unknown_label
                    segment['speaker_confidence'] = 0.0
                
                for word in transcription_result.words:
                    word.speaker = self.config.unknown_label
                
                transcription_result.metadata['diarization_failed'] = True
                return transcription_result
            
            # Step 3: Speaker identification
            speaker_segments = self._identify_speakers(audio_path, diarization_segments)
            transcription_result.speakers = speaker_segments
            
            # Step 4: Word-level alignment (legacy compatibility)
            if self.config.align_words:
                transcription_result = self._align_words_with_speakers(transcription_result, speaker_segments)
            
            # Step 5: Two-pass quality assurance
            transcription_result = self._perform_two_pass_qa(transcription_result, audio_path)
            
            # Update metadata
            transcription_result.metadata.update({
                'diarization_segments': len(diarization_segments),
                'identified_speakers': len(set(s.speaker for s in speaker_segments)),
                'word_alignment': self.config.align_words,
                'method': 'full_enhanced_pipeline',
                'whisper_config': {
                    'model': transcription_result.metadata.get('whisper_model'),
                    'compute_type': transcription_result.metadata.get('compute_type'),
                    'beam_size': transcription_result.metadata.get('beam_size'),
                    'domain_prompt': bool(self.config.whisper.initial_prompt)
                }
            })
            
            # Generate summary statistics
            self._add_summary_stats(transcription_result)
            
            # Log final quality metrics
            self._log_quality_metrics(transcription_result)
            
            logger.info("Enhanced ASR transcription completed successfully")
            return transcription_result
            
        except Exception as e:
            logger.error(f"Enhanced ASR transcription failed: {e}")
            if "out of memory" in str(e).lower() or "oom" in str(e).lower():
                logger.error("CUDA OOM detected. Consider:")
                logger.error("  1. Using smaller model: export WHISPER_MODEL=distil-large-v3")
                logger.error("  2. Reducing compute precision: export WHISPER_COMPUTE=int8_float16")
                logger.error("  3. Smaller chunk size: export WHISPER_CHUNK=30")
            return None
    
    def _add_summary_stats(self, result: TranscriptionResult):
        """Add summary statistics to transcription result"""
        try:
            # Speaker time distribution
            speaker_times = {}
            total_duration = 0.0
            
            for spk_seg in result.speakers:
                duration = spk_seg.end - spk_seg.start
                total_duration += duration
                
                if spk_seg.speaker not in speaker_times:
                    speaker_times[spk_seg.speaker] = 0.0
                speaker_times[spk_seg.speaker] += duration
            
            # Convert to percentages
            speaker_percentages = {}
            if total_duration > 0:
                for speaker, time in speaker_times.items():
                    speaker_percentages[speaker] = (time / total_duration) * 100
            
            # Confidence statistics
            confidence_stats = {}
            for speaker in speaker_times.keys():
                confidences = [s.confidence for s in result.speakers if s.speaker == speaker]
                if confidences:
                    confidence_stats[speaker] = {
                        'min': min(confidences),
                        'max': max(confidences),
                        'avg': np.mean(confidences)
                    }
            
            # Unknown segments count
            unknown_segments = len([s for s in result.speakers if s.speaker == self.config.unknown_label])
            
            result.metadata['summary'] = {
                'total_duration': total_duration,
                'speaker_time_percentages': speaker_percentages,
                'confidence_stats': confidence_stats,
                'unknown_segments': unknown_segments,
                'chaffee_percentage': speaker_percentages.get('Chaffee', 0.0)
            }
            
            # Log summary
            logger.info("=== Transcription Summary ===")
            logger.info(f"Total duration: {total_duration:.1f}s")
            for speaker, percentage in speaker_percentages.items():
                logger.info(f"{speaker}: {percentage:.1f}% of audio")
            
            if unknown_segments > 0:
                logger.warning(f"Unknown segments: {unknown_segments}")
            
        except Exception as e:
            logger.warning(f"Failed to generate summary stats: {e}")
    
    def _log_quality_metrics(self, result: TranscriptionResult):
        """Log quality metrics for monitoring and debugging"""
        try:
            segments = result.segments
            if not segments:
                return
            
            # Calculate quality metrics
            avg_logprobs = [s.get('avg_logprob', 0.0) for s in segments]
            compression_ratios = [s.get('compression_ratio', 1.0) for s in segments]
            no_speech_probs = [s.get('no_speech_prob', 0.0) for s in segments]
            
            avg_logprob_mean = np.mean(avg_logprobs) if avg_logprobs else 0.0
            compression_mean = np.mean(compression_ratios) if compression_ratios else 1.0
            no_speech_mean = np.mean(no_speech_probs) if no_speech_probs else 0.0
            
            # Count low-confidence segments
            low_conf_count = len(result.get_low_confidence_segments(
                self.config.quality.low_conf_avg_logprob,
                self.config.quality.low_conf_compression_ratio
            ))
            
            logger.info("=== Quality Metrics ===")
            logger.info(f"Average log probability: {avg_logprob_mean:.3f}")
            logger.info(f"Average compression ratio: {compression_mean:.2f}")
            logger.info(f"Average no-speech probability: {no_speech_mean:.3f}")
            logger.info(f"Low confidence segments: {low_conf_count}/{len(segments)} ({100*low_conf_count/len(segments):.1f}%)")
            
            # VRAM usage if available
            if torch.cuda.is_available():
                vram_used = torch.cuda.memory_allocated() / 1024**3
                vram_peak = torch.cuda.max_memory_allocated() / 1024**3
                logger.info(f"VRAM usage: {vram_used:.2f}GB (peak: {vram_peak:.2f}GB)")
            
            # Store metrics in metadata
            result.metadata['quality_metrics'] = {
                'avg_logprob_mean': avg_logprob_mean,
                'compression_ratio_mean': compression_mean,
                'no_speech_prob_mean': no_speech_mean,
                'low_conf_segments': low_conf_count,
                'low_conf_percentage': 100 * low_conf_count / len(segments) if segments else 0
            }
            
        except Exception as e:
            logger.warning(f"Failed to log quality metrics: {e}")

    def run(self, audio_file: str, **kwargs) -> Optional[TranscriptionResult]:
        """Public API method for running ASR with keyword arguments"""
        # Apply any runtime overrides to config
        if kwargs:
            # Create a new config with overrides for this run
            runtime_config = EnhancedASRConfig(**kwargs)
            original_config = self.config
            self.config = runtime_config
            try:
                return self.transcribe_with_speaker_id(audio_file, **kwargs)
            finally:
                self.config = original_config
        else:
            return self.transcribe_with_speaker_id(audio_file)

def main():
    """CLI for enhanced ASR system"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced ASR with Speaker Identification')
    parser.add_argument('audio_file', help='Path to audio file')
    parser.add_argument('--output', '-o', help='Output file path (JSON format)')
    parser.add_argument('--format', choices=['json', 'srt', 'vtt'], default='json', help='Output format')
    
    # New Whisper model options
    parser.add_argument('--model', help='Whisper model (large-v3, large-v3-turbo, distil-large-v3, etc.)')
    parser.add_argument('--device', choices=['cuda', 'cpu'], help='Processing device')
    parser.add_argument('--compute-type', choices=['float16', 'int8_float16', 'int8'], help='Compute precision')
    parser.add_argument('--beam-size', type=int, help='Beam search size')
    parser.add_argument('--chunk-length', type=int, help='Audio chunk length in seconds')
    parser.add_argument('--disable-vad', action='store_true', help='Disable voice activity detection')
    parser.add_argument('--language', default='en', help='Audio language')
    parser.add_argument('--task', choices=['transcribe', 'translate'], default='transcribe', help='Whisper task')
    parser.add_argument('--domain-prompt', help='Domain-specific prompt')
    parser.add_argument('--disable-two-pass', action='store_true', help='Disable two-pass quality assurance')
    parser.add_argument('--disable-alignment', action='store_true', help='Disable word alignment')
    
    # Legacy speaker ID configuration overrides (backward compatibility)
    parser.add_argument('--chaffee-min-sim', type=float, help='Minimum similarity for Chaffee')
    parser.add_argument('--guest-min-sim', type=float, help='Minimum similarity for guests')
    parser.add_argument('--attr-margin', type=float, help='Attribution margin threshold')
    parser.add_argument('--overlap-bonus', type=float, help='Overlap threshold bonus')
    parser.add_argument('--assume-monologue', action='store_true', help='Assume monologue (Chaffee only)')
    parser.add_argument('--no-word-alignment', action='store_true', help='Disable word alignment (legacy)')
    parser.add_argument('--unknown-label', help='Label for unknown speakers')
    parser.add_argument('--voices-dir', help='Directory containing voice profiles')
    
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Create config with overrides
    overrides = {}
    
    # New Whisper options
    if args.model:
        overrides['model'] = args.model
    if args.device:
        overrides['device'] = args.device
    if args.compute_type:
        overrides['compute_type'] = args.compute_type
    if args.beam_size:
        overrides['beam_size'] = args.beam_size
    if args.chunk_length:
        overrides['chunk_length'] = args.chunk_length
    if args.disable_vad:
        overrides['vad_filter'] = False
    if args.language:
        overrides['language'] = args.language
    if args.task:
        overrides['task'] = args.task
    if args.domain_prompt:
        overrides['initial_prompt'] = args.domain_prompt
    if args.disable_two_pass:
        overrides['enable_two_pass'] = False
    if args.disable_alignment:
        overrides['enable_alignment'] = False
    
    # Legacy speaker ID options
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
    
    # Initialize ASR system
    asr = EnhancedASR(config)
    
    # Transcribe using the new run method
    result = asr.run(args.audio_file)
    
    if not result:
        print("Transcription failed")
        return 1
    
    # Output result
    if args.format == 'json':
        output_data = result.to_dict()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"Results saved to: {args.output}")
        else:
            print(json.dumps(output_data, indent=2))
    
    elif args.format in ['srt', 'vtt']:
        # TODO: Implement SRT/VTT output with speaker prefixes
        print("SRT/VTT output not yet implemented")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
