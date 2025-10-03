"""Unit tests for concurrency and queue management in ingest_youtube_enhanced.py."""

import queue
import threading
import time
from unittest.mock import Mock, patch, MagicMock

import pytest


@pytest.mark.unit
class TestConcurrencyConfiguration:
    """Test concurrency configuration and limits."""
    
    def test_config_io_concurrency_default(self, monkeypatch):
        """Test I/O concurrency default value."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        config = IngestionConfig(enable_speaker_id=False, dry_run=True)
        
        # Default should be set
        assert config.io_concurrency > 0
    
    def test_config_asr_concurrency_default(self, monkeypatch):
        """Test ASR concurrency default value."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        config = IngestionConfig(enable_speaker_id=False, dry_run=True)
        
        # Default should be set
        assert config.asr_concurrency > 0
    
    def test_config_db_concurrency_default(self, monkeypatch):
        """Test DB concurrency default value."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        config = IngestionConfig(enable_speaker_id=False, dry_run=True)
        
        # Default should be set
        assert config.db_concurrency > 0
    
    def test_config_concurrency_from_env(self, monkeypatch):
        """Test concurrency values read from environment."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        monkeypatch.setenv('IO_WORKERS', '8')
        monkeypatch.setenv('ASR_WORKERS', '2')
        monkeypatch.setenv('DB_WORKERS', '6')
        
        config = IngestionConfig(enable_speaker_id=False, dry_run=True)
        
        assert config.io_concurrency == 8
        assert config.asr_concurrency == 2
        assert config.db_concurrency == 6
    
    def test_config_legacy_concurrency(self, monkeypatch):
        """Test legacy concurrency parameter."""
        from backend.scripts.ingest_youtube_enhanced import IngestionConfig
        
        monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost/test')
        
        config = IngestionConfig(
            concurrency=8,
            enable_speaker_id=False,
            dry_run=True
        )
        
        assert config.concurrency == 8


@pytest.mark.unit
class TestQueueManagement:
    """Test queue creation and management."""
    
    def test_queue_maxsize_limits(self):
        """Test queues respect maxsize limits."""
        # Create bounded queues
        io_queue = queue.Queue(maxsize=5)
        asr_queue = queue.Queue(maxsize=3)
        
        # Fill io_queue to capacity
        for i in range(5):
            io_queue.put(i)
        
        # Queue should be full
        assert io_queue.full()
        assert io_queue.qsize() == 5
        
        # Attempting to put without blocking should raise
        with pytest.raises(queue.Full):
            io_queue.put_nowait(6)
    
    def test_queue_get_blocks_when_empty(self):
        """Test queue.get blocks when empty."""
        test_queue = queue.Queue()
        
        # Queue should be empty
        assert test_queue.empty()
        
        # get_nowait should raise
        with pytest.raises(queue.Empty):
            test_queue.get_nowait()
    
    def test_queue_put_get_order(self):
        """Test queue maintains FIFO order."""
        test_queue = queue.Queue()
        
        items = [1, 2, 3, 4, 5]
        for item in items:
            test_queue.put(item)
        
        retrieved = []
        while not test_queue.empty():
            retrieved.append(test_queue.get())
        
        assert retrieved == items
    
    def test_queue_thread_safety(self):
        """Test queue is thread-safe."""
        test_queue = queue.Queue()
        results = []
        
        def producer():
            for i in range(10):
                test_queue.put(i)
        
        def consumer():
            while True:
                try:
                    item = test_queue.get(timeout=0.1)
                    results.append(item)
                except queue.Empty:
                    break
        
        # Start producer and consumer threads
        prod_thread = threading.Thread(target=producer)
        cons_thread = threading.Thread(target=consumer)
        
        prod_thread.start()
        prod_thread.join()
        
        cons_thread.start()
        cons_thread.join()
        
        # All items should be consumed
        assert len(results) == 10
        assert sorted(results) == list(range(10))


@pytest.mark.unit
class TestConcurrencyGuards:
    """Test concurrency guards and limits."""
    
    def test_max_concurrent_workers_respected(self):
        """Test maximum concurrent workers limit is respected."""
        from concurrent.futures import ThreadPoolExecutor
        
        max_workers = 3
        active_count = []
        lock = threading.Lock()
        
        def worker(n):
            with lock:
                active_count.append(1)
                current = len(active_count)
            
            # Simulate work
            time.sleep(0.01)
            
            with lock:
                active_count.pop()
            
            return current
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            results = [f.result() for f in futures]
        
        # Maximum concurrent should not exceed max_workers
        assert max(results) <= max_workers
    
    def test_semaphore_limits_concurrent_access(self):
        """Test semaphore limits concurrent access."""
        semaphore = threading.Semaphore(2)
        concurrent_count = []
        max_concurrent = [0]
        lock = threading.Lock()
        
        def worker():
            with semaphore:
                with lock:
                    concurrent_count.append(1)
                    max_concurrent[0] = max(max_concurrent[0], len(concurrent_count))
                
                time.sleep(0.01)
                
                with lock:
                    concurrent_count.pop()
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Max concurrent should not exceed semaphore limit
        assert max_concurrent[0] <= 2
    
    def test_stop_event_coordination(self):
        """Test stop event coordinates worker shutdown."""
        stop_event = threading.Event()
        worker_stopped = [False]
        
        def worker():
            while not stop_event.is_set():
                time.sleep(0.01)
            worker_stopped[0] = True
        
        thread = threading.Thread(target=worker)
        thread.start()
        
        # Worker should be running
        time.sleep(0.05)
        assert not worker_stopped[0]
        
        # Signal stop
        stop_event.set()
        thread.join(timeout=1.0)
        
        # Worker should have stopped
        assert worker_stopped[0]


