# YouTube Captions Policy - Speaker ID is MANDATORY

## Critical Change: YouTube Captions Now OPT-IN

### Why This Change Was Made

**YouTube captions bypass our sophisticated speaker identification system**, which is a CORE REQUIREMENT for Dr. Chaffee content. This creates critical issues:

1. **No speaker attribution** - Cannot distinguish Chaffee from guests
2. **Risk of misattribution** - Guest statements could be attributed to Dr. Chaffee
3. **Bypasses voice profile matching** - Ignores our Chaffee voice profile
4. **No diarization** - Cannot identify speaker changes
5. **No segment optimization** - Segments remain tiny (50-100 chars vs 1100-1400)
6. **No embeddings** - Cannot perform semantic search

### Previous Behavior (BROKEN)

```python
# OLD: YouTube captions used by default
if not force_whisper:
    youtube_segments = self.fetch_youtube_transcript(video_id)
    if youtube_segments:
        return youtube_segments  # ❌ NO SPEAKER ID!
```

**Result:** 99.6% of segments had NULL speaker labels and no embeddings

### New Behavior (CORRECT)

```python
# NEW: Speaker ID is MANDATORY when enabled
if self.enable_speaker_id:
    force_enhanced_asr = True  # ✅ Force Enhanced ASR
    
# YouTube captions are OPT-IN only
if allow_youtube_captions and not self.enable_speaker_id:
    # Only allowed if speaker ID is explicitly disabled
    youtube_segments = self.fetch_youtube_transcript(video_id)
```

## Configuration

### Default (Recommended)

```bash
# Speaker ID is MANDATORY (default)
ENABLE_SPEAKER_ID=true

# Run ingestion - Enhanced ASR is automatically used
python backend\scripts\ingest_youtube_enhanced.py \
  --source yt-dlp \
  --limit 50 \
  --skip-shorts \
  --voices-dir .\voices
```

**Result:**
- ✅ Enhanced ASR with speaker identification
- ✅ All segments labeled ('Chaffee' or 'GUEST')
- ✅ Segment optimization (1100-1400 chars)
- ✅ 1536-dim embeddings generated
- ✅ GPU fully utilized

### Allow YouTube Captions (NOT RECOMMENDED)

```bash
# ONLY use if you explicitly want to bypass speaker ID
python backend\scripts\ingest_youtube_enhanced.py \
  --source yt-dlp \
  --limit 50 \
  --allow-youtube-captions  # ⚠️  WARNING: Bypasses speaker ID
```

**Result:**
- ❌ No speaker identification
- ❌ NULL speaker labels
- ❌ Tiny segments (50-100 chars)
- ❌ No embeddings
- ❌ Unusable for RAG

## Code Changes

### 1. Enhanced Transcript Fetcher

**File:** `backend/scripts/common/enhanced_transcript_fetch.py`

```python
def fetch_transcript_with_speaker_id(
    self,
    video_id_or_path: str,
    allow_youtube_captions: bool = False  # NEW: OPT-IN only
):
    """
    CRITICAL: This pipeline requires speaker identification.
    YouTube captions are DISABLED by default because they:
    - Bypass speaker diarization
    - Bypass Chaffee voice profile matching
    - Cannot distinguish between Chaffee and guests
    - Risk misattributing guest statements to Dr. Chaffee
    """
    
    # MANDATORY: Speaker identification is required
    if self.enable_speaker_id:
        force_enhanced_asr = True  # Override
    
    # YouTube captions are OPT-IN only
    if allow_youtube_captions and not self.enable_speaker_id:
        logger.warning("⚠️  YouTube captions allowed - NO SPEAKER ID")
        # ... use YouTube captions
    else:
        # Use Enhanced ASR with speaker ID
```

### 2. Ingestion Config

**File:** `backend/scripts/ingest_youtube_enhanced.py`

```python
@dataclass
class IngestionConfig:
    force_whisper: bool = False
    allow_youtube_captions: bool = False  # NEW: Default False
    enable_speaker_id: bool = True  # MANDATORY
```

