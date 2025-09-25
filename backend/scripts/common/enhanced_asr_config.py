#!/usr/bin/env python3
"""
Enhanced ASR Configuration with 12-factor app methodology
Supports environment variables with CLI overrides for all Whisper parameters
"""

import os
import logging
from typing import List, Optional, Union
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WhisperConfig:
    """Configuration for Whisper transcription with quality-first defaults"""
    
    # Model configuration
    model: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    
    # Inference parameters (quality-first)
    beam_size: int = 6
    chunk_length: int = 45
    vad_filter: bool = True
    language: str = "en"
    task: str = "transcribe"
    temperature: List[float] = None
    
    # Domain-specific prompt for medical/nutrition content
    initial_prompt: str = (
        "ketogenesis linoleic acid LDL statins seed oils DHA EPA taurine "
        "oxalates gout uric acid mTOR autoimmunity cholecystectomy"
    )
    
    # Quality control
    word_timestamps: bool = True
    return_segments: bool = True
    return_dict: bool = True
    
    def __post_init__(self):
        if self.temperature is None:
            self.temperature = [0.0, 0.2, 0.4]
    
    @classmethod
    def from_env(cls, **overrides) -> 'WhisperConfig':
        """Create configuration from environment variables with overrides"""
        config = cls()
        
        # Load from environment
        config.model = os.getenv('WHISPER_MODEL', config.model)
        config.device = os.getenv('WHISPER_DEVICE', config.device)
        config.compute_type = os.getenv('WHISPER_COMPUTE', config.compute_type)
        config.beam_size = int(os.getenv('WHISPER_BEAM', str(config.beam_size)))
        config.chunk_length = int(os.getenv('WHISPER_CHUNK', str(config.chunk_length)))
        config.vad_filter = os.getenv('WHISPER_VAD', str(config.vad_filter)).lower() == 'true'
        config.language = os.getenv('WHISPER_LANG', config.language)
        config.task = os.getenv('WHISPER_TASK', config.task)
        
        # Parse temperature array
        temp_str = os.getenv('WHISPER_TEMPS', '0.0,0.2,0.4')
        try:
            config.temperature = [float(t.strip()) for t in temp_str.split(',')]
        except ValueError:
            logger.warning(f"Invalid WHISPER_TEMPS format: {temp_str}, using defaults")
        
        # Domain prompt
        domain_prompt = os.getenv('DOMAIN_PROMPT')
        if domain_prompt:
            config.initial_prompt = domain_prompt
        
        # Apply CLI overrides
        for key, value in overrides.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)
        
        return config


@dataclass 
class QualityConfig:
    """Quality assurance and two-pass configuration"""
    
    # Low confidence detection thresholds
    low_conf_avg_logprob: float = -0.35
    low_conf_compression_ratio: float = 2.4
    
    # Two-pass retry settings
    enable_two_pass: bool = True
    retry_beam_size: int = 8
    retry_temperature: List[float] = None
    
    # Quality improvement thresholds
    min_improvement_logprob: float = 0.05
    min_improvement_compression: float = 0.1
    
    def __post_init__(self):
        if self.retry_temperature is None:
            self.retry_temperature = [0.0, 0.2, 0.4, 0.6]
    
    @classmethod
    def from_env(cls, **overrides) -> 'QualityConfig':
        """Create configuration from environment variables"""
        config = cls()
        
        config.low_conf_avg_logprob = float(os.getenv('QA_LOW_LOGPROB', str(config.low_conf_avg_logprob)))
        config.low_conf_compression_ratio = float(os.getenv('QA_LOW_COMPRESSION', str(config.low_conf_compression_ratio)))
        config.enable_two_pass = os.getenv('QA_TWO_PASS', 'true').lower() == 'true'
        config.retry_beam_size = int(os.getenv('QA_RETRY_BEAM', str(config.retry_beam_size)))
        
        # Parse retry temperature array
        retry_temp_str = os.getenv('QA_RETRY_TEMPS', '0.0,0.2,0.4,0.6')
        try:
            config.retry_temperature = [float(t.strip()) for t in retry_temp_str.split(',')]
        except ValueError:
            logger.warning(f"Invalid QA_RETRY_TEMPS format: {retry_temp_str}, using defaults")
        
        # Apply overrides
        for key, value in overrides.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)
        
        return config


