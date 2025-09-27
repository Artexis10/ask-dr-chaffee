#!/usr/bin/env python3
"""
Direct GPU Monitoring for RTX 5080
Uses subprocess to call nvidia-smi directly for more reliable metrics
"""

import os
import time
import subprocess
import psutil
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def get_nvidia_smi_output():
    """Get GPU stats directly from nvidia-smi command"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,utilization.memory,memory.total,memory.used,memory.free', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.returncode == 0:
            # Parse the output (format: GPU util, memory util, total memory, used memory, free memory)
            values = result.stdout.strip().split(',')
            if len(values) >= 5:
                return {
                    'gpu_utilization_pct': float(values[0]),
                    'memory_utilization_pct': float(values[1]),
                    'total_memory_mb': float(values[2]),
                    'used_memory_mb': float(values[3]),
                    'free_memory_mb': float(values[4])
                }
    except Exception as e:
        logger.error(f"Error getting GPU stats from nvidia-smi: {e}")
    
    return None

def get_system_stats():
    """Get system CPU and memory stats"""
    return {
        'cpu_percent': psutil.cpu_percent(interval=1),
        'memory_percent': psutil.virtual_memory().percent,
        'python_processes': len([p for p in psutil.process_iter(['name']) if 'python' in p.info['name'].lower()])
    }

def get_db_stats():
    """Try to get database stats if available"""
    try:
        import psycopg2
        from dotenv import load_dotenv
        load_dotenv()
        
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        with conn.cursor() as cur:
            # Get source count
            cur.execute('SELECT COUNT(*) FROM sources')
            sources_count = cur.fetchone()[0]
            
            # Get chunk count
            cur.execute('SELECT COUNT(*) FROM chunks')
            chunks_count = cur.fetchone()[0]
            
            # Get pending videos count
            cur.execute("SELECT COUNT(*) FROM ingest_state WHERE status = 'pending'")
            pending_count = cur.fetchone()[0]
            
            # Get done videos count
            cur.execute("SELECT COUNT(*) FROM ingest_state WHERE status = 'done'")
            done_count = cur.fetchone()[0]
            
            # Get error videos count
            cur.execute("SELECT COUNT(*) FROM ingest_state WHERE status = 'error'")
            error_count = cur.fetchone()[0]
            
            conn.close()
            
            return {
                'sources': sources_count,
                'chunks': chunks_count,
                'pending': pending_count,
                'done': done_count,
                'error': error_count
            }
    except Exception as e:
        logger.debug(f"Could not get DB stats: {e}")
    
    return None

def monitor_gpu_usage():
    """Monitor GPU usage with direct nvidia-smi calls"""
    logger.info("🔥 DIRECT GPU & System Monitoring Started")
    logger.info("=" * 80)
    
    start_time = time.time()
    last_chunks = 0
    last_sources = 0
    
    while True:
        try:
            current_time = datetime.now().strftime("%H:%M:%S")
            elapsed = time.time() - start_time
            elapsed_min = elapsed / 60
            
            # Get stats
            gpu_stats = get_nvidia_smi_output()
            sys_stats = get_system_stats()
            db_stats = get_db_stats()
            
            # Format output
            status_line = f"⏰ {current_time} | ⏱️ {elapsed_min:.1f}m"
            
            if gpu_stats:
                gpu_util = gpu_stats['gpu_utilization_pct']
                mem_util = gpu_stats['memory_utilization_pct']
                used_gb = gpu_stats['used_memory_mb'] / 1024
                total_gb = gpu_stats['total_memory_mb'] / 1024
                
                status_line += f" | 🎯 GPU: {gpu_util:.1f}%"
                status_line += f" | 💾 VRAM: {used_gb:.1f}/{total_gb:.1f}GB ({mem_util:.1f}%)"
            
            status_line += f" | 🖥️ CPU: {sys_stats['cpu_percent']:.1f}%"
            status_line += f" | 🧠 RAM: {sys_stats['memory_percent']:.1f}%"
            
            if db_stats:
                chunks = db_stats['chunks']
                sources = db_stats['sources']
                
                # Calculate rates
                chunks_delta = chunks - last_chunks
                sources_delta = sources - last_sources
                last_chunks = chunks
                last_sources = sources
                
                status_line += f" | 📊 DB: {sources}src, {chunks}ch"
                status_line += f" | 🏁 Done: {db_stats['done']}"
                
                if chunks_delta > 0 or sources_delta > 0:
                    status_line += f" | 🆕 +{sources_delta}src, +{chunks_delta}ch"
            
            logger.info(status_line)
            
            # Check if we're hitting our targets
            if gpu_stats:
                if gpu_stats['gpu_utilization_pct'] >= 80:
                    logger.info("🎯 TARGET HIT: GPU utilization >= 80%!")
                if gpu_stats['used_memory_mb'] / 1024 >= 12:
                    logger.info("🎯 TARGET HIT: VRAM usage >= 12GB!")
            
            time.sleep(10)  # Update every 10 seconds
            
        except KeyboardInterrupt:
            logger.info("👋 Monitoring stopped by user")
            break
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_gpu_usage()
