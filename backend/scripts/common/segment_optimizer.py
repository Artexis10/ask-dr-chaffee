#!/usr/bin/env python3
"""
Segment optimizer for enhanced semantic search quality.
Merges short segments while preserving speaker attribution and timing precision.
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class OptimizedSegment:
    """Optimized segment for better semantic search"""
    start: float
    end: float
    text: str
    speaker_label: str
    speaker_confidence: float
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float
    temperature_used: float
    re_asr: bool
    is_overlap: bool
    needs_refinement: bool
    embedding: Any = None
    
    # Optimization metadata
    original_count: int = 1  # How many original segments were merged
    merge_quality: str = "single"  # single, merged, complex

class SegmentOptimizer:
    """Optimizes segments for better semantic search while preserving speaker attribution"""
    
    def __init__(self, 
                 target_min_chars: int = 120,
                 target_max_chars: int = 300,
                 max_gap_seconds: float = 2.0,
                 max_merge_duration: float = 30.0):
        """
        Initialize segment optimizer
        
        Args:
            target_min_chars: Minimum characters for optimal segments
            target_max_chars: Maximum characters before splitting consideration
            max_gap_seconds: Maximum gap between segments to merge
            max_merge_duration: Maximum total duration of merged segment
        """
        self.target_min_chars = target_min_chars
        self.target_max_chars = target_max_chars
        self.max_gap_seconds = max_gap_seconds
        self.max_merge_duration = max_merge_duration
        
    def optimize_segments(self, segments: List[Any]) -> List[OptimizedSegment]:
        """
        Optimize segments for better semantic search quality
        
        Args:
            segments: List of TranscriptSegment objects
            
        Returns:
            List of OptimizedSegment objects with improved search characteristics
        """
        if not segments:
            return []
        
        logger.info(f"Optimizing {len(segments)} segments for semantic search")
        
        # Convert to OptimizedSegment objects
        optimized = []
        for segment in segments:
            opt_segment = OptimizedSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text,
                speaker_label=segment.speaker_label or 'GUEST',
                speaker_confidence=segment.speaker_confidence or 0.0,
                avg_logprob=segment.avg_logprob or 0.0,
                compression_ratio=segment.compression_ratio or 0.0,
                no_speech_prob=segment.no_speech_prob or 0.0,
                temperature_used=segment.temperature_used or 0.0,
                re_asr=segment.re_asr or False,
                is_overlap=segment.is_overlap or False,
                needs_refinement=segment.needs_refinement or False,
                embedding=getattr(segment, 'embedding', None)
            )
            optimized.append(opt_segment)
        
        # Apply optimization strategies
        optimized = self._merge_short_segments(optimized)
        optimized = self._split_very_long_segments(optimized)
        optimized = self._clean_text(optimized)
        
        logger.info(f"Optimization complete: {len(segments)} → {len(optimized)} segments")
        self._log_optimization_stats(segments, optimized)
        
        return optimized
    
    def _merge_short_segments(self, segments: List[OptimizedSegment]) -> List[OptimizedSegment]:
        """Merge consecutive same-speaker segments that are too short"""
        if len(segments) <= 1:
            return segments
        
        merged = []
        current = segments[0]
        
        for next_segment in segments[1:]:
            # Check if we should merge
            should_merge = self._should_merge_segments(current, next_segment)
            
            if should_merge:
                # Merge segments
                merged_segment = self._merge_two_segments(current, next_segment)
                current = merged_segment
            else:
                # Keep current segment and move to next
                merged.append(current)
                current = next_segment
        
        # Don't forget the last segment
        merged.append(current)
        
        return merged
    
    def _should_merge_segments(self, seg1: OptimizedSegment, seg2: OptimizedSegment) -> bool:
        """Determine if two segments should be merged"""
        
        # Must be same speaker
        if seg1.speaker_label != seg2.speaker_label:
            return False
        
        # Check gap between segments
        gap = seg2.start - seg1.end
        if gap > self.max_gap_seconds:
            return False
        
        # Check total duration after merge
        total_duration = seg2.end - seg1.start
        if total_duration > self.max_merge_duration:
            return False
        
        # Check if either segment is too short
        seg1_chars = len(seg1.text)
        seg2_chars = len(seg2.text)
        combined_chars = seg1_chars + seg2_chars + 1  # +1 for space
        
        # Always merge very short segments
        if seg1_chars < 30 or seg2_chars < 30:
            return True
        
        # Merge if combined length is under target and both are short
        if combined_chars < self.target_max_chars and (seg1_chars < self.target_min_chars or seg2_chars < self.target_min_chars):
            return True
        
        return False
    
    def _merge_two_segments(self, seg1: OptimizedSegment, seg2: OptimizedSegment) -> OptimizedSegment:
        """Merge two segments into one optimized segment"""
        
        # Combine text with proper spacing
        combined_text = seg1.text.strip()
        if combined_text and not combined_text.endswith(('.', '!', '?', ':')):
            combined_text += " " + seg2.text.strip()
        else:
            combined_text += " " + seg2.text.strip()
        
        # Average numerical properties weighted by duration
        seg1_duration = seg1.end - seg1.start
        seg2_duration = seg2.end - seg2.start
        total_duration = seg1_duration + seg2_duration
        
        if total_duration > 0:
            weight1 = seg1_duration / total_duration
            weight2 = seg2_duration / total_duration
        else:
            weight1 = weight2 = 0.5
        
        return OptimizedSegment(
            start=seg1.start,
            end=seg2.end,
            text=combined_text,
            speaker_label=seg1.speaker_label,
            speaker_confidence=max(seg1.speaker_confidence, seg2.speaker_confidence),
            avg_logprob=(seg1.avg_logprob * weight1 + seg2.avg_logprob * weight2),
            compression_ratio=(seg1.compression_ratio * weight1 + seg2.compression_ratio * weight2),
            no_speech_prob=(seg1.no_speech_prob * weight1 + seg2.no_speech_prob * weight2),
            temperature_used=(seg1.temperature_used * weight1 + seg2.temperature_used * weight2),
            re_asr=seg1.re_asr or seg2.re_asr,
            is_overlap=seg1.is_overlap or seg2.is_overlap,
            needs_refinement=seg1.needs_refinement or seg2.needs_refinement,
            embedding=None,  # Will be regenerated
            original_count=seg1.original_count + seg2.original_count,
            merge_quality="merged"
        )
    
    def _split_very_long_segments(self, segments: List[OptimizedSegment]) -> List[OptimizedSegment]:
        """Split segments that are too long for optimal embedding"""
        result = []
        
        for segment in segments:
            if len(segment.text) <= self.target_max_chars * 1.5:  # Allow some flexibility
                result.append(segment)
            else:
                # Split long segment at sentence boundaries
                split_segments = self._split_long_segment(segment)
                result.extend(split_segments)
        
        return result
    
    def _split_long_segment(self, segment: OptimizedSegment) -> List[OptimizedSegment]:
        """Split a long segment at natural boundaries"""
        text = segment.text
        
        # Try to split at sentence boundaries
        import re
        sentences = re.split(r'[.!?]+\s+', text)
        
        if len(sentences) <= 1:
            # No good split points, keep as is
            return [segment]
        
        # Create splits
        splits = []
        current_text = ""
        
        for sentence in sentences:
            potential_text = current_text + sentence + ". "
            
            if len(potential_text) > self.target_max_chars and current_text:
                # Create a split here
                duration_ratio = len(current_text) / len(text)
                split_duration = (segment.end - segment.start) * duration_ratio
                
                split_segment = OptimizedSegment(
                    start=segment.start + (segment.end - segment.start) * len(current_text) / len(text),
                    end=segment.start + split_duration,
                    text=current_text.strip(),
                    speaker_label=segment.speaker_label,
                    speaker_confidence=segment.speaker_confidence,
                    avg_logprob=segment.avg_logprob,
                    compression_ratio=segment.compression_ratio,
                    no_speech_prob=segment.no_speech_prob,
                    temperature_used=segment.temperature_used,
                    re_asr=segment.re_asr,
                    is_overlap=segment.is_overlap,
                    needs_refinement=segment.needs_refinement,
                    embedding=None,
                    original_count=segment.original_count,
                    merge_quality="split"
                )
                splits.append(split_segment)
                current_text = sentence + ". "
            else:
                current_text = potential_text
        
        # Add remaining text
        if current_text.strip():
            final_segment = OptimizedSegment(
                start=segment.start + (segment.end - segment.start) * (len(text) - len(current_text)) / len(text),
                end=segment.end,
                text=current_text.strip(),
                speaker_label=segment.speaker_label,
                speaker_confidence=segment.speaker_confidence,
                avg_logprob=segment.avg_logprob,
                compression_ratio=segment.compression_ratio,
                no_speech_prob=segment.no_speech_prob,
                temperature_used=segment.temperature_used,
                re_asr=segment.re_asr,
                is_overlap=segment.is_overlap,
                needs_refinement=segment.needs_refinement,
                embedding=None,
                original_count=segment.original_count,
                merge_quality="split"
            )
            splits.append(final_segment)
        
        return splits if splits else [segment]
    
    def _clean_text(self, segments: List[OptimizedSegment]) -> List[OptimizedSegment]:
        """Clean and normalize segment text"""
        for segment in segments:
            # Basic text cleaning
            text = segment.text.strip()
            
            # Remove excessive whitespace
            import re
            text = re.sub(r'\s+', ' ', text)
            
            # Ensure proper sentence ending
            if text and not text.endswith(('.', '!', '?', ':')):
                if len(text) > 20:  # Only add period for substantial text
                    text += '.'
            
            segment.text = text
        
        return segments
    
    def _log_optimization_stats(self, original: List[Any], optimized: List[OptimizedSegment]):
        """Log optimization statistics"""
        
        original_lengths = [len(seg.text) for seg in original]
        optimized_lengths = [len(seg.text) for seg in optimized]
        
        logger.info("Segment optimization results:")
        logger.info(f"  Original segments: {len(original)}")
        logger.info(f"  Optimized segments: {len(optimized)}")
        logger.info(f"  Reduction: {len(original) - len(optimized)} segments ({((len(original) - len(optimized))/len(original)*100):.1f}%)")
        logger.info(f"  Original avg length: {sum(original_lengths)/len(original_lengths):.1f} chars")
        logger.info(f"  Optimized avg length: {sum(optimized_lengths)/len(optimized_lengths):.1f} chars")
        
        # Quality distribution
        short_count = sum(1 for length in optimized_lengths if length < self.target_min_chars)
        good_count = sum(1 for length in optimized_lengths if self.target_min_chars <= length <= self.target_max_chars)
        long_count = sum(1 for length in optimized_lengths if length > self.target_max_chars)
        
        logger.info(f"  Quality distribution:")
        logger.info(f"    Short (<{self.target_min_chars} chars): {short_count} ({short_count/len(optimized)*100:.1f}%)")
        logger.info(f"    Optimal ({self.target_min_chars}-{self.target_max_chars} chars): {good_count} ({good_count/len(optimized)*100:.1f}%)")
        logger.info(f"    Long (>{self.target_max_chars} chars): {long_count} ({long_count/len(optimized)*100:.1f}%)")
