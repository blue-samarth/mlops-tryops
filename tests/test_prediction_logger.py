"""
Tests for PredictionLogger.
"""
import pytest
from datetime import datetime
import threading
import time

from src.monitoring.prediction_logger import PredictionLogger


class TestPredictionLogger:
    """Test PredictionLogger functionality."""
    
    def test_initialization(self):
        """Test logger initialization."""
        logger = PredictionLogger(max_size=100)
        
        assert logger.max_size == 100
        assert logger.get_count() == 0
    
    def test_log_prediction(self, sample_predictions):
        """Test logging a single prediction."""
        logger = PredictionLogger(max_size=100)
        
        logger.log(sample_predictions[0])
        
        assert logger.get_count() == 1
        snapshot = logger.get_snapshot()
        assert snapshot[0]['prediction'] == 0.45
        assert snapshot[0]['request_id'] == 'req-001'
    
    def test_log_multiple_predictions(self, sample_predictions):
        """Test logging multiple predictions."""
        logger = PredictionLogger(max_size=100)
        
        for pred in sample_predictions:
            logger.log(pred)
        
        assert logger.get_count() == 3
        snapshot = logger.get_snapshot()
        assert len(snapshot) == 3
    
    def test_circular_buffer_eviction(self):
        """Test that old predictions are evicted when buffer is full."""
        logger = PredictionLogger(max_size=5)
        
        # Log 10 predictions
        for i in range(10):
            logger.log({
                'prediction': float(i),
                'timestamp': datetime.utcnow()
            })
        
        # Should only have last 5
        assert logger.get_count() == 5
        snapshot = logger.get_snapshot()
        
        # First should be prediction 5 (0-4 were evicted)
        assert snapshot[0]['prediction'] == 5.0
        assert snapshot[-1]['prediction'] == 9.0
    
    def test_get_snapshot_with_window_size(self, sample_predictions):
        """Test getting snapshot with specific window size."""
        logger = PredictionLogger(max_size=100)
        
        for pred in sample_predictions:
            logger.log(pred)
        
        # Get only last 2
        snapshot = logger.get_snapshot(window_size=2)
        assert len(snapshot) == 2
        assert snapshot[0]['request_id'] == 'req-002'
        assert snapshot[1]['request_id'] == 'req-003'
    
    def test_get_snapshot_window_larger_than_buffer(self, sample_predictions):
        """Test snapshot when window size > buffer size."""
        logger = PredictionLogger(max_size=100)
        
        logger.log(sample_predictions[0])
        
        # Request 10 but only 1 exists
        snapshot = logger.get_snapshot(window_size=10)
        assert len(snapshot) == 1
    
    def test_clear_buffer(self, sample_predictions):
        """Test clearing the buffer."""
        logger = PredictionLogger(max_size=100)
        
        for pred in sample_predictions:
            logger.log(pred)
        
        assert logger.get_count() == 3
        
        logger.clear()
        
        assert logger.get_count() == 0
        assert logger.get_snapshot() == []
    
    def test_get_statistics_empty(self):
        """Test statistics on empty buffer."""
        logger = PredictionLogger(max_size=100)
        
        stats = logger.get_statistics()
        
        assert stats['count'] == 0
        assert stats['max_size'] == 100
        assert stats['utilization'] == 0.0
        assert stats['oldest'] is None
        assert stats['newest'] is None
    
    def test_get_statistics_with_data(self, sample_predictions):
        """Test statistics with data."""
        logger = PredictionLogger(max_size=100)
        
        for pred in sample_predictions:
            logger.log(pred)
        
        stats = logger.get_statistics()
        
        assert stats['count'] == 3
        assert stats['max_size'] == 100
        assert stats['utilization'] == 0.03
        assert stats['oldest'] is not None
        assert stats['newest'] is not None
        assert stats['time_span_seconds'] == 2.0
    
    def test_automatic_timestamp_addition(self):
        """Test that timestamp is added if not provided."""
        logger = PredictionLogger(max_size=100)
        
        pred = {'prediction': 0.5, 'request_id': 'test'}
        logger.log(pred)
        
        snapshot = logger.get_snapshot()
        assert 'timestamp' in snapshot[0]
        assert isinstance(snapshot[0]['timestamp'], datetime)
    
    def test_thread_safety_concurrent_writes(self):
        """Test thread safety with concurrent writes."""
        logger = PredictionLogger(max_size=1000)
        
        def log_predictions(thread_id, count):
            for i in range(count):
                logger.log({
                    'thread': thread_id,
                    'index': i,
                    'prediction': float(i),
                    'timestamp': datetime.utcnow()
                })
        
        # Start 10 threads, each logging 100 predictions
        threads = []
        for i in range(10):
            t = threading.Thread(target=log_predictions, args=(i, 100))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Should have exactly 1000 predictions (all logged)
        assert logger.get_count() == 1000
    
    def test_thread_safety_concurrent_read_write(self):
        """Test thread safety with concurrent reads and writes."""
        logger = PredictionLogger(max_size=500)
        results = {'snapshots': []}
        
        def write_predictions():
            for i in range(100):
                logger.log({'prediction': float(i), 'timestamp': datetime.utcnow()})
                time.sleep(0.001)
        
        def read_snapshots():
            for _ in range(50):
                snapshot = logger.get_snapshot()
                results['snapshots'].append(len(snapshot))
                time.sleep(0.002)
        
        # Start writer and reader threads
        writer = threading.Thread(target=write_predictions)
        reader = threading.Thread(target=read_snapshots)
        
        writer.start()
        reader.start()
        
        writer.join()
        reader.join()
        
        # Should have read snapshots without errors
        assert len(results['snapshots']) == 50
        # Final count should be 100
        assert logger.get_count() == 100
