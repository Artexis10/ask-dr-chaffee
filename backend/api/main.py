#!/usr/bin/env python3
"""
FastAPI main application for Ask Dr. Chaffee
Multi-source transcript processing with admin interface
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncio
import zipfile
import io
import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# Import our existing processors
import sys
backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(backend_path)
from scripts.process_srt_files import SRTProcessor
from scripts.common.database_upsert import DatabaseUpserter
from scripts.common.transcript_common import TranscriptSegment

app = FastAPI(
    title="Ask Dr. Chaffee API",
    description="Multi-source transcript processing and LLM search",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-secret-key")

# Background job tracking
processing_jobs: Dict[str, Dict[str, Any]] = {}

class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    total_files: int
    processed_files: int
    failed_files: int
    current_file: Optional[str] = None
    errors: List[str] = []
    created_at: datetime
    completed_at: Optional[datetime] = None

class UploadRequest(BaseModel):
    source_type: str  # youtube_takeout, zoom, manual, other
    description: Optional[str] = None

# Authentication
async def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return credentials.credentials

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/jobs", dependencies=[Depends(verify_admin_token)])
async def list_jobs():
    """List all processing jobs"""
    return {"jobs": list(processing_jobs.values())}

@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a specific job (no auth required for status checks)"""
    if job_id not in processing_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return processing_jobs[job_id]

@app.post("/api/upload/youtube-takeout", dependencies=[Depends(verify_admin_token)])
async def upload_youtube_takeout(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    description: Optional[str] = None
):
    """Upload and process Google Takeout ZIP with YouTube captions"""
    
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")
    
    # Create job
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "pending",
        "source_type": "youtube_takeout",
        "total_files": 0,
        "processed_files": 0,
        "failed_files": 0,
        "current_file": None,
        "errors": [],
        "created_at": datetime.now(),
        "completed_at": None,
        "description": description or f"YouTube Takeout upload: {file.filename}"
    }
    processing_jobs[job_id] = job
    
    # Process in background
    background_tasks.add_task(process_youtube_takeout, job_id, file)
    
    return {"job_id": job_id, "message": "Upload started", "status": "pending"}

@app.post("/api/upload/zoom-transcripts", dependencies=[Depends(verify_admin_token)])
async def upload_zoom_transcripts(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    description: Optional[str] = None
):
    """Upload and process Zoom transcript files (VTT, SRT, or TXT)"""
    
    # Validate file types
    allowed_extensions = {'.vtt', '.srt', '.txt'}
    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"File {file.filename} has unsupported extension. Allowed: {allowed_extensions}"
            )
    
    # Create job
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "pending",
        "source_type": "zoom",
        "total_files": len(files),
        "processed_files": 0,
        "failed_files": 0,
        "current_file": None,
        "errors": [],
        "created_at": datetime.now(),
        "completed_at": None,
        "description": description or f"Zoom transcripts upload: {len(files)} files"
    }
    processing_jobs[job_id] = job
    
    # Process in background
    background_tasks.add_task(process_zoom_transcripts, job_id, files)
    
    return {"job_id": job_id, "message": "Upload started", "status": "pending"}

@app.post("/api/upload/manual-transcripts", dependencies=[Depends(verify_admin_token)])
async def upload_manual_transcripts(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    source_type: str = "manual",
    description: Optional[str] = None
):
    """Upload and process manual transcript files from any source"""
    
    # Create job
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "pending",
        "source_type": source_type,
        "total_files": len(files),
        "processed_files": 0,
        "failed_files": 0,
        "current_file": None,
        "errors": [],
        "created_at": datetime.now(),
        "completed_at": None,
        "description": description or f"Manual transcripts upload: {len(files)} files"
    }
    processing_jobs[job_id] = job
    
    # Process in background
    background_tasks.add_task(process_manual_transcripts, job_id, files, source_type)
    
    return {"job_id": job_id, "message": "Upload started", "status": "pending"}

@app.post("/api/sync/new-videos", dependencies=[Depends(verify_admin_token)])
async def sync_new_videos(
    background_tasks: BackgroundTasks,
    limit: int = 10,
    use_proxy: bool = True
):
    """Manually trigger sync of new YouTube videos"""
    
    # Create job
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "status": "pending",
        "source_type": "youtube_sync",
        "total_files": 0,  # Will be updated when we discover videos
        "processed_files": 0,
        "failed_files": 0,
        "current_file": None,
        "errors": [],
        "created_at": datetime.now(),
        "completed_at": None,
        "description": f"Sync new YouTube videos (limit: {limit})"
    }
    processing_jobs[job_id] = job
    
    # Process in background
    background_tasks.add_task(sync_youtube_videos, job_id, limit, use_proxy)
    
    return {"job_id": job_id, "message": "Sync started", "status": "pending"}

# Background processing functions