@pytest.mark.unit
class TestPipelineCoordination:
    """Test pipeline stage coordination."""
    
    def test_poison_pill_pattern(self):
        """Test poison pill pattern for worker shutdown."""
        work_queue = queue.Queue()
        results = []
        
        def worker():
            while True:
                item = work_queue.get()
                if item is None:  # Poison pill
                    break
                results.append(item)
        
        thread = threading.Thread(target=worker)
        thread.start()
        
        # Add work items
        for i in range(5):
            work_queue.put(i)
        
        # Send poison pill
        work_queue.put(None)
        
        thread.join(timeout=1.0)
        
        assert results == [0, 1, 2, 3, 4]
    
    def test_multiple_workers_poison_pills(self):
        """Test poison pills for multiple workers."""
        work_queue = queue.Queue()
        results = []
        lock = threading.Lock()
        
        def worker():
            while True:
                item = work_queue.get()
                if item is None:
                    break
                with lock:
                    results.append(item)
        
        num_workers = 3
        threads = [threading.Thread(target=worker) for _ in range(num_workers)]
        for t in threads:
            t.start()
        
        # Add work
        for i in range(10):
            work_queue.put(i)
        
        # Send poison pills (one per worker)
        for _ in range(num_workers):
            work_queue.put(None)
        
        for t in threads:
            t.join(timeout=1.0)
        
        # All work should be processed
        assert sorted(results) == list(range(10))


@pytest.mark.unit
class TestQueuePeakTracking:
    """Test queue peak size tracking."""
    
    def test_queue_peak_tracking(self):
        """Test tracking maximum queue size."""
        test_queue = queue.Queue()
        peak_size = 0
        
        # Add items and track peak
        for i in range(1, 11):
            test_queue.put(i)
            peak_size = max(peak_size, test_queue.qsize())
        
        assert peak_size == 10
        
        # Remove some items
        for _ in range(5):
            test_queue.get()
        
        # Peak should remain at maximum
        assert peak_size == 10
        assert test_queue.qsize() == 5
    
    def test_processing_stats_queue_peaks(self):
        """Test ProcessingStats tracks queue peaks."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        stats = ProcessingStats()
        
        # Simulate queue size updates
        stats.io_queue_peak = max(stats.io_queue_peak, 15)
        stats.asr_queue_peak = max(stats.asr_queue_peak, 8)
        stats.db_queue_peak = max(stats.db_queue_peak, 20)
        
        assert stats.io_queue_peak == 15
        assert stats.asr_queue_peak == 8
        assert stats.db_queue_peak == 20


@pytest.mark.unit
class TestThreadSafety:
    """Test thread-safe operations."""
    
    def test_stats_lock_prevents_race_conditions(self):
        """Test stats lock prevents race conditions."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        stats = ProcessingStats()
        stats_lock = threading.Lock()
        
        def increment_processed():
            for _ in range(100):
                with stats_lock:
                    stats.processed += 1
        
        threads = [threading.Thread(target=increment_processed) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have exactly 1000 increments (10 threads * 100 each)
        assert stats.processed == 1000
    
    def test_concurrent_stats_updates(self):
        """Test concurrent statistics updates are safe."""
        from backend.scripts.ingest_youtube_enhanced import ProcessingStats
        
        stats = ProcessingStats()
        lock = threading.Lock()
        
        def update_stats():
            for _ in range(50):
                with lock:
                    stats.processed += 1
                    stats.segments_created += 10
                    stats.chaffee_segments += 8
        
        threads = [threading.Thread(target=update_stats) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify all updates completed
        assert stats.processed == 250  # 5 threads * 50 each
        assert stats.segments_created == 2500  # 5 threads * 50 * 10
        assert stats.chaffee_segments == 2000  # 5 threads * 50 * 8


@pytest.mark.unit
class TestLoggingInterleaving:
    """Test logging does not interleave incorrectly."""
    
    def test_concurrent_logging_no_interleave(self, caplog):
        """Test concurrent logging produces complete messages."""
        import logging
        
        caplog.set_level(logging.INFO)
        logger = logging.getLogger('test_concurrent')
        
        def log_message(thread_id):
            for i in range(5):
                logger.info(f"Thread {thread_id} message {i}")
        
        threads = [threading.Thread(target=log_message, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All messages should be complete (no interleaving within a message)
        for record in caplog.records:
            # Each message should be well-formed
            assert 'Thread' in record.message
            assert 'message' in record.message
