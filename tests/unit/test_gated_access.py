#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from huggingface_hub import HfApi, login

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
    
    # Test access to both required gated models
    models_to_check = [
        "pyannote/segmentation-3.0",
        "pyannote/speaker-diarization-3.1"
    ]
    
    for model_name in models_to_check:
        try:
            print(f"\nChecking access to {model_name}...")
            model_info = api.model_info(model_name, token=token)
            print(f"[SUCCESS] Access granted to {model_name}")
            print(f"   Model ID: {model_info.id}")
            print(f"   Gated: {model_info.gated}")
        except Exception as e:
            print(f"[FAILED] Cannot access {model_name}: {e}")
    
except Exception as e:
    print(f"Error: {e}")