async def process_youtube_takeout(job_id: str, file: UploadFile):
    """Process YouTube Takeout ZIP file"""
    job = processing_jobs[job_id]
    job["status"] = "processing"
    
    try:
        # Read ZIP file
        content = await file.read()
        
        with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
            # Find SRT files
            srt_files = [f for f in zip_file.namelist() if f.endswith('.srt')]
            job["total_files"] = len(srt_files)
            
            if not srt_files:
                raise Exception("No SRT files found in ZIP archive")
            
            # Initialize processor
            processor = SRTProcessor()
            
            # Process each SRT file
            for srt_path in srt_files:
                job["current_file"] = srt_path
                
                try:
                    # Extract and process SRT content
                    srt_content = zip_file.read(srt_path).decode('utf-8')
                    
                    # Create temporary file
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as temp_file:
                        temp_file.write(srt_content)
                        temp_path = Path(temp_file.name)
                    
                    # Process SRT file
                    success = processor.process_srt_file(temp_path)
                    
                    # Cleanup
                    temp_path.unlink()
                    
                    if success:
                        job["processed_files"] += 1
                    else:
                        job["failed_files"] += 1
                        job["errors"].append(f"Failed to process {srt_path}")
                        
                except Exception as e:
                    job["failed_files"] += 1
                    job["errors"].append(f"Error processing {srt_path}: {str(e)}")
        
        job["status"] = "completed"
        job["completed_at"] = datetime.now()
        
    except Exception as e:
        job["status"] = "failed"
        job["errors"].append(f"Job failed: {str(e)}")
        job["completed_at"] = datetime.now()

async def process_zoom_transcripts(job_id: str, files: List[UploadFile]):
    """Process Zoom transcript files"""
    job = processing_jobs[job_id]
    job["status"] = "processing"
    
    try:
        processor = SRTProcessor()
        
        for file in files:
            job["current_file"] = file.filename
            
            try:
                content = await file.read()
                
                # Create temporary file
                import tempfile
                suffix = Path(file.filename).suffix
                with tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, delete=False) as temp_file:
                    temp_file.write(content)
                    temp_path = Path(temp_file.name)
                
                # Process based on file type
                if suffix.lower() == '.srt':
                    success = processor.process_srt_file(temp_path)
                elif suffix.lower() in ['.vtt', '.txt']:
                    # Convert to SRT format first, then process
                    success = process_zoom_vtt_or_txt(temp_path, processor)
                else:
                    success = False
                
                # Cleanup
                temp_path.unlink()
                
                if success:
                    job["processed_files"] += 1
                else:
                    job["failed_files"] += 1
                    job["errors"].append(f"Failed to process {file.filename}")
                    
            except Exception as e:
                job["failed_files"] += 1
                job["errors"].append(f"Error processing {file.filename}: {str(e)}")
        
        job["status"] = "completed"
        job["completed_at"] = datetime.now()
        
    except Exception as e:
        job["status"] = "failed"
        job["errors"].append(f"Job failed: {str(e)}")
        job["completed_at"] = datetime.now()

async def process_manual_transcripts(job_id: str, files: List[UploadFile], source_type: str):
    """Process manual transcript files"""
    # Similar to Zoom processing but with different source type
    job = processing_jobs[job_id]
    job["status"] = "processing"
    
    try:
        processor = SRTProcessor()
        
        for file in files:
            job["current_file"] = file.filename
            
            try:
                content = await file.read()
                
                # Create temporary file and process
                import tempfile
                suffix = Path(file.filename).suffix
                with tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, delete=False) as temp_file:
                    temp_file.write(content)
                    temp_path = Path(temp_file.name)
                
                # Process file (customize based on source_type if needed)
                success = processor.process_srt_file(temp_path)
                temp_path.unlink()
                
                if success:
                    job["processed_files"] += 1
                else:
                    job["failed_files"] += 1
                    job["errors"].append(f"Failed to process {file.filename}")
                    
            except Exception as e:
                job["failed_files"] += 1
                job["errors"].append(f"Error processing {file.filename}: {str(e)}")
        
        job["status"] = "completed" 
        job["completed_at"] = datetime.now()
        
    except Exception as e:
        job["status"] = "failed"
        job["errors"].append(f"Job failed: {str(e)}")
        job["completed_at"] = datetime.now()

async def sync_youtube_videos(job_id: str, limit: int, use_proxy: bool):
    """Sync new YouTube videos using existing pipeline with proxy support"""
    job = processing_jobs[job_id]
    job["status"] = "processing"
    
    try:
        # Import YouTube ingestion pipeline
        from scripts.ingest_youtube_enhanced import EnhancedYouTubeIngester, IngestionConfig
        
        # Configure with proxy if needed
        config = IngestionConfig(
            source='api',
            limit=limit,
            skip_shorts=True,
            youtube_api_key=os.getenv('YOUTUBE_API_KEY'),
            proxy=os.getenv('NORDVPN_PROXY') if use_proxy else None
        )
        
        # Run ingestion
        ingester = EnhancedYouTubeIngester(config)
        await ingester.run_async()  # Implement async version
        
        job["status"] = "completed"
        job["completed_at"] = datetime.now()
        job["processed_files"] = limit  # Approximate
        
    except Exception as e:
        job["status"] = "failed"
        job["errors"].append(f"Sync failed: {str(e)}")
        job["completed_at"] = datetime.now()

def process_zoom_vtt_or_txt(file_path: Path, processor: SRTProcessor) -> bool:
    """Convert Zoom VTT/TXT to SRT format and process"""
    try:
        # Basic VTT to SRT conversion
        # Implement based on Zoom's specific format
        # This is a placeholder - actual implementation depends on Zoom format
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Convert to SRT format (implement specific conversion logic)
        srt_content = convert_to_srt(content)
        
        # Create temporary SRT file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as temp_file:
            temp_file.write(srt_content)
            srt_path = Path(temp_file.name)
        
        # Process as SRT
        success = processor.process_srt_file(srt_path)
        srt_path.unlink()
        
        return success
        
    except Exception as e:
        print(f"Error converting VTT/TXT: {e}")
        return False

def convert_to_srt(content: str) -> str:
    """Convert VTT or TXT content to SRT format"""
    # Placeholder implementation
    # Actual implementation depends on the specific format of Zoom transcripts
    return content

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
