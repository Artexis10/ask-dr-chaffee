#!/usr/bin/env python3
import os
from dotenv import load_dotenv
import torch

# Load .env file
load_dotenv()

# Get the token
token = os.getenv('HUGGINGFACE_HUB_TOKEN')
print(f"Token: {token[:5]}...")

try:
    # Import pyannote.audio
    from pyannote.audio import Pipeline
    
    # Create the pipeline using the correct v3.1 name
    print("Creating pipeline...")
    
    # Try both token parameter names depending on pyannote.audio version
    # Start with CPU as GPT-5 suggested
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token
        )
        pipeline.to(torch.device("cpu"))  # Force CPU initially
        print("Pipeline loaded on CPU")
    except TypeError:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token
        )
        pipeline.to(torch.device("cpu"))  # Force CPU initially
        print("Pipeline loaded on CPU")
    
    print(f"Pipeline created successfully: {type(pipeline)}")
    
    # Test with a simple audio file if available
    print("Pipeline loaded successfully! Ready for diarization.")
    
except Exception as e:
    print(f"Error: {e}")
