# Audio Storage Cleanup Guide

## Overview

Audio files can consume significant disk space. This guide provides multiple ways to manage and clean up audio storage.

## Option 1: Automatic Cleanup (Recommended)

Add to your `.env` file:
```bash
CLEANUP_AUDIO_AFTER_PROCESSING=true
```

This will automatically delete audio files after embeddings are extracted during profile creation.

**Pros:**
- Automatic, no manual intervention needed
- Keeps disk usage minimal
- Safe - only deletes after successful processing

**Cons:**
- Cannot re-process audio without re-downloading
- Useful for one-time profile creation

## Option 2: Manual Cleanup Script

Use the `cleanup_audio.py` script for more control.

### Show Statistics
```bash
python cleanup_audio.py stats
```

### Delete All Audio Files
```bash
# Preview what would be deleted
python cleanup_audio.py all --dry-run

# Actually delete (with confirmation)
python cleanup_audio.py all

# Delete without confirmation
python cleanup_audio.py all --force
```

### Delete Files Older Than N Days
```bash
# Preview
python cleanup_audio.py older-than --days 7 --dry-run

# Delete files older than 7 days
python cleanup_audio.py older-than --days 7
```

### Delete N Largest Files
```bash
# Preview
python cleanup_audio.py largest --count 10 --dry-run

# Delete 10 largest files
python cleanup_audio.py largest --count 10
```

### Custom Audio Directory
```bash
python cleanup_audio.py stats --audio-dir /path/to/audio
```

## Option 3: Manual Cleanup

### Windows PowerShell
```powershell
# Show total size
Get-ChildItem audio_storage -Recurse | Measure-Object -Property Length -Sum

# Delete all .wav files
Remove-Item audio_storage\*.wav

# Delete files older than 7 days
Get-ChildItem audio_storage -Recurse | Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-7)} | Remove-Item

# Delete largest files
Get-ChildItem audio_storage -Recurse | Sort-Object Length -Descending | Select-Object -First 10 | Remove-Item
```

### Linux/Mac
```bash
# Show total size
du -sh audio_storage

# Delete all .wav files
rm audio_storage/*.wav

# Delete files older than 7 days
find audio_storage -type f -mtime +7 -delete

# Delete largest files
find audio_storage -type f -exec ls -lh {} \; | sort -k5 -hr | head -10 | awk '{print $9}' | xargs rm
```

## Recommendations

### For Profile Creation (One-Time)
Set `CLEANUP_AUDIO_AFTER_PROCESSING=true` in `.env` to automatically clean up after processing.

### For Ongoing Ingestion
Keep audio files if you plan to:
- Re-process with different settings
- Update profiles incrementally
- Debug issues

Use the cleanup script periodically:
```bash
# Weekly cleanup of files older than 7 days
python cleanup_audio.py older-than --days 7
```

### For Development
Keep `CLEANUP_AUDIO_AFTER_PROCESSING=false` and manually clean up when needed:
```bash
python cleanup_audio.py stats  # Check what's using space
python cleanup_audio.py largest --count 20  # Remove biggest files
```

## Disk Space Estimates

Typical audio file sizes:
- **WAV (uncompressed)**: ~10MB per minute
- **MP3 (compressed)**: ~1MB per minute
- **1 hour video**: ~600MB (WAV) or ~60MB (MP3)

For 20 videos averaging 1 hour each:
- **WAV**: ~12GB
- **MP3**: ~1.2GB

## Safety Tips

1. **Always use `--dry-run` first** to preview what will be deleted
2. **Backup important audio files** before cleanup
3. **Check profile was created successfully** before deleting source audio
4. **Keep at least one copy** of seed video audio files for profile updates

## Troubleshooting

### "Permission denied" errors
Run with administrator/sudo privileges or check file permissions.

### Files not being deleted
- Check if files are in use by another process
- Verify the audio directory path is correct
- Check file permissions

### Disk space not freed immediately
On some systems, disk space may not show as freed until the recycle bin/trash is emptied.
