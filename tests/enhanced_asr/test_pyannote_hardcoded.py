#!/usr/bin/env python3
import os
import torch

# Get token from environment variable
token = os.getenv("HUGGINGFACE_TOKEN")
if not token:
    raise ValueError("HUGGINGFACE_TOKEN environment variable not set")
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
    except TypeError:
        # Newer versions use 'token' instead of 'use_auth_token'
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token
        )
    
    print("Pipeline created successfully!")
    print(f"Pipeline type: {type(pipeline)}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
