"""Tests for ModelLoader service."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
import onnxruntime as ort

from src.api.services.model_loader import ModelLoader


class TestModelLoader:
    """Test suite for ModelLoader."""
    
    @pytest.fixture
    def mock_s3_ops(self):
        """Mock S3Operations."""
        with patch('src.api.services.model_loader.S3Operations') as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance
    
    @pytest.fixture
    def mock_serving_pointer(self):
        """Mock ServingPointerManager."""
        with patch('src.api.services.model_loader.ServingPointerManager') as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance
    
    @pytest.fixture
    def mock_model_storage(self):
        """Mock ModelStorage."""
        with patch('src.api.services.model_loader.ModelStorage') as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance
    
    @pytest.fixture
    def sample_pointer(self):
        """Sample serving pointer data."""
        return {
            "model_version": "v20250118_120000_abc123",
            "model_path": "s3://bucket/models/v20250118_120000_abc123.onnx",
            "metadata_path": "s3://bucket/metadata/v20250118_120000_abc123.json",
            "baseline_path": "s3://bucket/baselines/v20250118_120000_abc123_baseline.json",
            "schema_hash": "abc123def456",
            "environment": "production"
        }
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample model metadata."""
        return {
            "schema": {
                "schema_hash": "abc123def456",
                "n_features": 5,
                "feature_names": ["age", "income", "credit_score", "employment_years", "debt_ratio"]
            },
            "metrics": {
                "accuracy": 0.85,
                "precision": 0.83,
                "recall": 0.87
            },
            "model_type": "binary_classification"
        }
    
    @pytest.fixture
    def sample_baseline(self):
        """Sample baseline stats."""
        return {
            "feature_stats": {
                "age": {"mean": 45.0, "std": 10.0}
            },
            "prediction_stats": {
                "mean": 0.65
            }
        }
    
    def test_initialization(self, mock_s3_ops, mock_serving_pointer, mock_model_storage):
        """Test ModelLoader initialization."""
        loader = ModelLoader(s3_bucket="test-bucket", environment="production")
        
        assert loader.s3_bucket == "test-bucket"
        assert loader.environment == "production"
        assert loader.model is None
        assert loader.metadata is None
        assert loader.current_version is None
    
    def test_initialization_defaults(self, mock_s3_ops, mock_serving_pointer, mock_model_storage):
        """Test ModelLoader uses settings defaults."""
        with patch('src.api.services.model_loader.settings') as mock_settings:
            mock_settings.S3_BUCKET = "default-bucket"
            mock_settings.ENVIRONMENT = "staging"
            mock_settings.AWS_REGION = "us-west-2"
            
            loader = ModelLoader()
            
            assert loader.s3_bucket == "default-bucket"
            assert loader.environment == "staging"
    
    def test_load_initial_model_no_pointer(self, mock_s3_ops, mock_serving_pointer, mock_model_storage):
        """Test loading initial model when no pointer exists."""
        mock_serving_pointer.get_current_pointer.return_value = None
        
        loader = ModelLoader()
        loader.load_initial_model()
        
        assert loader.model is None
        assert loader.current_version is None
    
    def test_load_initial_model_success(self, mock_s3_ops, mock_serving_pointer, mock_model_storage, 
                                       sample_pointer, sample_metadata, sample_baseline, mock_onnx_session):
        """Test successful initial model loading."""
        mock_serving_pointer.get_current_pointer.return_value = sample_pointer
        mock_model_storage.download_model.return_value = True
        mock_model_storage.get_model_metadata.return_value = sample_metadata
        mock_model_storage.get_baseline_stats.return_value = sample_baseline
        
        with patch('onnxruntime.InferenceSession', return_value=mock_onnx_session):
            loader = ModelLoader()
            loader.load_initial_model()
        
        assert loader.current_version == "v20250118_120000_abc123"
        assert loader.metadata == sample_metadata
        assert loader.baseline == sample_baseline
        assert loader.model is not None
    
    def test_load_model_download_failure(self, mock_s3_ops, mock_serving_pointer, mock_model_storage, sample_pointer):
        """Test model loading fails when download fails."""
        mock_serving_pointer.get_current_pointer.return_value = sample_pointer
        mock_model_storage.download_model.return_value = False
        
        loader = ModelLoader()
        
        with pytest.raises(RuntimeError, match="Failed to download model"):
            loader.load_initial_model()
    
    def test_load_model_missing_metadata(self, mock_s3_ops, mock_serving_pointer, mock_model_storage, 
                                        sample_pointer, mock_onnx_session):
        """Test model loading fails when metadata missing."""
        mock_serving_pointer.get_current_pointer.return_value = sample_pointer
        mock_model_storage.download_model.return_value = True
        mock_model_storage.get_model_metadata.return_value = None
        
        with patch('onnxruntime.InferenceSession', return_value=mock_onnx_session):
            loader = ModelLoader()
            
            with pytest.raises(RuntimeError, match="Failed to load metadata"):
                loader.load_initial_model()
    
    def test_load_same_version_skipped(self, mock_s3_ops, mock_serving_pointer, mock_model_storage, 
                                      sample_pointer, sample_metadata, sample_baseline, mock_onnx_session):
        """Test loading same version is skipped."""
        mock_serving_pointer.get_current_pointer.return_value = sample_pointer
        mock_model_storage.download_model.return_value = True
        mock_model_storage.get_model_metadata.return_value = sample_metadata
        mock_model_storage.get_baseline_stats.return_value = sample_baseline
        
        with patch('onnxruntime.InferenceSession', return_value=mock_onnx_session):
            loader = ModelLoader()
            loader.load_initial_model()
            
            # Reset mocks
            mock_model_storage.download_model.reset_mock()
            
            # Try loading same version again
            loader._load_model_from_pointer(sample_pointer)
            
            # Should not download again
            mock_model_storage.download_model.assert_not_called()
    
    def test_start_hot_reload(self, mock_s3_ops, mock_serving_pointer, mock_model_storage):
        """Test starting hot reload thread."""
        loader = ModelLoader()
        
        with patch('src.api.services.model_loader.settings') as mock_settings:
            mock_settings.MODEL_RELOAD_INTERVAL = 30
            
            loader.start_hot_reload()
            
            assert loader._reload_thread is not None
            assert loader._reload_thread.is_alive()
            
            # Cleanup
            loader.stop_hot_reload()
    
    def test_start_hot_reload_already_running(self, mock_s3_ops, mock_serving_pointer, mock_model_storage):
        """Test starting hot reload when already running."""
        loader = ModelLoader()
        
        loader.start_hot_reload()
        first_thread = loader._reload_thread
        
        # Try starting again
        loader.start_hot_reload()
        
        # Should be same thread
        assert loader._reload_thread == first_thread
        
        # Cleanup
        loader.stop_hot_reload()
    
    def test_stop_hot_reload(self, mock_s3_ops, mock_serving_pointer, mock_model_storage):
        """Test stopping hot reload thread."""
        loader = ModelLoader()
        loader.start_hot_reload()
        
        assert loader._reload_thread.is_alive()
        
        loader.stop_hot_reload()
        
        # Thread should be stopped
        assert loader._stop_reload.is_set()
    
    def test_stop_hot_reload_not_started(self, mock_s3_ops, mock_serving_pointer, mock_model_storage):
        """Test stopping hot reload when not started."""
        loader = ModelLoader()
        
        # Should not raise error
        loader.stop_hot_reload()
    
    def test_get_model_info_no_model(self, mock_s3_ops, mock_serving_pointer, mock_model_storage):
        """Test get_model_info raises error when no model loaded."""
        loader = ModelLoader()
        
        with pytest.raises(RuntimeError, match="No model loaded"):
            loader.get_model_info()
    
    def test_get_model_info_success(self, mock_s3_ops, mock_serving_pointer, mock_model_storage, 
                                    sample_pointer, sample_metadata, sample_baseline, mock_onnx_session):
        """Test get_model_info returns correct information."""
        mock_serving_pointer.get_current_pointer.return_value = sample_pointer
        mock_model_storage.download_model.return_value = True
        mock_model_storage.get_model_metadata.return_value = sample_metadata
        mock_model_storage.get_baseline_stats.return_value = sample_baseline
        
        with patch('onnxruntime.InferenceSession', return_value=mock_onnx_session):
            loader = ModelLoader()
            loader.load_initial_model()
            
            info = loader.get_model_info()
        
        assert info["model_version"] == "v20250118_120000_abc123"
        assert info["schema_hash"] == "abc123def456"
        assert info["n_features"] == 5
        assert "metrics" in info
