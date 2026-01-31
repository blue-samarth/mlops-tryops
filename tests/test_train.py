"""Tests for train.py module."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import pandas as pd
import numpy as np
import pytest
import onnx

from src.train.train import ModelTrainer, generate_model_version, get_git_commit


class TestGenerateModelVersion:
    """Test model version generation."""
    
    def test_generate_model_version_format(self):
        """Test version string format."""
        version = generate_model_version()
        
        assert version.startswith("v")
        assert len(version) == 23  # v + 8 (date) + 1 (_) + 6 (time) + 1 (_) + 6 (hash)
        
    def test_generate_model_version_custom_prefix(self):
        """Test custom prefix."""
        version = generate_model_version(prefix="model_")
        
        assert version.startswith("model_")
    
    def test_generate_model_version_unique(self):
        """Test versions are unique."""
        v1 = generate_model_version()
        v2 = generate_model_version()
        
        # Should be different due to microsecond timing
        assert v1 != v2


class TestGetGitCommit:
    """Test git commit retrieval."""
    
    @patch('subprocess.run')
    def test_get_git_commit_success(self, mock_run):
        """Test successful git commit retrieval."""
        mock_run.return_value = MagicMock(stdout="abc123def456\n")
        
        commit = get_git_commit()
        
        assert commit == "abc123def456"
    
    @patch('subprocess.run')
    def test_get_git_commit_failure(self, mock_run):
        """Test git commit retrieval failure."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, 'git')
        
        commit = get_git_commit()
        
        assert commit is None
    
    @patch('subprocess.run')
    def test_get_git_commit_timeout(self, mock_run):
        """Test git command timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired('git', 5)
        
        commit = get_git_commit()
        
        assert commit is None


class TestModelTrainer:
    """Test suite for ModelTrainer."""
    
    @pytest.fixture
    def mock_s3_ops(self):
        """Mock S3Operations."""
        with patch('src.train.train.S3Operations') as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance
    
    @pytest.fixture
    def mock_model_storage(self):
        """Mock ModelStorage."""
        with patch('src.train.train.ModelStorage') as mock:
            instance = MagicMock()
            instance.upload_model.return_value = "s3://bucket/models/v1.onnx"
            instance.upload_metadata.return_value = "s3://bucket/metadata/v1.json"
            instance.upload_baseline.return_value = "s3://bucket/baselines/v1_baseline.json"
            mock.return_value = instance
            yield instance
    
    @pytest.fixture
    def sample_training_data(self, tmp_path):
        """Create sample training data CSV."""
        data = pd.DataFrame({
            "age": [25, 30, 35, 40, 45, 50, 55, 60],
            "income": [50000, 60000, 70000, 80000, 90000, 100000, 110000, 120000],
            "credit_score": [650, 700, 750, 800, 650, 700, 750, 800],
            "target": [0, 1, 1, 1, 0, 1, 1, 1]
        })
        
        csv_path = tmp_path / "training_data.csv"
        data.to_csv(csv_path, index=False)
        
        return str(csv_path)
    
    def test_initialization(self, mock_s3_ops, mock_model_storage):
        """Test ModelTrainer initialization."""
        trainer = ModelTrainer(s3_bucket="test-bucket")
        
        assert trainer.s3_bucket == "test-bucket"
        assert trainer.model_version.startswith("v")
    
    def test_initialization_uses_settings(self, mock_s3_ops, mock_model_storage):
        """Test trainer uses settings when bucket not provided."""
        with patch('src.train.train.settings') as mock_settings:
            mock_settings.S3_BUCKET = "default-bucket"
            mock_settings.AWS_REGION = "us-west-2"
            
            trainer = ModelTrainer()
            
            assert trainer.s3_bucket == "default-bucket"
    
    @patch('src.train.train.get_git_commit')
    def test_train_complete_pipeline(self, mock_git, mock_s3_ops, mock_model_storage, sample_training_data, tmp_path):
        """Test complete training pipeline."""
        mock_git.return_value = "abc123"
        
        with patch('onnx.save_model'), \
             patch('pathlib.Path.unlink'):
            
            trainer = ModelTrainer()
            results = trainer.train(
                data_path=sample_training_data,
                target_column="target",
                test_size=0.25,
                random_state=42
            )
        
        assert results["model_version"] == trainer.model_version
        assert "metrics" in results
        assert "accuracy" in results["metrics"]
        assert "precision" in results["metrics"]
        assert "recall" in results["metrics"]
        assert "f1_score" in results["metrics"]
        assert "roc_auc" in results["metrics"]
        assert "training_duration" in results
        
        # Verify uploads were called
        mock_model_storage.upload_model.assert_called_once()
        mock_model_storage.upload_metadata.assert_called_once()
        mock_model_storage.upload_baseline.assert_called_once()
    
    def test_train_metrics_quality(self, mock_s3_ops, mock_model_storage, sample_training_data):
        """Test that training produces reasonable metrics."""
        with patch('onnx.save_model'), \
             patch('pathlib.Path.unlink'):
            
            trainer = ModelTrainer()
            results = trainer.train(
                data_path=sample_training_data,
                target_column="target"
            )
        
        metrics = results["metrics"]
        
        # Metrics should be between 0 and 1
        assert 0 <= metrics["accuracy"] <= 1
        assert 0 <= metrics["precision"] <= 1
        assert 0 <= metrics["recall"] <= 1
        assert 0 <= metrics["f1_score"] <= 1
        assert 0 <= metrics["roc_auc"] <= 1
    
    def test_train_metadata_structure(self, mock_s3_ops, mock_model_storage, sample_training_data):
        """Test metadata has correct structure."""
        with patch('onnx.save_model'), \
             patch('pathlib.Path.unlink'), \
             patch('src.train.train.get_git_commit', return_value="abc123"):
            
            trainer = ModelTrainer()
            trainer.train(data_path=sample_training_data, target_column="target")
        
        # Get the metadata that was uploaded
        metadata = mock_model_storage.upload_metadata.call_args[0][0]
        
        assert metadata["model_version"] == trainer.model_version
        assert metadata["model_type"] == "logistic_regression"
        assert metadata["framework"] == "sklearn"
        assert metadata["format"] == "onnx"
        assert "schema" in metadata
        assert "metrics" in metadata
        assert "hyperparameters" in metadata
        assert metadata["training_samples"] == 6  # 75% of 8
        assert metadata["test_samples"] == 2  # 25% of 8
        assert metadata["git_commit"] == "abc123"
        assert metadata["created_by"] == "training_pipeline"
    
    def test_train_schema_generation(self, mock_s3_ops, mock_model_storage, sample_training_data):
        """Test schema is generated correctly."""
        with patch('onnx.save_model'), \
             patch('pathlib.Path.unlink'):
            
            trainer = ModelTrainer()
            trainer.train(data_path=sample_training_data, target_column="target")
        
        metadata = mock_model_storage.upload_metadata.call_args[0][0]
        schema = metadata["schema"]
        
        assert "structural_schema" in schema
        assert "schema_hash" in schema
        assert schema["n_features"] == 3  # age, income, credit_score (excludes target)
    
    def test_train_baseline_generation(self, mock_s3_ops, mock_model_storage, sample_training_data):
        """Test baseline statistics are generated."""
        with patch('onnx.save_model'), \
             patch('pathlib.Path.unlink'):
            
            trainer = ModelTrainer()
            trainer.train(data_path=sample_training_data, target_column="target")
        
        # Baseline should have been uploaded
        assert mock_model_storage.upload_baseline.called
        baseline = mock_model_storage.upload_baseline.call_args[0][0]
        
        # Should contain feature and prediction stats
        assert isinstance(baseline, dict)
    
    def test_convert_to_onnx(self, mock_s3_ops, mock_model_storage, sample_training_data):
        """Test ONNX conversion."""
        from sklearn.linear_model import LogisticRegression
        
        trainer = ModelTrainer()
        
        # Create a simple trained model
        X = pd.DataFrame({
            "age": [25, 30, 35],
            "income": [50000, 60000, 70000]
        })
        y = [0, 1, 1]
        
        model = LogisticRegression()
        model.fit(X, y)
        
        onnx_model = trainer._convert_to_onnx(model, X)
        
        assert isinstance(onnx_model, onnx.ModelProto)
    
    def test_train_custom_parameters(self, mock_s3_ops, mock_model_storage, sample_training_data):
        """Test training with custom parameters."""
        with patch('onnx.save_model'), \
             patch('pathlib.Path.unlink'):
            
            trainer = ModelTrainer()
            results = trainer.train(
                data_path=sample_training_data,
                target_column="target",
                test_size=0.375,  # 3 out of 8
                random_state=123
            )
        
        metadata = mock_model_storage.upload_metadata.call_args[0][0]
        
        # Verify custom split was used
        assert metadata["test_samples"] == 3
        assert metadata["training_samples"] == 5