@dataclass
class AlignmentConfig:
    """WhisperX alignment and diarization configuration"""
    
    # Word alignment
    enable_alignment: bool = True
    align_model: str = "WAV2VEC2_ASR_LARGE_LV60K_960H"
    
    # Speaker diarization
    enable_diarization: bool = False
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    min_speakers: Optional[int] = None
    max_speakers: Optional[int] = None
    
    @classmethod
    def from_env(cls, **overrides) -> 'AlignmentConfig':
        """Create configuration from environment variables"""
        config = cls()
        
        config.enable_alignment = os.getenv('ALIGN_WORDS', str(config.enable_alignment)).lower() == 'true'
        config.enable_diarization = os.getenv('DIARIZE', str(config.enable_diarization)).lower() == 'true'
        config.diarization_model = os.getenv('DIARIZE_MODEL', config.diarization_model)
        
        min_spk = os.getenv('MIN_SPEAKERS')
        if min_spk:
            config.min_speakers = int(min_spk)
        
        max_spk = os.getenv('MAX_SPEAKERS') 
        if max_spk:
            config.max_speakers = int(max_spk)
        
        # Apply overrides
        for key, value in overrides.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)
        
        return config


class EnhancedASRConfig:
    """
    Comprehensive ASR configuration with 12-factor methodology
    Maintains backward compatibility with existing config
    """
    
    def __init__(self, **overrides):
        # Whisper configuration
        self.whisper = WhisperConfig.from_env(**overrides)
        
        # Quality assurance
        self.quality = QualityConfig.from_env(**overrides)
        
        # Alignment and diarization
        self.alignment = AlignmentConfig.from_env(**overrides)
        
        # Existing speaker identification config (backward compatibility)
        self.chaffee_min_sim = float(overrides.get('chaffee_min_sim', os.getenv('CHAFFEE_MIN_SIM', '0.82')))
        self.guest_min_sim = float(overrides.get('guest_min_sim', os.getenv('GUEST_MIN_SIM', '0.82')))
        self.attr_margin = float(overrides.get('attr_margin', os.getenv('ATTR_MARGIN', '0.05')))
        self.overlap_bonus = float(os.getenv('OVERLAP_BONUS', '0.03'))
        
        # Processing options
        self.assume_monologue = os.getenv('ASSUME_MONOLOGUE', 'true').lower() == 'true'
        self.align_words = self.alignment.enable_alignment  # Bridge old API
        self.unknown_label = os.getenv('UNKNOWN_LABEL', 'Unknown')
        
        # Legacy model references (backward compatibility)
        self.whisper_model = self.whisper.model
        self.diarization_model = self.alignment.diarization_model
        self.voices_dir = os.getenv('VOICES_DIR', 'voices')
        
        # Guardrails
        self.min_speaker_duration = float(os.getenv('MIN_SPEAKER_DURATION', '3.0'))
        self.min_diarization_confidence = float(os.getenv('MIN_DIARIZATION_CONFIDENCE', '0.5'))
        
        # VRAM safety
        self.enable_fallback = os.getenv('ENABLE_FALLBACK', 'true').lower() == 'true'
        
        # Apply any direct overrides to maintain API compatibility
        for key, value in overrides.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)
    
    def get_fallback_models(self) -> List[str]:
        """Get ordered list of fallback models"""
        base_model = self.whisper.model
        
        # Define fallback hierarchy
        fallbacks = {
            'large-v3': ['large-v3-turbo', 'distil-large-v3', 'large-v2', 'medium.en'],
            'large-v3-turbo': ['distil-large-v3', 'large-v2', 'medium.en'],
            'distil-large-v3': ['large-v2', 'medium.en', 'small.en'],
            'large-v2': ['medium.en', 'small.en', 'base.en'],
            'medium.en': ['small.en', 'base.en'],
            'small.en': ['base.en'],
            'base.en': ['tiny.en']
        }
        
        return fallbacks.get(base_model, ['base.en'])
    
    def get_fallback_compute_types(self) -> List[str]:
        """Get ordered list of compute type fallbacks"""
        base_compute = self.whisper.compute_type
        
        # Define compute type fallbacks for CUDA OOM
        if base_compute == 'float16':
            return ['int8_float16', 'int8']
        elif base_compute == 'int8_float16':
            return ['int8']
        else:
            return []
    
    def log_config(self):
        """Log current configuration for debugging"""
        logger.info("=== Enhanced ASR Configuration ===")
        logger.info(f"Whisper Model: {self.whisper.model}")
        logger.info(f"Device: {self.whisper.device}")
        logger.info(f"Compute Type: {self.whisper.compute_type}")
        logger.info(f"Beam Size: {self.whisper.beam_size}")
        logger.info(f"Chunk Length: {self.whisper.chunk_length}")
        logger.info(f"VAD Filter: {self.whisper.vad_filter}")
        logger.info(f"Temperature: {self.whisper.temperature}")
        logger.info(f"Two-pass QA: {self.quality.enable_two_pass}")
        logger.info(f"Word Alignment: {self.alignment.enable_alignment}")
        logger.info(f"Diarization: {self.alignment.enable_diarization}")
        logger.info(f"Domain Prompt: {self.whisper.initial_prompt[:50]}...")
        
        # Speaker ID config
        logger.info(f"Chaffee Threshold: {self.chaffee_min_sim:.3f}")
        logger.info(f"Guest Threshold: {self.guest_min_sim:.3f}")
        logger.info(f"Attribution Margin: {self.attr_margin:.3f}")


