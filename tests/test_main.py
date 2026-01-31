from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from fastapi.testclient import TestClient


class TestMainApplication:
    """Test suite for main FastAPI application."""
    
    @pytest.fixture
    def mock_model_loader(self):
        """Mock ModelLoader."""
        mock = MagicMock()
        mock.version = "v20250118_120000_abc123"
        mock.baseline = {
            "feature_stats": {"age": {"mean": 45.0}},
            "prediction_stats": {"mean": 0.65}
        }
        mock.load_initial_model = MagicMock()
        mock.start_hot_reload = MagicMock()
        mock.stop_hot_reload = MagicMock()
        return mock
    
    @pytest.fixture
    def mock_drift_service(self):
        """Mock DriftService."""
        mock = MagicMock()
        mock.start = MagicMock()
        mock.stop = MagicMock()
        mock.update_baseline = MagicMock()
        return mock
    
    def test_lifespan_startup_success(self, mock_model_loader, mock_drift_service):
        """Test successful application startup."""
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = True
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            with TestClient(app) as client:
                # Lifespan should have started
                mock_model_loader.load_initial_model.assert_called_once()
                mock_model_loader.start_hot_reload.assert_called_once()
                mock_drift_service.update_baseline.assert_called_once()
                mock_drift_service.start.assert_called_once()
            
            # Lifespan shutdown
            mock_model_loader.stop_hot_reload.assert_called_once()
            mock_drift_service.stop.assert_called_once()
    
    def test_lifespan_model_load_failure(self, mock_model_loader, mock_drift_service):
        """Test startup continues even if model load fails."""
        mock_model_loader.load_initial_model.side_effect = Exception("S3 error")
        
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = False
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            # Should not raise exception
            with TestClient(app) as client:
                response = client.get("/")
                assert response.status_code == 200
    
    def test_lifespan_drift_detection_disabled(self, mock_model_loader, mock_drift_service):
        """Test startup with drift detection disabled."""
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = False
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            with TestClient(app) as client:
                # Drift service should not be started
                mock_drift_service.start.assert_not_called()
    
    def test_lifespan_no_baseline(self, mock_drift_service):
        """Test startup when model has no baseline."""
        mock_loader = MagicMock()
        mock_loader.version = None
        mock_loader.baseline = None
        mock_loader.load_initial_model = MagicMock()
        mock_loader.start_hot_reload = MagicMock()
        mock_loader.stop_hot_reload = MagicMock()
        
        with patch('src.api.main.get_model_loader', return_value=mock_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = True
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            with TestClient(app) as client:
                # Should not update baseline if none exists
                mock_drift_service.update_baseline.assert_not_called()
    
    def test_root_endpoint(self, mock_model_loader, mock_drift_service):
        """Test root endpoint returns service info."""
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = False
            mock_settings.ENVIRONMENT = "production"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            with TestClient(app) as client:
                response = client.get("/")
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["service"] == "ML Serving API"
                assert data["version"] == "1.0.0"
                assert data["environment"] == "production"
                assert "endpoints" in data
                assert "/health" in data["endpoints"]["health"]
    
    def test_metrics_endpoint_enabled(self, mock_model_loader, mock_drift_service):
        """Test metrics endpoint when Prometheus enabled."""
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = False
            mock_settings.ENABLE_PROMETHEUS = True
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            with TestClient(app) as client:
                response = client.get("/metrics")
                
                assert response.status_code == 200
                # Should return Prometheus format
                assert "text/plain" in response.headers["content-type"]
    
    def test_metrics_endpoint_disabled(self, mock_model_loader, mock_drift_service):
        """Test metrics endpoint when Prometheus disabled."""
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = False
            mock_settings.ENABLE_PROMETHEUS = False
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            with TestClient(app) as client:
                response = client.get("/metrics")
                
                assert response.status_code == 200
                data = response.json()
                assert "error" in data
                assert "disabled" in data["error"].lower()
    
    def test_cors_middleware(self, mock_model_loader, mock_drift_service):
        """Test CORS middleware is configured."""
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = False
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            with TestClient(app) as client:
                response = client.options("/", headers={"Origin": "http://example.com"})
                
                # CORS headers should be present
                assert "access-control-allow-origin" in response.headers
    
    def test_rate_limiter_configured(self, mock_model_loader, mock_drift_service):
        """Test rate limiter is configured on app."""
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = False
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            mock_settings.RATE_LIMIT = "100/minute"
            
            from src.api.main import app
            
            # Rate limiter should be in app state
            assert hasattr(app.state, 'limiter')
    
    def test_request_id_middleware(self, mock_model_loader, mock_drift_service):
        """Test RequestID middleware adds request IDs."""
        with patch('src.api.main.get_model_loader', return_value=mock_model_loader), \
             patch('src.api.main.get_drift_service', return_value=mock_drift_service), \
             patch('src.api.main.settings') as mock_settings:
            
            mock_settings.ENABLE_DRIFT_DETECTION = False
            mock_settings.ENVIRONMENT = "test"
            mock_settings.S3_BUCKET = "test-bucket"
            mock_settings.AWS_REGION = "us-east-1"
            
            from src.api.main import app
            
            with TestClient(app) as client:
                response = client.get("/")
                
                # Should have X-Request-ID header
                assert "x-request-id" in response.headers
