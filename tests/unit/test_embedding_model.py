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
    # Try to use the embedding model instead
    from pyannote.audio import Inference
    
    print("Creating embedding model...")
    embedding_model = Inference(
        "pyannote/embedding",
        use_auth_token=token
    )
    
    print(f"Embedding model created successfully: {type(embedding_model)}")
    
except Exception as e:
    print(f"Error: {e}")