# Model availability mapping for fallbacks
MODEL_AVAILABILITY = {
    'large-v3': True,
    'large-v3-turbo': True, 
    'distil-large-v3': True,
    'large-v2': True,
    'medium.en': True,
    'small.en': True,
    'base.en': True,
    'tiny.en': True
}

# Performance characteristics for model selection
MODEL_PERFORMANCE = {
    'large-v3': {'accuracy': 95, 'speed': 30, 'memory': 3000},
    'large-v3-turbo': {'accuracy': 93, 'speed': 45, 'memory': 2800},  
    'distil-large-v3': {'accuracy': 90, 'speed': 60, 'memory': 2000},
    'large-v2': {'accuracy': 92, 'speed': 35, 'memory': 2800},
    'medium.en': {'accuracy': 87, 'speed': 70, 'memory': 1500},
    'small.en': {'accuracy': 82, 'speed': 120, 'memory': 800},
    'base.en': {'accuracy': 75, 'speed': 180, 'memory': 500},
    'tiny.en': {'accuracy': 65, 'speed': 300, 'memory': 200}
}


def get_recommended_model(use_case: str = "quality", vram_gb: int = 16) -> str:
    """
    Get recommended model based on use case and available VRAM
    
    Args:
        use_case: "quality", "speed", "efficiency", or "realtime" 
        vram_gb: Available VRAM in GB
    
    Returns:
        Recommended model name
    """
    if use_case == "quality":
        return "large-v3" if vram_gb >= 4 else "medium.en"
    elif use_case == "speed":
        return "large-v3-turbo" if vram_gb >= 4 else "small.en"
    elif use_case == "efficiency":
        return "distil-large-v3" if vram_gb >= 3 else "base.en"
    elif use_case == "realtime":
        return "small.en" if vram_gb >= 1 else "tiny.en"
    else:
        return "large-v3"  # Default to quality
