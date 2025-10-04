#!/usr/bin/env python3
import os
from dotenv import load_dotenv
import whisperx
import torch

# Load .env file
load_dotenv()

# Get the token
token = os.getenv('HUGGINGFACE_HUB_TOKEN')
print(f"Token: {token[:5]}...")

try:
    # Set device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    # Load audio
    audio_file = "test.wav"  # Replace with a real audio file path
    
    # Create a test audio file if it doesn't exist
    if not os.path.exists(audio_file):
        import numpy as np
        import soundfile as sf
        print(f"Creating test audio file: {audio_file}")
        sample_rate = 16000
        duration = 5  # seconds
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz sine wave
        sf.write(audio_file, audio, sample_rate)
    
    # Load WhisperX model
    print("Loading WhisperX model...")
    model = whisperx.load_model("tiny", device)
    
    # Transcribe audio
    print("Transcribing audio...")
    result = model.transcribe(audio_file)
    
    # Align whisper output
    print("Aligning whisper output...")
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio_file, device)
    
    # Diarize with Pyannote
    print("Diarizing with Pyannote...")
    from pyannote.audio import Pipeline
    diarization_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token
    )
    
    # Get diarization result
    diarization = diarization_pipeline(audio_file)
    
    # Convert to whisperx format
    print("Converting diarization to whisperx format...")
    diarize_segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segment = {
            "start": turn.start,
            "end": turn.end,
            "speaker": speaker
        }
        diarize_segments.append(segment)
    
    # Assign speaker labels
    print("Assigning speaker labels...")
    result = whisperx.assign_word_speakers(diarize_segments, result)
    
    print("WhisperX diarization completed successfully!")
    print(f"Result: {result}")
    
except Exception as e:
    print(f"Error: {e}")
