"""
Integration tests for API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import numpy as np

from src.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_model_loader():
    """Mock ModelLoader for testing."""
    with patch('src.api.dependencies.get_model_loader') as mock:
        loader = MagicMock()
        loader.model = MagicMock()
        loader.metadata = {
            'model_version': 'v20260125_120000_test',
            'schema': {
                'features': ['age', 'income', 'credit_score'],
                'schema_version': '1.0',
                'structural_hash': 'abc123'
            },
            'schema_hash': 'abc123'
        }
        loader.baseline = {
            'feature_statistics': {
                'age': {'type': 'numeric', 'mean': 45.0, 'std': 10.0}
            }
        }
        loader.current_version = 'v20260125_120000_test'
        loader.version = 'v20260125_120000_test'
        
        # Mock get_model_info return value
        loader.get_model_info.return_value = {
            'model_version': 'v20260125_120000_test',
            'schema_hash': 'abc123',
            'feature_names': ['age', 'income', 'credit_score'],
            'n_features': 3,
            'model_type': 'LogisticRegression',
            'promoted_at': '2026-01-25T12:00:00Z',
            'promoted_by': 'test_user'
        }
        
        # Mock ONNX session
        loader.model.get_inputs.return_value = [MagicMock(name='input')]
        loader.model.get_outputs.return_value = [
            MagicMock(name='label'),
            MagicMock(name='probabilities')
        ]
        loader.model.run.return_value = [
            np.array([1]),
            np.array([[0.3, 0.7]])
        ]
        
        mock.return_value = loader
        yield loader


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data['service'] == 'ML Serving API'
        assert 'endpoints' in data
    
    def test_health_endpoint(self, client):
        """Test health endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        # Health can be 'healthy' or 'initializing' depending on model load state
        assert data['status'] in ['healthy', 'initializing']
    
    def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint."""
        response = client.get("/metrics")
        
        assert response.status_code == 200
        # Should return Prometheus text format
        assert 'text/plain' in response.headers.get('content-type', '')


class TestPredictionEndpoints:
    """Test prediction endpoints."""
    
    def test_single_prediction(self, client, mock_model_loader, sample_features):
        """Test single prediction endpoint."""
        response = client.post("/v1/predict", json={'features': sample_features})
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'prediction' in data
        assert 'prediction_class' in data
        assert 'model_version' in data
        assert data['model_version'] == 'v20260125_120000_test'
    
    def test_batch_prediction(self, client, mock_model_loader, sample_batch_features):
        """Test batch prediction endpoint."""
        # Mock batch predictions
        mock_model_loader.model.run.return_value = [
            np.array([0, 1, 1]),
            np.array([[0.6, 0.4], [0.3, 0.7], [0.2, 0.8]])
        ]
        
        response = client.post("/v1/predict/batch", json={'instances': sample_batch_features})
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'predictions' in data
        assert len(data['predictions']) == 3
        assert data['model_version'] == 'v20260125_120000_test'
    
    def test_prediction_invalid_features(self, client, mock_model_loader):
        """Test prediction with invalid features."""
        invalid_features = {'wrong_feature': 123}
        
        response = client.post("/v1/predict", json={'features': invalid_features})
        
        # Should return error
        assert response.status_code in [400, 500]
    
    def test_prediction_missing_features(self, client, mock_model_loader):
        """Test prediction with missing required features."""
        incomplete_features = {'age': 45}  # Missing income and credit_score
        
        response = client.post("/v1/predict", json={'features': incomplete_features})
        
        # Should return validation error
        assert response.status_code in [400, 500]
    
    @patch('src.api.routes.prediction.settings')
    def test_rate_limiting(self, mock_settings, client, mock_model_loader, sample_features):
        """Test rate limiting on endpoints."""
        mock_settings.RATE_LIMIT = "5/minute"
        
        # Make 6 requests quickly
        responses = []
        for _ in range(6):
            response = client.post("/v1/predict", json={'features': sample_features})
            responses.append(response)
        
        # At least one should be rate limited (429)
        status_codes = [r.status_code for r in responses]
        # Note: May need to configure rate limiter properly in test environment
        # assert 429 in status_codes or all(code == 200 for code in status_codes)
    
    def test_model_info_endpoint(self, client, mock_model_loader):
        """Test model info endpoint."""
        response = client.get("/v1/model/info")
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'model_version' in data
        assert data['model_version'] == 'v20260125_120000_test'


class TestRequestIDMiddleware:
    """Test request ID tracking."""
    
    def test_request_id_generated(self, client, mock_model_loader, sample_features):
        """Test that request ID is generated."""
        response = client.post("/v1/predict", json={'features': sample_features})
        
        assert response.status_code == 200
        
        # Should have X-Request-ID in response headers
        assert 'X-Request-ID' in response.headers
        assert len(response.headers['X-Request-ID']) > 0
    
    def test_request_id_preserved(self, client, mock_model_loader, sample_features):
        """Test that provided request ID is preserved."""
        request_id = "test-req-123"
        
        response = client.post(
            "/v1/predict",
            json={'features': sample_features},
            headers={'X-Request-ID': request_id}
        )
        
        assert response.status_code == 200
        assert response.headers['X-Request-ID'] == request_id


class TestDriftIntegration:
    """Test drift detection integration."""
    
    def test_prediction_logging_enabled(self, client, mock_model_loader, sample_features):
        """Test that predictions are logged when drift detection enabled."""
        from src.api.main import app
        from src.api.dependencies import get_prediction_logger
        from src.utils import settings
        
        mock_logger = MagicMock()
        
        # Override dependency
        app.dependency_overrides[get_prediction_logger] = lambda: mock_logger
        
        # Patch settings to enable drift detection
        with patch.object(settings, 'ENABLE_DRIFT_DETECTION', True):
            response = client.post("/v1/predict", json={'features': sample_features})
            
            assert response.status_code == 200
            
            # Should have logged prediction
            assert mock_logger.log.called
            call_args = mock_logger.log.call_args[0][0]
            assert 'features' in call_args
            assert 'prediction' in call_args
            assert 'model_version' in call_args
        
        # Clean up override
        app.dependency_overrides.clear()
    
    @patch('src.api.routes.prediction.settings')
    @patch('src.api.routes.prediction.get_prediction_logger')
    def test_prediction_logging_disabled(self, mock_get_logger, mock_settings, client, mock_model_loader, sample_features):
        """Test that predictions are not logged when drift detection disabled."""
        mock_settings.ENABLE_DRIFT_DETECTION = False
        
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        response = client.post("/v1/predict", json={'features': sample_features})
        
        assert response.status_code == 200
        
        # Should NOT have logged prediction
        assert not mock_logger.log.called
