# HuggingFace Model Setup

## Current Status

We're currently using the simple energy-based diarization method as a fallback because there's an issue accessing the HuggingFace pyannote/speaker-diarization-3.1 model.

## How to Fix

To use the HuggingFace pyannote/speaker-diarization-3.1 model, you need to:

1. Go to https://huggingface.co/pyannote/speaker-diarization-3.1
2. Log in with your HuggingFace account
3. Accept the user agreement to share your contact information
4. Go to https://huggingface.co/pyannote/speaker-diarization
5. Accept the user agreement for this model as well
6. Go to https://huggingface.co/pyannote/segmentation
7. Accept the user agreement for this model as well

After accepting all the agreements, update the `.env` file:

```ini
# HuggingFace Configuration
HUGGINGFACE_HUB_TOKEN=your_token_here
USE_SIMPLE_DIARIZATION=false
DIARIZE=true
```

## Troubleshooting

If you're still having issues accessing the model, try:

1. Checking that your HuggingFace token has the correct permissions
2. Ensuring you've accepted all the necessary user agreements
3. Checking your network connection
4. Clearing your HuggingFace cache: `rm -rf ~/.cache/huggingface`
5. Reinstalling pyannote.audio: `pip install --upgrade pyannote.audio`

## Alternative Approaches

If you can't get the HuggingFace model working, you can:

1. Continue using the simple energy-based diarization (current approach)
2. Use WhisperX's built-in diarization capabilities
3. Use a different diarization library like resemblyzer (requires C++ build tools)
