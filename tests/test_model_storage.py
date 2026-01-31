"""Tests for ModelStorage."""
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.utils.model_storage import ModelStorage


class TestModelStorage:
    """Test suite for ModelStorage."""
    
    @pytest.fixture
    def mock_s3_ops(self):
        """Mock S3Operations."""
        return MagicMock()
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample model metadata."""
        return {
            "model_version": "v20250118_120000_abc123",
            "schema": {"schema_hash": "abc123"},
            "metrics": {"accuracy": 0.85}
        }
    
    @pytest.fixture
    def sample_baseline(self):
        """Sample baseline stats."""
        return {
            "feature_stats": {"age": {"mean": 45.0}},
            "prediction_stats": {"mean": 0.65}
        }
    
    def test_upload_model_success(self, mock_s3_ops, tmp_path):
        """Test successful model upload."""
        model_file = tmp_path / "model.onnx"
        model_file.write_bytes(b"fake model content")
        
        mock_s3_ops.upload_file.return_value = True
        mock_s3_ops.get_s3_uri.return_value = "s3://bucket/models/v20250118_120000_abc123.onnx"
        
        storage = ModelStorage(mock_s3_ops)
        result = storage.upload_model(
            local_model_path=str(model_file),
            model_version="v20250118_120000_abc123"
        )
        
        assert result == "s3://bucket/models/v20250118_120000_abc123.onnx"
        mock_s3_ops.upload_file.assert_called_once()
    
    def test_upload_model_failure(self, mock_s3_ops, tmp_path):
        """Test model upload failure."""
        model_file = tmp_path / "model.onnx"
        model_file.write_bytes(b"fake model content")
        
        mock_s3_ops.upload_file.return_value = False
        
        storage = ModelStorage(mock_s3_ops)
        
        with pytest.raises(RuntimeError, match="Failed to upload model"):
            storage.upload_model(
                local_model_path=str(model_file),
                model_version="v20250118_120000_abc123"
            )
    
    def test_upload_metadata_success(self, mock_s3_ops, sample_metadata):
        """Test successful metadata upload."""
        mock_s3_ops.upload_json.return_value = True
        mock_s3_ops.get_s3_uri.return_value = "s3://bucket/metadata/v20250118_120000_abc123.json"
        
        storage = ModelStorage(mock_s3_ops)
        result = storage.upload_metadata(
            metadata=sample_metadata,
            model_version="v20250118_120000_abc123"
        )
        
        assert result == "s3://bucket/metadata/v20250118_120000_abc123.json"
        mock_s3_ops.upload_json.assert_called_once()
    
    def test_upload_baseline_success(self, mock_s3_ops, sample_baseline):
        """Test successful baseline upload."""
        mock_s3_ops.upload_json.return_value = True
        mock_s3_ops.get_s3_uri.return_value = "s3://bucket/baselines/v20250118_120000_abc123_baseline.json"
        
        storage = ModelStorage(mock_s3_ops)
        result = storage.upload_baseline(
            baseline_stats=sample_baseline,
            model_version="v20250118_120000_abc123"
        )
        
        assert result == "s3://bucket/baselines/v20250118_120000_abc123_baseline.json"
        mock_s3_ops.upload_json.assert_called_once()
    
    def test_download_model_success(self, mock_s3_ops, tmp_path):
        """Test successful model download."""
        local_path = tmp_path / "downloaded_model.onnx"
        mock_s3_ops.download_file.return_value = True
        
        storage = ModelStorage(mock_s3_ops)
        result = storage.download_model(
            model_version="v20250118_120000_abc123",
            local_path=str(local_path)
        )
        
        assert result is True
    
    def test_get_model_metadata_success(self, mock_s3_ops, sample_metadata):
        """Test getting model metadata."""
        mock_s3_ops.download_json.return_value = sample_metadata
        
        storage = ModelStorage(mock_s3_ops)
        result = storage.get_model_metadata("v20250118_120000_abc123")
        
        assert result == sample_metadata
    
    def test_get_baseline_stats_success(self, mock_s3_ops, sample_baseline):
        """Test getting baseline stats."""
        mock_s3_ops.download_json.return_value = sample_baseline
        
        storage = ModelStorage(mock_s3_ops)
        result = storage.get_baseline_stats("v20250118_120000_abc123")
        
        assert result == sample_baseline
    
    def test_list_model_versions(self, mock_s3_ops):
        """Test listing available models."""
        mock_s3_ops.list_objects.return_value = [
            "models/v20250118_120000_abc123.onnx",
            "models/v20250117_100000_xyz789.onnx"
        ]
        
        storage = ModelStorage(mock_s3_ops)
        models = storage.list_model_versions()
        
        assert len(models) == 2
        assert "v20250118_120000_abc123" in models
