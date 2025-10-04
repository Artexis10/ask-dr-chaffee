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
    # Try to login
    login(token=token)
    print("Login successful!")
    
    # Try to access the API
    api = HfApi()
    user_info = api.whoami()
    print(f"Logged in as: {user_info}")
    
    # Check if we can access the model
    model_info = api.model_info("pyannote/speaker-diarization-3.1")
    print(f"Model info: {model_info.id}")
    print("Access to model confirmed!")
    
except Exception as e:
    print(f"Error: {e}")
