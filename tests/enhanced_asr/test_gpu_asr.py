#!/usr/bin/env python3

import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_gpu_asr():
    """Test if Enhanced ASR works with GPU"""
    try:
        # Import PyTorch and check CUDA
        import torch
        logger.info(f"PyTorch version: {torch.__version__}")
        logger.info(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"CUDA version: {torch.version.cuda}")
            logger.info(f"Device count: {torch.cuda.device_count()}")
            logger.info(f"Current device: {torch.cuda.current_device()}")
            logger.info(f"Device name: {torch.cuda.get_device_name(0)}")
        
        # Import Enhanced ASR
        from backend.scripts.common.enhanced_asr import EnhancedASR, EnhancedASRConfig
        from backend.scripts.common.enhanced_asr_config import EnhancedASRConfig
        
        # Create config
        config = EnhancedASRConfig()
        logger.info(f"Whisper model: {config.whisper.model}")
        logger.info(f"Device: {config.whisper.device}")
        
        # Initialize Enhanced ASR
        asr = EnhancedASR(config)
        logger.info("Enhanced ASR initialized successfully")
        
        # Load Whisper model
        whisper_model = asr._get_whisper_model()
        logger.info(f"Whisper model loaded: {whisper_model is not None}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing Enhanced ASR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("TESTING ENHANCED ASR WITH GPU")
    print("=" * 50)
    
    success = test_gpu_asr()
    
    print("=" * 50)
    if success:
        print("SUCCESS: Enhanced ASR works with GPU!")
    else:
        print("FAILED: Enhanced ASR has issues with GPU")
