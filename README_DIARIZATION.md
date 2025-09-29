# Speaker Diarization and Voice Enrollment

This document explains the speaker diarization and voice enrollment system used in the Ask Dr. Chaffee project.

## Overview

The system uses a combination of:

1. **Pyannote.audio** for high-quality speaker diarization
2. **Voice enrollment** with centroid-based profiles for speaker identification
3. **Monologue fast-path** for optimized processing of solo content

## Voice Profiles

Voice profiles are stored in the `voices/` directory as JSON files. The system supports two formats:

### Centroid-Based Format (Recommended)

This format uses a single centroid vector that represents the speaker's voice characteristics. This is more efficient and accurate.

```json
{
  "name": "Chaffee",
  "centroid": [0.1, 0.2, ...],  // 192-dimensional vector
  "threshold": 0.62,
  "created_at": "2023-01-01T00:00:00"
}
```

### Embeddings-Based Format

This format stores multiple embedding vectors for the speaker.

```json
{
  "name": "Chaffee",
  "embeddings": [
    [0.1, 0.2, ...],  // 192-dimensional vector
    [0.3, 0.4, ...],
    ...
  ],
  "threshold": 0.62,
  "created_at": "2023-01-01T00:00:00"
}
```

## Configuration

Key environment variables:

- `HUGGINGFACE_HUB_TOKEN`: Required for pyannote.audio
- `DIARIZATION_MODEL`: Default is `pyannote/speaker-diarization-3.1`
- `MIN_SPEAKERS`: Optional minimum number of speakers
- `MAX_SPEAKERS`: Optional maximum number of speakers
- `CHAFFEE_MIN_SIM`: Minimum similarity threshold for Dr. Chaffee (default: 0.62)
- `GUEST_MIN_SIM`: Minimum similarity threshold for guests (default: 0.82)
- `ATTR_MARGIN`: Required margin between best and second-best match (default: 0.05)
- `ASSUME_MONOLOGUE`: Enable monologue fast-path optimization (default: true)

## Monologue Fast-Path

For solo content (Dr. Chaffee only), the system uses a fast-path that:

1. Extracts a few embeddings from the audio
2. Compares them with the Chaffee profile
3. If similarity is high enough, skips diarization and assigns all segments to Dr. Chaffee
4. Otherwise, falls back to the full pipeline with diarization

This provides a 3x speedup for solo content.

## Troubleshooting

If speaker identification is not working correctly:

1. Check that you have a valid HuggingFace token
2. Ensure the Chaffee voice profile is using the centroid-based format
3. Adjust the similarity thresholds if needed
4. For interviews, set `ASSUME_MONOLOGUE=false`

## Testing

Run the test script to verify diarization and speaker identification:

```bash
python test_diarization.py
```
