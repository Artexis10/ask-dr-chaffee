#!/usr/bin/env python3
import os
import torch
from dotenv import load_dotenv
from huggingface_hub import login, snapshot_download, hf_hub_download

# Load .env file
load_dotenv()

# Get the token
token = os.getenv('HUGGINGFACE_HUB_TOKEN')
print(f"Token: {token[:5]}...")

try:
    # Login to HuggingFace
    login(token=token)
    print("Login successful!")
    
    # Create cache directory
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pretrained_models")
    os.makedirs(cache_dir, exist_ok=True)
    print(f"Cache directory: {cache_dir}")
    
    # Download the model configuration
    print("Downloading model configuration...")
    config_path = hf_hub_download(
        repo_id="pyannote/speaker-diarization-3.1",
        filename="config.yaml",
        token=token,
        cache_dir=cache_dir
    )
    print(f"Config downloaded to: {config_path}")
    
    # Now try to import and use the pipeline
    print("Importing pyannote.audio...")
    from pyannote.audio import Pipeline
    
    print("Creating pipeline...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token,
        cache_dir=cache_dir
    )
    
    print(f"Pipeline created successfully: {type(pipeline)}")
    
except Exception as e:
    print(f"Error: {e}")
