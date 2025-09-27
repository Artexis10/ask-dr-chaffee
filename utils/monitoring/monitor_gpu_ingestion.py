#!/usr/bin/env python3
"""
GPU Monitoring for Production Ingestion
Tracks GPU utilization, VRAM usage, and ingestion progress
"""

import time
import psutil
import logging
from datetime import datetime
from pathlib import Path

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import nvidia_ml_py3 as nvml
    nvml.nvmlInit()
    NVML_AVAILABLE = True
except:
    NVML_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def get_gpu_stats():
    """Get GPU utilization and memory stats"""
    if not TORCH_AVAILABLE:
        return None
    
    try:
        if torch.cuda.is_available():
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            allocated = torch.cuda.memory_allocated(0) / (1024**3)
            cached = torch.cuda.memory_reserved(0) / (1024**3)
            
            stats = {
                'total_memory_gb': gpu_memory,
                'allocated_gb': allocated,
                'cached_gb': cached,
                'utilization_pct': (allocated / gpu_memory) * 100 if gpu_memory > 0 else 0
            }
            
            # Try to get utilization from nvidia-ml-py if available
            if NVML_AVAILABLE:
                try:
                    handle = nvml.nvmlDeviceGetHandleByIndex(0)
                    util = nvml.nvmlDeviceGetUtilizationRates(handle)
                    stats['gpu_utilization_pct'] = util.gpu
                    stats['memory_utilization_pct'] = util.memory
                except:
                    pass
            
            return stats
    except Exception as e:
        logger.error(f"Error getting GPU stats: {e}")
    
    return None

def get_system_stats():
    """Get system CPU and memory stats"""
    return {
        'cpu_percent': psutil.cpu_percent(interval=1),
        'memory_percent': psutil.virtual_memory().percent,
        'python_processes': len([p for p in psutil.process_iter(['name']) if 'python' in p.info['name'].lower()])
    }

def monitor_ingestion_progress():
    """Monitor the ingestion progress"""
    logger.info("🔥 GPU & System Monitoring Started for Production Ingestion")
    logger.info("=" * 80)
    
    start_time = time.time()
    
    while True:
        try:
            current_time = datetime.now().strftime("%H:%M:%S")
            elapsed = time.time() - start_time
            
            # Get stats
            gpu_stats = get_gpu_stats()
            sys_stats = get_system_stats()
            
            # Format output
            status_line = f"⏰ {current_time} | ⏱️ {elapsed/60:.1f}m"
            
            if gpu_stats:
                status_line += f" | 🎯 GPU: {gpu_stats.get('gpu_utilization_pct', 'N/A')}%"
                status_line += f" | 💾 VRAM: {gpu_stats['allocated_gb']:.1f}/{gpu_stats['total_memory_gb']:.1f}GB ({gpu_stats['utilization_pct']:.1f}%)"
            
            status_line += f" | 🖥️ CPU: {sys_stats['cpu_percent']:.1f}%"
            status_line += f" | 🧠 RAM: {sys_stats['memory_percent']:.1f}%"
            status_line += f" | 🐍 Python: {sys_stats['python_processes']} procs"
            
            logger.info(status_line)
            
            # Check if we're hitting our targets
            if gpu_stats:
                gpu_util = gpu_stats.get('gpu_utilization_pct', 0)
                vram_gb = gpu_stats['allocated_gb']
                
                if gpu_util >= 80:
                    logger.info("🎯 TARGET HIT: GPU utilization >= 80%!")
                if vram_gb >= 12:
                    logger.info("🎯 TARGET HIT: VRAM usage >= 12GB!")
            
            time.sleep(10)  # Update every 10 seconds
            
        except KeyboardInterrupt:
            logger.info("👋 Monitoring stopped by user")
            break
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_ingestion_progress()
