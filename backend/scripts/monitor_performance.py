#!/usr/bin/env python3
"""
Real-time performance monitoring for Enhanced YouTube Ingestion
Monitors processing speed, GPU utilization, and optimization effectiveness
"""
import os
import sys
import time
import psutil
import subprocess
from datetime import datetime
from pathlib import Path
import logging

# Add backend scripts to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.database import DatabaseManager

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Monitor ingestion performance and system resources"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.start_time = None
        self.last_check = None
        self.last_segment_count = 0
        self.processing_times = []
        
    def get_gpu_stats(self):
        """Get GPU utilization and memory usage"""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu', 
                 '--format=csv,noheader,nounits'], 
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                gpu_data = []
                for line in lines:
                    parts = [x.strip() for x in line.split(',')]
                    if len(parts) >= 4:
                        gpu_data.append({
                            'utilization': int(parts[0]),
                            'memory_used': int(parts[1]),
                            'memory_total': int(parts[2]), 
                            'temperature': int(parts[3])
                        })
                return gpu_data
        except Exception as e:
            logger.warning(f"Failed to get GPU stats: {e}")
        return []
    
    def get_db_stats(self):
        """Get current database statistics"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total segments
                    cur.execute("SELECT COUNT(*) FROM segments")
                    total_segments = cur.fetchone()[0]
                    
                    # Get segments by speaker
                    cur.execute("""
                        SELECT speaker_label, COUNT(*) 
                        FROM segments 
                        GROUP BY speaker_label
                        ORDER BY COUNT(*) DESC
                    """)
                    speaker_stats = cur.fetchall()
                    
                    # Get processing rate (segments per minute)
                    if self.last_check and self.last_segment_count > 0:
                        time_diff = (datetime.now() - self.last_check).total_seconds() / 60.0
                        segment_diff = total_segments - self.last_segment_count
                        processing_rate = segment_diff / time_diff if time_diff > 0 else 0
                    else:
                        processing_rate = 0
                    
                    self.last_check = datetime.now()
                    self.last_segment_count = total_segments
                    
                    return {
                        'total_segments': total_segments,
                        'speaker_stats': speaker_stats,
                        'processing_rate': processing_rate
                    }
        except Exception as e:
            logger.error(f"Database stats error: {e}")
            return None
    
    def get_system_stats(self):
        """Get system resource utilization"""
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('.').percent
        }
    
    def display_stats(self):
        """Display comprehensive performance statistics"""
        # Clear screen
        os.system('cls' if os.name == 'nt' else 'clear')
        
        now = datetime.now()
        
        print("=" * 80)
        print(f"🚀 ENHANCED INGESTION PERFORMANCE MONITOR - {now.strftime('%H:%M:%S')}")
        print("=" * 80)
        
        # Database Statistics
        db_stats = self.get_db_stats()
        if db_stats:
            print(f"\n📊 DATABASE STATISTICS:")
            print(f"   Total segments: {db_stats['total_segments']:,}")
            print(f"   Processing rate: {db_stats['processing_rate']:.1f} segments/min")
            
            if db_stats['speaker_stats']:
                print(f"\n🎯 SPEAKER ATTRIBUTION:")
                for speaker, count in db_stats['speaker_stats']:
                    percentage = (count / db_stats['total_segments'] * 100) if db_stats['total_segments'] > 0 else 0
                    speaker_name = "Dr. Chaffee" if speaker in ['CH', 'Chaffee'] else speaker
                    print(f"   {speaker_name}: {count:,} segments ({percentage:.1f}%)")
        
        # GPU Statistics
        gpu_stats = self.get_gpu_stats()
        if gpu_stats:
            print(f"\n🎮 GPU STATISTICS:")
            for i, gpu in enumerate(gpu_stats):
                memory_pct = (gpu['memory_used'] / gpu['memory_total'] * 100)
                print(f"   GPU {i}: {gpu['utilization']}% util, {memory_pct:.1f}% VRAM ({gpu['memory_used']:,}MB/{gpu['memory_total']:,}MB), {gpu['temperature']}°C")
        
        # System Statistics
        sys_stats = self.get_system_stats()
        print(f"\n💻 SYSTEM RESOURCES:")
        print(f"   CPU: {sys_stats['cpu_percent']}%")
        print(f"   Memory: {sys_stats['memory_percent']}%")
        print(f"   Disk: {sys_stats['disk_usage']}%")
        
        # Performance Analysis
        if self.start_time and db_stats:
            elapsed = (now - self.start_time).total_seconds() / 60.0
            if elapsed > 0:
                avg_rate = db_stats['total_segments'] / elapsed
                print(f"\n⚡ PERFORMANCE METRICS:")
                print(f"   Runtime: {elapsed:.1f} minutes")
                print(f"   Average rate: {avg_rate:.1f} segments/min")
                
                # Estimate completion time
                if db_stats['processing_rate'] > 0:
                    # Estimate based on typical video having 15-25 segments
                    estimated_videos_remaining = (100 - (db_stats['total_segments'] / 20)) if db_stats['total_segments'] < 2000 else 0
                    if estimated_videos_remaining > 0:
                        eta_minutes = (estimated_videos_remaining * 20) / db_stats['processing_rate']
                        print(f"   ETA: {eta_minutes:.1f} minutes")
        
        # Optimization Status
        print(f"\n🚀 OPTIMIZATION STATUS:")
        assume_mono = os.getenv('ASSUME_MONOLOGUE', 'true').lower()
        vad_filter = os.getenv('VAD_FILTER', 'true').lower()
        parallel_models = os.getenv('WHISPER_PARALLEL_MODELS', '4')
        
        print(f"   Smart Monologue: {'✅ ENABLED' if assume_mono == 'true' else '❌ DISABLED'}")
        print(f"   VAD Filter: {'❌ DISABLED (faster)' if vad_filter == 'false' else '⚠️ ENABLED (slower)'}")
        print(f"   Parallel Models: {parallel_models}")
        
        # Performance Recommendations
        if gpu_stats and gpu_stats[0]['utilization'] < 60:
            print(f"\n💡 RECOMMENDATIONS:")
            print(f"   • GPU utilization low ({gpu_stats[0]['utilization']}%) - consider increasing concurrency")
        
        if db_stats and db_stats['processing_rate'] < 10:
            print(f"\n💡 RECOMMENDATIONS:")
            print(f"   • Processing rate low ({db_stats['processing_rate']:.1f}/min) - check optimizations")
        
        print(f"\n" + "=" * 80)
        print(f"Press Ctrl+C to exit monitoring")
        print("=" * 80)
    
    def run(self, interval=5):
        """Run continuous monitoring"""
        self.start_time = datetime.now()
        self.last_check = datetime.now()
        
        print("🚀 Starting Enhanced Ingestion Performance Monitor...")
        print(f"Monitoring interval: {interval} seconds")
        
        try:
            while True:
                self.display_stats()
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n\n✅ Monitoring stopped.")
            
            # Final summary
            if self.start_time:
                total_time = (datetime.now() - self.start_time).total_seconds() / 60.0
                db_stats = self.get_db_stats()
                if db_stats:
                    avg_rate = db_stats['total_segments'] / total_time if total_time > 0 else 0
                    print(f"\n📊 FINAL SUMMARY:")
                    print(f"   Total runtime: {total_time:.1f} minutes")
                    print(f"   Total segments: {db_stats['total_segments']:,}")
                    print(f"   Average rate: {avg_rate:.1f} segments/min")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor Enhanced YouTube Ingestion Performance')
    parser.add_argument('--interval', type=int, default=5, help='Update interval in seconds (default: 5)')
    args = parser.parse_args()
    
    monitor = PerformanceMonitor()
    monitor.run(args.interval)
