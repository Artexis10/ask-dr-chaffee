#!/usr/bin/env python3
"""
Production-ready transcript service with cloud API integration
Designed for hybrid local bulk processing + cloud daily updates
"""

import os
import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
import openai
from openai import OpenAI

# Local imports
from .transcript_fetch import TranscriptSegment, TranscriptFetcher

logger = logging.getLogger(__name__)

class TranscriptionMethod(Enum):
    YOUTUBE_API = "youtube_api"
    YOUTUBE_TRANSCRIPT_API = "youtube_transcript_api"  
    LOCAL_WHISPER = "local_whisper"
    OPENAI_WHISPER = "openai_whisper"
    ASSEMBLYAI = "assemblyai"

@dataclass
class TranscriptionConfig:
    """Production transcription configuration"""
    environment: str = "production"  # "local" or "production"
    preferred_method: TranscriptionMethod = TranscriptionMethod.OPENAI_WHISPER
    fallback_methods: List[TranscriptionMethod] = None
    openai_api_key: Optional[str] = None
    assemblyai_api_key: Optional[str] = None
    cost_limit_per_day: float = 10.00
    max_retries: int = 3
    
    def __post_init__(self):
        if self.fallback_methods is None:
            if self.environment == "local":
                self.fallback_methods = [
                    TranscriptionMethod.YOUTUBE_API,
                    TranscriptionMethod.YOUTUBE_TRANSCRIPT_API,
                    TranscriptionMethod.LOCAL_WHISPER
                ]
            else:
                self.fallback_methods = [
                    TranscriptionMethod.YOUTUBE_API,
                    TranscriptionMethod.YOUTUBE_TRANSCRIPT_API,
                    TranscriptionMethod.OPENAI_WHISPER
                ]

