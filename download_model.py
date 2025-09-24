#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from huggingface_hub import snapshot_download

# Load .env file
load_dotenv()

# Get the token
token = os.getenv('HUGGINGFACE_HUB_TOKEN')
print(f"Token: {token[:5]}...")

try:
    # Download the model
    print("Downloading model...")
    snapshot_download(
        repo_id="pyannote/speaker-diarization-3.1",
        token=token,
        local_dir="./pretrained_models/pyannote-speaker-diarization-3.1"
    )
    print("Model downloaded successfully!")
    
except Exception as e:
    print(f"Error: {e}")
