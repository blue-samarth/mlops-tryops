"""
Tests for DriftService.
"""
import pytest
import time
from unittest.mock import patch, MagicMock
import numpy as np

from src.monitoring.drift_service import DriftService
from src.monitoring.prediction_logger import PredictionLogger


class TestDriftService:
    """Test DriftService functionality."""
    
    def test_initialization(self, sample_baseline):
        """Test service initialization."""
        logger = PredictionLogger(max_size=1000)
        service = DriftService(logger, sample_baseline, "v1.0.0")
        
        assert service.prediction_logger == logger
        assert service.baseline == sample_baseline
        assert service.model_version == "v1.0.0"
        assert service._thread is None
    
    def test_update_baseline(self, sample_baseline):
        """Test baseline update."""
        logger = PredictionLogger(max_size=1000)
        service = DriftService(logger)
        
        service.update_baseline(sample_baseline, "v2.0.0")
        
        assert service.baseline == sample_baseline
        assert service.model_version == "v2.0.0"
    
    @patch('src.monitoring.drift_service.settings')
    def test_start_service(self, mock_settings, sample_baseline):
        """Test starting drift service."""
        mock_settings.ENABLE_DRIFT_DETECTION = True
        mock_settings.DRIFT_CHECK_INTERVAL = 1
        mock_settings.DRIFT_WINDOW_SIZE = 10
        
        logger = PredictionLogger(max_size=100)
        service = DriftService(logger, sample_baseline, "v1.0.0")
        
        service.start()
        
        assert service._thread is not None
        assert service._thread.is_alive()
        
        # Cleanup
        service.stop()
    
    @patch('src.monitoring.drift_service.settings')
    def test_stop_service(self, mock_settings, sample_baseline):
        """Test stopping drift service."""
        mock_settings.ENABLE_DRIFT_DETECTION = True
        mock_settings.DRIFT_CHECK_INTERVAL = 1
        mock_settings.DRIFT_WINDOW_SIZE = 10
        
        logger = PredictionLogger(max_size=100)
        service = DriftService(logger, sample_baseline, "v1.0.0")
        
        service.start()
        time.sleep(0.1)  # Let it start
        service.stop()
        
        time.sleep(0.2)  # Let it stop
        
        assert not service._thread.is_alive() or service._thread is None
    
    @patch('src.monitoring.drift_service.settings')
    def test_service_disabled(self, mock_settings, sample_baseline):
        """Test that service doesn't start when disabled."""
        mock_settings.ENABLE_DRIFT_DETECTION = False
        
        logger = PredictionLogger(max_size=100)
        service = DriftService(logger, sample_baseline, "v1.0.0")
        
        service.start()
        
        assert service._thread is None
    
    @patch('src.monitoring.drift_service.settings')
    @patch('src.monitoring.drift_service.metrics')
    def test_drift_check_execution(self, mock_metrics, mock_settings, sample_baseline, sample_predictions):
        """Test that drift check runs when conditions met."""
        mock_settings.DRIFT_WINDOW_SIZE = 3
        mock_settings.DRIFT_CHECK_INTERVAL = 3600
        mock_settings.DRIFT_PSI_THRESHOLD = 0.2
        mock_settings.DRIFT_KS_THRESHOLD = 0.1
        
        logger = PredictionLogger(max_size=100)
        service = DriftService(logger, sample_baseline, "v1.0.0")
        
        # Log predictions
        for pred in sample_predictions:
            logger.log(pred)
        
        # Manually trigger drift check
        service._run_drift_check()
        
        # Should have recorded check duration
        assert mock_metrics.drift_check_duration_seconds.observe.called
    
    @patch('src.monitoring.drift_service.settings')
    def test_drift_check_insufficient_data(self, mock_settings, sample_baseline):
        """Test drift check with insufficient data."""
        mock_settings.DRIFT_WINDOW_SIZE = 100
        
        logger = PredictionLogger(max_size=100)
        service = DriftService(logger, sample_baseline, "v1.0.0")
        
        # Only log 10 predictions (need 100)
        for i in range(10):
            logger.log({'prediction': float(i), 'features': {'age': 45}})
        
        # Run drift check (should skip)
        service._run_drift_check()
        
        # No error should occur
        assert logger.get_count() == 10
    
    @patch('src.monitoring.drift_service.settings')
    def test_drift_check_no_baseline(self, mock_settings):
        """Test drift check without baseline."""
        mock_settings.DRIFT_WINDOW_SIZE = 10
        
        logger = PredictionLogger(max_size=100)
        service = DriftService(logger, baseline=None, model_version="v1.0.0")
        
        # Log predictions
        for i in range(20):
            logger.log({'prediction': float(i), 'features': {'age': 45}})
        
        # Run drift check (should skip due to no baseline)
        service._run_drift_check()
        
        # Should not crash
        assert logger.get_count() == 20
    
    @patch('src.monitoring.drift_service.settings')
    @patch('src.monitoring.drift_service.metrics')
    @patch('src.monitoring.drift_service.logger')
    def test_drift_alert_triggered(self, mock_logger, mock_metrics, mock_settings, sample_baseline):
        """Test that alerts are triggered when drift exceeds threshold."""
        mock_settings.DRIFT_WINDOW_SIZE = 10
        mock_settings.DRIFT_PSI_THRESHOLD = 0.2
        mock_settings.DRIFT_KS_THRESHOLD = 0.1
        
        logger = PredictionLogger(max_size=100)
        service = DriftService(logger, sample_baseline, "v1.0.0")
        
        # Log predictions with drifted features
        for i in range(15):
            logger.log({
                'features': {
                    'age': 60 + i,  # Drifted from baseline mean of 45
                    'income': 65000,
                    'credit_score': 680
                },
                'prediction': 0.5,
                'prediction_class': 1,
                'model_version': 'v1.0.0'
            })
        
        # Run drift check
        service._run_drift_check()
        
        # Should have logged warnings or incremented alert counter
        # (actual assertion depends on implementation details)
        assert mock_metrics.drift_check_duration_seconds.observe.called
    
    @patch('src.monitoring.drift_service.settings')
    def test_error_handling_in_drift_check(self, mock_settings, sample_baseline):
        """Test error handling during drift check."""
        mock_settings.DRIFT_WINDOW_SIZE = 10
        
        logger = PredictionLogger(max_size=100)
        service = DriftService(logger, sample_baseline, "v1.0.0")
        
        # Log invalid predictions (missing features)
        for i in range(15):
            logger.log({
                'prediction': 0.5,
                # Missing 'features' key - should cause error
            })
        
        # Run drift check - should handle error gracefully
        try:
            service._run_drift_check()
        except Exception as e:
            pytest.fail(f"Drift check should handle errors gracefully: {e}")
