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
    # Try to use the segmentation model instead
    from pyannote.audio import Pipeline
    
    print("Creating segmentation pipeline...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/segmentation-3.0",
        use_auth_token=token
    )
    
    print(f"Pipeline created successfully: {type(pipeline)}")
    
except Exception as e:
    print(f"Error: {e}")
