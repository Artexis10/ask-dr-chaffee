# Voice Profiles Directory

This directory stores voice profile files for speaker identification.

## Usage

Voice profiles are created using the enrollment command:

```bash
python scripts/asr_cli.py enroll --name Chaffee --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

## File Format

Each voice profile is stored as a JSON file with the speaker's name (lowercase) as the filename:

- `chaffee.json` - Dr. Chaffee's voice profile
- `guest1.json` - Optional guest voice profile

## Structure

Each profile contains:
- Voice embeddings (ECAPA-TDNN)
- Centroid vector (average embedding)
- Metadata (creation date, duration, etc.)
- Audio sources used for enrollment
