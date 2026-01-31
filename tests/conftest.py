"""
Pytest fixtures for testing.
"""
import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, MagicMock
from datetime import datetime


@pytest.fixture
def sample_training_data():
    """Generate small training dataset."""
    np.random.seed(42)
    return pd.DataFrame({
        'age': np.random.normal(45, 10, 100).clip(25, 70).astype(int),
        'income': np.random.normal(65000, 20000, 100).clip(30000, 150000).astype(int),
        'credit_score': np.random.normal(680, 70, 100).clip(300, 850).astype(int),
        'approved': np.random.randint(0, 2, 100)
    })


@pytest.fixture
def sample_drifted_data():
    """Generate drifted dataset."""
    np.random.seed(43)
    return pd.DataFrame({
        'age': np.random.normal(55, 10, 100).clip(25, 70).astype(int),  # Drifted
        'income': np.random.normal(65000, 20000, 100).clip(30000, 150000).astype(int),
        'credit_score': np.random.normal(680, 70, 100).clip(300, 850).astype(int),
        'approved': np.random.randint(0, 2, 100)
    })


@pytest.fixture
def sample_features():
    """Single feature set for prediction."""
    return {
        'age': 45,
        'income': 75000,
        'credit_score': 720
    }


@pytest.fixture
def sample_batch_features():
    """Batch of features for prediction."""
    return [
        {'age': 35, 'income': 50000, 'credit_score': 650},
        {'age': 45, 'income': 75000, 'credit_score': 720},
        {'age': 55, 'income': 100000, 'credit_score': 800},
    ]


@pytest.fixture
def sample_schema():
    """Sample model schema."""
    return {
        'features': ['age', 'income', 'credit_score'],
        'feature_types': {
            'age': 'int64',
            'income': 'int64',
            'credit_score': 'int64'
        },
        'feature_order': ['age', 'income', 'credit_score'],
        'schema_version': '1.0',
        'structural_hash': 'abc123def456'
    }


@pytest.fixture
def sample_baseline():
    """Sample baseline statistics."""
    return {
        'feature_statistics': {
            'age': {
                'type': 'numeric',
                'mean': 45.0,
                'std': 10.0,
                'min': 25,
                'max': 70,
                'percentiles': {'p25': 40, 'p50': 45, 'p75': 50}
            },
            'income': {
                'type': 'numeric',
                'mean': 65000.0,
                'std': 20000.0,
                'min': 30000,
                'max': 150000,
                'percentiles': {'p25': 50000, 'p50': 65000, 'p75': 80000}
            },
            'credit_score': {
                'type': 'numeric',
                'mean': 680.0,
                'std': 70.0,
                'min': 300,
                'max': 850,
                'percentiles': {'p25': 640, 'p50': 680, 'p75': 720}
            }
        },
        'prediction_statistics': {
            'type': 'binary_classification',
            'mean_probability': 0.5,
            'histogram': {
                'bin_edges': [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
                'counts': [5, 10, 15, 20, 25, 25, 20, 15, 10, 5]
            }
        }
    }


@pytest.fixture
def sample_metadata(sample_schema, sample_baseline):
    """Sample model metadata."""
    return {
        'model_version': 'v20260125_120000_test123',
        'schema': sample_schema,
        'baseline': sample_baseline,
        'training_date': '2026-01-25T12:00:00Z',
        'git_commit': 'abc123',
        'model_type': 'LogisticRegression'
    }


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing."""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp)


@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client."""
    mock_client = MagicMock()
    
    # Mock successful responses
    mock_client.download_file.return_value = None
    mock_client.upload_file.return_value = None
    mock_client.put_object.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}
    mock_client.get_object.return_value = {
        'Body': MagicMock(read=lambda: b'{"test": "data"}')
    }
    
    return mock_client


@pytest.fixture
def mock_onnx_session():
    """Mock ONNX runtime session."""
    mock_session = MagicMock()
    
    # Mock model inputs/outputs
    mock_input = MagicMock()
    mock_input.name = 'input'
    mock_session.get_inputs.return_value = [mock_input]
    
    mock_output1 = MagicMock()
    mock_output1.name = 'label'
    mock_output2 = MagicMock()
    mock_output2.name = 'probabilities'
    mock_session.get_outputs.return_value = [mock_output1, mock_output2]
    
    # Mock predictions
    mock_session.run.return_value = [
        np.array([1]),  # Predicted class
        np.array([[0.3, 0.7]])  # Probabilities
    ]
    
    return mock_session


@pytest.fixture
def sample_predictions():
    """Sample prediction data for logging."""
    return [
        {
            'features': {'age': 35, 'income': 50000, 'credit_score': 650},
            'prediction': 0.45,
            'prediction_class': 0,
            'model_version': 'v20260125_120000_test123',
            'timestamp': datetime(2026, 1, 25, 12, 0, 0),
            'request_id': 'req-001'
        },
        {
            'features': {'age': 45, 'income': 75000, 'credit_score': 720},
            'prediction': 0.72,
            'prediction_class': 1,
            'model_version': 'v20260125_120000_test123',
            'timestamp': datetime(2026, 1, 25, 12, 0, 1),
            'request_id': 'req-002'
        },
        {
            'features': {'age': 55, 'income': 100000, 'credit_score': 800},
            'prediction': 0.89,
            'prediction_class': 1,
            'model_version': 'v20260125_120000_test123',
            'timestamp': datetime(2026, 1, 25, 12, 0, 2),
            'request_id': 'req-003'
        }
    ]


@pytest.fixture(autouse=True)
def reset_prometheus_metrics():
    """Reset Prometheus metrics between tests."""
    from prometheus_client import REGISTRY
    
    # Clear collectors
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass
    
    yield
    
    # Clean up after test
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass
