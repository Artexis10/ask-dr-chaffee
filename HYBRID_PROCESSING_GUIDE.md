# Hybrid YouTube Processing System

## Overview

This system provides intelligent routing between local GPU processing and cloud API processing to optimize for quality, cost, and efficiency.

## Architecture

### Processing Methods

1. **Local GPU Processing** (`local_gpu`)
   - Uses your RTX 5080 with parallel workers
   - Superior quality with faster-whisper
   - FREE processing (electricity only)
   - Best for: Backlog processing, high-quality transcription

2. **Cloud API Processing** (`api_whisper`) 
   - Uses OpenAI Whisper API
   - Cost: $0.006/minute (~$2-5/month for daily updates)
   - No GPU infrastructure needed
   - Best for: Daily automation, small batches

3. **Auto Mode** (`auto`)
   - Intelligently chooses based on context
   - Considers video count, costs, availability
   - Optimizes for efficiency and cost

## Usage Examples

### Daily Production Cron (Recommended)
```bash
# Cost-effective daily updates
python backend/scripts/cloud_daily_ingestion.py --max-cost 5.0 --limit 10
```

### Local Bulk Processing
```bash
# Process backlog with your RTX 5080
python backend/scripts/parallel_ingestion_orchestrator.py --workers 14 --limit 100
```

### Smart Hybrid Processing
```bash
# Auto-decide based on context
python backend/scripts/hybrid_orchestrator.py --mode auto --limit 20 --max-cost 8.0
```

## Cost Analysis

### Local GPU Processing
- **Hardware**: RTX 5080 (already owned)
- **Operating Cost**: ~$0.50/day electricity for 8 hours
- **Scalability**: Limited to your local machine
- **Quality**: Superior (local faster-whisper)

### Cloud API Processing  
- **Dr. Chaffee uploads**: ~2-3 videos/week (6-9 hours/month)
- **API Cost**: 6 hours × 60 min × $0.006 = ~$2.16/month
- **Scalability**: Unlimited
- **Quality**: Excellent (OpenAI Whisper-1)

### Cloud GPU Alternative (Not Recommended)
- **AWS p3.2xlarge**: $3.06/hour × 24 × 30 = $2,203/month
- **Conclusion**: 1000x more expensive than API approach

## Setup Instructions

### 1. Environment Variables
```bash
# Required
DATABASE_URL="postgresql://user:pass@host:5432/db"
OPENAI_API_KEY="sk-your-api-key"
YOUTUBE_API_KEY="your-youtube-api-key"

# Optional
SKIP_MEMBERS_ONLY="true"
YOUTUBE_COOKIES_FILE="/path/to/cookies.txt"
```

### 2. Database Schema Updates
```sql
-- Run the schema update
psql $DATABASE_URL -f database_schema_update.sql
```

### 3. Test Individual Components
```bash
# Test cloud API worker
python backend/scripts/cloud_whisper_worker.py VIDEO_ID "Video Title"

# Test local GPU worker  
python backend/scripts/parallel_whisper_worker_fixed.py 0 VIDEO_ID "Video Title"

# Test hybrid orchestrator
python backend/scripts/hybrid_orchestrator.py --dry-run --limit 5
```

## Production Deployment

### Cron Job Setup
```bash
# Install cron configuration
cp cron_setup_examples.sh /tmp/
chmod +x /tmp/cron_setup_examples.sh
# Edit paths in the file, then:
crontab /tmp/youtube_ingestion_crontab
```

### Monitoring
```sql
-- Check processing methods
SELECT processing_method, COUNT(*) 
FROM ingest_state 
GROUP BY processing_method;

-- Monthly cost summary
SELECT * FROM processing_cost_summary 
WHERE processing_date >= DATE_TRUNC('month', NOW());
```

## Quality Comparison

### YouTube Auto-Generated vs Whisper

**Medical Accuracy Example:**
- YouTube: "the carnival diet helps with auto immune issues"
- Whisper: "The carnivore diet helps with autoimmune issues."

**Technical Terminology:**
- YouTube: "electric tights and fits states"  
- Whisper: "lectins and phytates"

**Punctuation & Context:**
- YouTube: "when you eat carbs you go into key toe sis"
- Whisper: "When you eat carbs, you go into ketosis."

## Best Practices

### For Production
1. **Use cloud API for daily automation** (reliable, cost-effective)
2. **Use local GPU for backlog processing** (superior quality, free)
3. **Set cost limits** to prevent API overruns
4. **Monitor processing quality** with database views
5. **Use hybrid auto mode** for optimal routing

### For Development
1. **Test with small batches first**
2. **Use dry-run flags** to preview processing
3. **Monitor GPU utilization** during local processing
4. **Check cost estimates** before large API runs

## Troubleshooting

### Common Issues

**Local GPU Issues:**
- Check NVIDIA-SMI availability
- Verify CUDA installation
- Monitor VRAM usage (14-16GB for 14 workers)
- Check for stuck processes

**API Issues:**
- Verify OpenAI API key validity
- Check account credits/billing
- Monitor rate limits (50 requests/minute)
- Validate file size limits (25MB)

**Database Issues:**
- Check connection strings
- Verify schema updates applied
- Monitor connection pool limits
- Check for constraint violations

### Performance Optimization

**Local GPU:**
```bash
# Optimal workers for RTX 5080
python parallel_ingestion_orchestrator.py --workers 14

# Monitor GPU utilization
watch -n 1 nvidia-smi
```

**Cloud API:**
```bash
# Batch processing for efficiency
python cloud_daily_ingestion.py --limit 10 --max-cost 5.0

# Monitor costs
python -c "
import os, psycopg2
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cursor = conn.cursor()
cursor.execute('SELECT SUM(processing_cost_usd) FROM ingest_state WHERE updated_at::date = CURRENT_DATE')
print(f'Today cost: ${cursor.fetchone()[0] or 0:.4f}')
"
```

## Future Enhancements

1. **Dynamic Cost Optimization**: Adjust processing based on API pricing changes
2. **Quality Scoring**: Compare transcript quality metrics automatically  
3. **Multi-Cloud Support**: Add Azure, Google Cloud Whisper alternatives
4. **Scheduling Intelligence**: Process during off-peak hours for cost savings
5. **Content Prioritization**: Process high-value content with local GPU first
