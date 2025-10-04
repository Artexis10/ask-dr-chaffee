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
    # Try to use an older version of the model
    from pyannote.audio import Pipeline
    
    print("Creating pipeline with version 2...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization@2.1",
        use_auth_token=token
    )
    
    print(f"Pipeline created successfully: {type(pipeline)}")
    
except Exception as e:
    print(f"Error: {e}")
