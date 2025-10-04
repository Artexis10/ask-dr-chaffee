#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from huggingface_hub import login, HfApi

# Load .env file
load_dotenv()

# Get the token
token = os.getenv('HUGGINGFACE_HUB_TOKEN')
print(f"Token: {token[:5]}...")

try:
    # Login to HuggingFace
    login(token=token)
    print("Login successful!")
    
    # Create API client
    api = HfApi()
    
    # Check if we can access the model info
    model_info = api.model_info("pyannote/speaker-diarization-3.1")
    print(f"Model ID: {model_info.id}")
    print(f"Model SHA: {model_info.sha}")
    print(f"Model tags: {model_info.tags}")
    print(f"Model pipeline tag: {model_info.pipeline_tag}")
    print("Model access confirmed!")
    
    # List model files
    print("\nModel files:")
    files = api.list_repo_files("pyannote/speaker-diarization-3.1")
    for file in files:
        print(f"- {file}")
    
except Exception as e:
    print(f"Error: {e}")