### 3. Command Line Argument

```python
parser.add_argument('--allow-youtube-captions', action='store_true',
                   help='⚠️  ALLOW YouTube captions (NOT RECOMMENDED - bypasses speaker ID)')
```

## Impact on Data Quality

### Before Fix (YouTube Captions)

```sql
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN speaker_label IS NULL THEN 1 END) as null_labels,
    COUNT(CASE WHEN embedding IS NULL THEN 1 END) as no_embeddings,
    AVG(LENGTH(text)) as avg_chars
FROM segments;

-- Results:
-- total: 44,328
-- null_labels: 44,156 (99.6%)
-- no_embeddings: 44,156 (99.6%)
-- avg_chars: 54
```

### After Fix (Enhanced ASR)

```sql
-- Expected results:
-- total: ~4,000 (optimized)
-- null_labels: 0 (0%)
-- no_embeddings: 0 (0%)
-- avg_chars: 1200
```

## Migration Steps

### 1. Clear Broken Data

```bash
python -c "import psycopg2; import os; from dotenv import load_dotenv; load_dotenv(); conn = psycopg2.connect(os.getenv('DATABASE_URL')); cur = conn.cursor(); cur.execute('TRUNCATE TABLE segments CASCADE'); cur.execute('TRUNCATE TABLE sources CASCADE'); conn.commit(); print('Cleared')"
```

### 2. Verify Configuration

```bash
# Check .env
cat .env | grep ENABLE_SPEAKER_ID
# Should show: ENABLE_SPEAKER_ID=true

# Check voice profile exists
ls voices/chaffee.json
```

### 3. Run Ingestion (Correct Way)

```bash
# NO --allow-youtube-captions flag
python backend\scripts\ingest_youtube_enhanced.py \
  --source yt-dlp \
  --limit 50 \
  --skip-shorts \
  --voices-dir .\voices \
  --channel-url "https://www.youtube.com/@anthonychaffeemd"
```

### 4. Verify Results

```sql
SELECT 
    metadata->>'transcript_method' as method,
    COUNT(*) as videos,
    AVG((SELECT COUNT(*) FROM segments WHERE video_id = source_id)) as avg_segments,
    AVG((SELECT AVG(LENGTH(text)) FROM segments WHERE video_id = source_id)) as avg_chars
FROM sources
GROUP BY 1;

-- Should show:
-- method: enhanced_asr or enhanced_asr_monologue
-- avg_segments: ~80-100 per video
-- avg_chars: 1000-1400
```

## Documentation Updates

### README.md

Added warning about YouTube captions:

```markdown
⚠️  **IMPORTANT:** YouTube captions are DISABLED by default because they bypass
speaker identification. This is critical for accurate attribution of statements
to Dr. Chaffee vs guests. Only use `--allow-youtube-captions` if you explicitly
want to bypass speaker ID (NOT RECOMMENDED).
```

### Help Text

```bash
python backend\scripts\ingest_youtube_enhanced.py --help

# Shows:
--allow-youtube-captions
    ⚠️  ALLOW YouTube captions (NOT RECOMMENDED - bypasses speaker identification)
```

## Summary

**Key Changes:**
1. ✅ YouTube captions are now OPT-IN (require explicit flag)
2. ✅ Enhanced ASR is MANDATORY when speaker ID is enabled
3. ✅ Clear warnings when YouTube captions are used
4. ✅ Fail-hard if Enhanced ASR unavailable when speaker ID required
5. ✅ Comprehensive documentation of the policy

**Impact:**
- Prevents 99.6% data quality issues
- Ensures accurate speaker attribution
- Protects against misattribution of guest statements
- Maintains integrity of Dr. Chaffee content database

**Migration Required:**
- Clear existing broken data (44k segments with NULL labels)
- Re-run ingestion without `--allow-youtube-captions` flag
- Verify all segments have speaker labels and embeddings
