"""Tests for ServingPointerManager."""
from unittest.mock import MagicMock, patch
import pytest

from src.utils.serving_pointer import ServingPointerManager


class TestServingPointerManager:
    """Test suite for ServingPointerManager."""
    
    @pytest.fixture
    def mock_s3_ops(self):
        """Mock S3Operations."""
        with patch('src.utils.serving_pointer.S3Operations') as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample model metadata."""
        return {
            "schema": {"schema_hash": "abc123", "n_features": 5},
            "metrics": {"accuracy": 0.85},
            "model_type": "binary_classification"
        }
    
    def test_initialization(self, mock_s3_ops):
        """Test ServingPointerManager initialization."""
        manager = ServingPointerManager(
            s3_bucket="test-bucket",
            environment="production",
            region="us-west-2"
        )
        
        assert manager.environment == "production"
        assert manager.pointer_key == "serving/production.json"
        assert manager.history_prefix == "serving/history/production_"
    
    def test_get_current_pointer_success(self, mock_s3_ops):
        """Test getting current pointer."""
        pointer = {
            "model_version": "v20250118_120000_abc123",
            "environment": "production"
        }
        mock_s3_ops.download_json.return_value = pointer
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        result = manager.get_current_pointer()
        
        assert result == pointer
        mock_s3_ops.download_json.assert_called_once_with("serving/production.json")
    
    def test_get_current_pointer_not_found(self, mock_s3_ops):
        """Test getting pointer when none exists."""
        mock_s3_ops.download_json.return_value = None
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        result = manager.get_current_pointer()
        
        assert result is None
    
    def test_promote_model_invalid_version_format(self, mock_s3_ops):
        """Test promoting model with invalid version format."""
        manager = ServingPointerManager(s3_bucket="test-bucket")
        
        with pytest.raises(ValueError, match="Invalid model version format"):
            manager.promote_model("invalid_version", "user@example.com")
    
    def test_promote_model_missing_files(self, mock_s3_ops, sample_metadata):
        """Test promoting model when files missing."""
        mock_s3_ops.object_exists.return_value = False
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        
        with pytest.raises(ValueError, match="Model not found"):
            manager.promote_model("v20250118_120000_abc123", "user@example.com")
    
    def test_promote_model_missing_metadata(self, mock_s3_ops):
        """Test promoting model when metadata missing required fields."""
        # Model exists but metadata is incomplete
        mock_s3_ops.object_exists.return_value = True
        mock_s3_ops.download_json.return_value = {"incomplete": "metadata"}
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        
        with pytest.raises(ValueError, match="Invalid metadata: missing"):
            manager.promote_model("v20250118_120000_abc123", "user@example.com")
    
    def test_promote_model_first_time(self, mock_s3_ops, sample_metadata):
        """Test promoting model for first time (no previous pointer)."""
        mock_s3_ops.object_exists.return_value = True
        mock_s3_ops.download_json.side_effect = [
            None,  # First call: no current pointer
            sample_metadata  # Second call: metadata
        ]
        mock_s3_ops.upload_json.return_value = True
        
        manager = ServingPointerManager(s3_bucket="test-bucket", environment="production")
        result = manager.promote_model(
            "v20250118_120000_abc123",
            promoted_by="user@example.com",
            promotion_reason="Initial deployment"
        )
        
        assert result["model_version"] == "v20250118_120000_abc123"
        assert result["promoted_by"] == "user@example.com"
        assert result["promotion_reason"] == "Initial deployment"
        assert result["previous_version"] is None
        assert result["environment"] == "production"
        assert result["approved"] is True
        
        # Should upload new pointer
        assert mock_s3_ops.upload_json.call_count == 1
    
    def test_promote_model_with_history(self, mock_s3_ops, sample_metadata):
        """Test promoting model saves previous to history."""
        previous_pointer = {
            "model_version": "v20250117_100000_xyz789",
            "environment": "production"
        }
        
        mock_s3_ops.object_exists.return_value = True
        mock_s3_ops.download_json.side_effect = [
            previous_pointer,  # First call: current pointer
            sample_metadata  # Second call: metadata
        ]
        mock_s3_ops.upload_json.return_value = True
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        result = manager.promote_model(
            "v20250118_120000_abc123",
            promoted_by="system",
            promotion_reason="Performance improvement"
        )
        
        assert result["previous_version"] == "v20250117_100000_xyz789"
        assert result["rollback_to"] == "v20250117_100000_xyz789"
        
        # Should upload history + new pointer
        assert mock_s3_ops.upload_json.call_count == 2
    
    def test_promote_model_upload_failure(self, mock_s3_ops, sample_metadata):
        """Test promoting model handles upload failure."""
        mock_s3_ops.object_exists.return_value = True
        mock_s3_ops.download_json.side_effect = [None, sample_metadata]
        mock_s3_ops.upload_json.return_value = False
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        
        with pytest.raises(RuntimeError, match="Failed to update serving pointer"):
            manager.promote_model("v20250118_120000_abc123", "system")
    
    def test_rollback_to_previous(self, mock_s3_ops, sample_metadata):
        """Test rollback functionality."""
        current_pointer = {
            "model_version": "v20250118_120000_abc123",
            "previous_version": "v20250117_100000_xyz789",
            "environment": "production"
        }
        
        mock_s3_ops.object_exists.return_value = True
        mock_s3_ops.download_json.side_effect = [
            current_pointer,  # get_current_pointer
            current_pointer,  # promote_model gets current
            sample_metadata,  # metadata
            None, # baseline (not checked in test)
        ]
        mock_s3_ops.upload_json.return_value = True
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        result = manager.rollback()
        
        assert result["model_version"] == "v20250117_100000_xyz789"
    
    def test_rollback_no_previous_version(self, mock_s3_ops):
        """Test rollback fails when no previous version."""
        current_pointer = {
            "model_version": "v20250118_120000_abc123",
            "previous_version": None,
            "environment": "production"
        }
        
        mock_s3_ops.download_json.return_value = current_pointer
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        
        with pytest.raises(ValueError, match="No previous version in pointer"):
            manager.rollback()
    
    def test_rollback_no_current_pointer(self, mock_s3_ops):
        """Test rollback fails when no current pointer."""
        mock_s3_ops.download_json.return_value = None
        
        manager = ServingPointerManager(s3_bucket="test-bucket")
        
        with pytest.raises(ValueError, match="No current pointer found"):
            manager.rollback()
    
    def test_get_promotion_history(self, mock_s3_ops):
        """Test getting promotion history."""
        history_files = [
            "serving/history/production_20250118_120000.json",
            "serving/history/production_20250117_100000.json"
        ]
        
        mock_s3_ops.list_objects.return_value = history_files
        
        mock_s3_ops.download_json.side_effect = [
            {"model_version": "v20250118_120000_abc123", "promoted_at": "2025-01-18T12:00:00Z"},
            {"model_version": "v20250117_100000_xyz789", "promoted_at": "2025-01-17T10:00:00Z"}
        ]
        
        manager = ServingPointerManager(s3_bucket="test-bucket", environment="production")
        history = manager.get_promotion_history(limit=10)
        
        assert len(history) == 2
        assert history[0]["model_version"] == "v20250118_120000_abc123"