class ProductionTranscriptService:
    """Production-ready transcript service supporting multiple backends"""
    
    def __init__(self, config: TranscriptionConfig = None):
        self.config = config or TranscriptionConfig()
        self.openai_client = None
        self.local_fetcher = None
        self.daily_cost = 0.0
        
        # Initialize clients based on environment
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize API clients based on configuration"""
        
        # OpenAI client for production
        if self.config.openai_api_key or os.getenv('OPENAI_API_KEY'):
            try:
                self.openai_client = OpenAI(
                    api_key=self.config.openai_api_key or os.getenv('OPENAI_API_KEY')
                )
                logger.info("OpenAI Whisper API client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")
        
        # Local Whisper for bulk processing
        if TranscriptionMethod.LOCAL_WHISPER in self.config.fallback_methods:
            try:
                self.local_fetcher = TranscriptFetcher()
                logger.info("Local Whisper client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize local Whisper: {e}")
    
    async def get_transcript(self, video_id: str, video_metadata: Dict = None) -> tuple[List[TranscriptSegment], str, Dict[str, Any]]:
        """
        Get transcript using production-optimized method selection
        
        Returns:
            tuple: (segments, method_used, metadata)
        """
        
        # Try preferred method first
        try:
            segments, metadata = await self._try_method(
                self.config.preferred_method, 
                video_id, 
                video_metadata
            )
            if segments:
                return segments, self.config.preferred_method.value, metadata
        except Exception as e:
            logger.warning(f"Preferred method {self.config.preferred_method} failed: {e}")
        
        # Try fallback methods
        for method in self.config.fallback_methods:
            try:
                segments, metadata = await self._try_method(method, video_id, video_metadata)
                if segments:
                    return segments, method.value, metadata
            except Exception as e:
                logger.warning(f"Fallback method {method} failed: {e}")
                continue
        
        return [], "failed", {"error": "All transcription methods failed"}
    
    async def _try_method(self, method: TranscriptionMethod, video_id: str, video_metadata: Dict = None) -> tuple[List[TranscriptSegment], Dict[str, Any]]:
        """Try a specific transcription method"""
        
        if method == TranscriptionMethod.YOUTUBE_API:
            return await self._youtube_api_transcribe(video_id)
        
        elif method == TranscriptionMethod.YOUTUBE_TRANSCRIPT_API:
            return await self._youtube_transcript_api_transcribe(video_id)
        
        elif method == TranscriptionMethod.LOCAL_WHISPER:
            return await self._local_whisper_transcribe(video_id, video_metadata)
        
        elif method == TranscriptionMethod.OPENAI_WHISPER:
            return await self._openai_whisper_transcribe(video_id, video_metadata)
        
        else:
            raise ValueError(f"Unsupported transcription method: {method}")
    
    async def _youtube_api_transcribe(self, video_id: str) -> tuple[List[TranscriptSegment], Dict[str, Any]]:
        """Use YouTube Data API for captions"""
        if not self.local_fetcher:
            raise Exception("Local fetcher not available")
        
        # Use existing YouTube API implementation
        segments = self.local_fetcher.fetch_youtube_transcript(video_id)
        if segments:
            return segments, {"method": "youtube_api", "cost": 0.0}
        else:
            raise Exception("No captions available via YouTube API")
    
    async def _youtube_transcript_api_transcribe(self, video_id: str) -> tuple[List[TranscriptSegment], Dict[str, Any]]:
        """Use YouTube Transcript API (third-party)"""
        if not self.local_fetcher:
            raise Exception("Local fetcher not available")
        
        # Use existing implementation
        segments = self.local_fetcher.fetch_youtube_transcript(video_id)
        if segments:
            return segments, {"method": "youtube_transcript_api", "cost": 0.0}
        else:
            raise Exception("No transcript available via third-party API")
    
    async def _local_whisper_transcribe(self, video_id: str, video_metadata: Dict = None) -> tuple[List[TranscriptSegment], Dict[str, Any]]:
        """Use local RTX 5080 + Whisper for transcription"""
        if not self.local_fetcher:
            raise Exception("Local Whisper not available")
        
        # Use existing local implementation
        segments, method, metadata = self.local_fetcher.fetch_transcript(video_id)
        if segments:
            return segments, {
                "method": "local_whisper", 
                "cost": 0.0,
                "model": metadata.get("model", "unknown"),
                "quality": metadata.get("quality_assessment", {})
            }
        else:
            raise Exception(f"Local Whisper failed: {metadata.get('error', 'Unknown error')}")
    
    async def _openai_whisper_transcribe(self, video_id: str, video_metadata: Dict = None) -> tuple[List[TranscriptSegment], Dict[str, Any]]:
        """Use OpenAI Whisper API for production transcription"""
        if not self.openai_client:
            raise Exception("OpenAI client not initialized")
        
        # Check daily cost limit
        if self.daily_cost >= self.config.cost_limit_per_day:
            raise Exception(f"Daily cost limit reached: ${self.daily_cost:.2f}")
        
        try:
            # Download audio (reuse existing yt-dlp logic)
            audio_path = await self._download_audio(video_id)
            
            # Estimate cost (OpenAI charges $0.006 per minute)
            duration_minutes = video_metadata.get('duration_s', 600) / 60  # Default 10 min
            estimated_cost = duration_minutes * 0.006
            
            if self.daily_cost + estimated_cost > self.config.cost_limit_per_day:
                raise Exception(f"Would exceed daily cost limit: ${self.daily_cost + estimated_cost:.2f}")
            
            # Call OpenAI Whisper API
            with open(audio_path, 'rb') as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            
            # Parse response into TranscriptSegment format
            segments = self._parse_openai_response(response)
            
            # Update cost tracking
            actual_cost = len(response.segments) * 0.006 / 60  # Rough estimate
            self.daily_cost += actual_cost
            
            return segments, {
                "method": "openai_whisper",
                "cost": actual_cost,
                "model": "whisper-1",
                "duration": duration_minutes,
                "daily_cost_total": self.daily_cost
            }
            
        except Exception as e:
            logger.error(f"OpenAI Whisper API error: {e}")
            raise
    
    async def _download_audio(self, video_id: str) -> str:
        """Download audio using yt-dlp (reuse existing logic)"""
        if self.local_fetcher and hasattr(self.local_fetcher, 'downloader'):
            return self.local_fetcher.downloader.download_audio(video_id)
        else:
            raise Exception("Audio downloader not available")
    
    def _parse_openai_response(self, response) -> List[TranscriptSegment]:
        """Parse OpenAI Whisper API response into TranscriptSegment format"""
        segments = []
        
        for segment in response.segments:
            segments.append(TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text.strip()
            ))
        
        return segments
    
    def get_daily_cost(self) -> float:
        """Get current daily transcription cost"""
        return self.daily_cost
    
    def reset_daily_cost(self):
        """Reset daily cost counter (call this daily)"""
        self.daily_cost = 0.0

# Factory function for easy switching between environments
def create_transcript_service(environment: str = None) -> ProductionTranscriptService:
    """Create transcript service optimized for environment"""
    
    env = environment or os.getenv('ENVIRONMENT', 'local')
    
    if env == 'production':
        config = TranscriptionConfig(
            environment='production',
            preferred_method=TranscriptionMethod.OPENAI_WHISPER,
            fallback_methods=[
                TranscriptionMethod.YOUTUBE_API,
                TranscriptionMethod.YOUTUBE_TRANSCRIPT_API,
                TranscriptionMethod.OPENAI_WHISPER
            ],
            cost_limit_per_day=10.00
        )
    else:
        config = TranscriptionConfig(
            environment='local',
            preferred_method=TranscriptionMethod.LOCAL_WHISPER,
            fallback_methods=[
                TranscriptionMethod.YOUTUBE_API,
                TranscriptionMethod.YOUTUBE_TRANSCRIPT_API,
                TranscriptionMethod.LOCAL_WHISPER
            ]
        )
    
    return ProductionTranscriptService(config)

if __name__ == "__main__":
    # Test the service
    async def test_service():
        service = create_transcript_service('local')
        segments, method, metadata = await service.get_transcript('dQw4w9WgXcQ')
        print(f"Method: {method}, Segments: {len(segments)}, Cost: ${metadata.get('cost', 0):.2f}")
    
    asyncio.run(test_service())
