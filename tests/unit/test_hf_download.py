#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download, login

# Load .env file
load_dotenv()

# Get the token
token = os.getenv('HUGGINGFACE_HUB_TOKEN')
print(f"Token: {token[:5]}...")

try:
    # Login to HuggingFace
    login(token=token)
    print("Login successful!")
    
    # Try to download a public model
    print("Downloading a public model...")
    file_path = hf_hub_download(
        repo_id="facebook/wav2vec2-base-960h",
        filename="pytorch_model.bin",
        cache_dir="./pretrained_models"
    )
    print(f"Downloaded to: {file_path}")
    
except Exception as e:
    print(f"Error: {e}")
