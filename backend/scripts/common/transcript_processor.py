import re
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class TranscriptProcessor:
    def __init__(self, chunk_duration_seconds: int = 45):
        self.chunk_duration_seconds = chunk_duration_seconds
    
    def chunk_transcript(self, transcript_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Chunk transcript into segments of specified duration.
        
        Args:
            transcript_entries: List of dicts with 'start', 'duration', 'text' keys
            
        Returns:
            List of chunk dictionaries with metadata
        """
        chunks = []
        current_chunk = {
            'text': '',
            'start_time': None,
            'end_time': None,
            'entries': []
        }
        
        for entry in transcript_entries:
            start_time = entry.get('start', 0)
            duration = entry.get('duration', 0) 
            text = entry.get('text', '').strip()
            
            if not text:
                continue
                
            # Initialize first chunk
            if current_chunk['start_time'] is None:
                current_chunk['start_time'] = start_time
            
            # Check if adding this entry would exceed chunk duration
            entry_end_time = start_time + duration
            chunk_duration = entry_end_time - current_chunk['start_time']
            
            if chunk_duration > self.chunk_duration_seconds and current_chunk['text']:
                # Finalize current chunk
                current_chunk['end_time'] = current_chunk['entries'][-1]['end_time']
                chunks.append(self._finalize_chunk(current_chunk, len(chunks)))
                
                # Start new chunk
                current_chunk = {
                    'text': text,
                    'start_time': start_time,
                    'end_time': entry_end_time,
                    'entries': [{'start': start_time, 'end': entry_end_time, 'text': text}]
                }
            else:
                # Add to current chunk
                if current_chunk['text']:
                    current_chunk['text'] += ' '
                current_chunk['text'] += text
                current_chunk['entries'].append({
                    'start': start_time, 
                    'end': entry_end_time, 
                    'text': text
                })
        
        # Add final chunk if it has content
        if current_chunk['text'].strip():
            current_chunk['end_time'] = current_chunk['entries'][-1]['end']
            chunks.append(self._finalize_chunk(current_chunk, len(chunks)))
        
        logger.info(f"Created {len(chunks)} chunks from transcript")
        return chunks
    
    def _finalize_chunk(self, chunk_data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Finalize a chunk with cleaned text and metadata"""
        text = self._clean_text(chunk_data['text'])
        
        return {
            'chunk_index': index,
            'start_time_seconds': chunk_data['start_time'],
            'end_time_seconds': chunk_data['end_time'],
            'text': text,
            'word_count': len(text.split()),
            'embedding': None  # Will be generated later
        }
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize transcript text"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common transcript artifacts
        text = re.sub(r'\[.*?\]', '', text)  # Remove [Music], [Applause], etc.
        text = re.sub(r'\(.*?\)', '', text)  # Remove (inaudible), etc.
        
        # Fix common punctuation issues
        text = re.sub(r'\s+([.!?])', r'\1', text)  # Remove space before punctuation
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Ensure space after punctuation
        
        # Capitalize first letter if needed
        text = text.strip()
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        
        return text

    def chunk_vtt_transcript(self, vtt_content: str) -> List[Dict[str, Any]]:
        """
        Process VTT format transcript (for Zoom recordings).
        
        Args:
            vtt_content: Raw VTT file content
            
        Returns:
            List of transcript entries for chunking
        """
        import webvtt
        
        # Parse VTT content
        try:
            # Write to temporary file since webvtt expects a file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.vtt', delete=False) as f:
                f.write(vtt_content)
                temp_path = f.name
            
            # Parse VTT
            captions = webvtt.read(temp_path)
            
            # Clean up temp file
            import os
            os.unlink(temp_path)
            
            entries = []
            for caption in captions:
                # Convert timestamp to seconds
                start_seconds = self._timestamp_to_seconds(caption.start)
                end_seconds = self._timestamp_to_seconds(caption.end)
                
                entries.append({
                    'start': start_seconds,
                    'duration': end_seconds - start_seconds,
                    'text': caption.text
                })
            
            return entries
            
        except Exception as e:
            logger.error(f"Error parsing VTT content: {e}")
            return []
    
    def _timestamp_to_seconds(self, timestamp: str) -> float:
        """Convert VTT timestamp (HH:MM:SS.mmm) to seconds"""
        try:
            parts = timestamp.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds_parts = parts[2].split('.')
            seconds = int(seconds_parts[0])
            milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
            
            total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
            return total_seconds
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse timestamp {timestamp}: {e}")
            return 0.0
