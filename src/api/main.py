import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.api.routes import health, prediction
from src.api.dependencies import get_model_loader, get_prediction_logger, get_drift_service
from src.api.middleware import RequestIDMiddleware
from src.utils import settings
from src.monitoring import metrics

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s',
    defaults={'request_id': 'N/A'}
)
logger: logging.Logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting ML Serving API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"S3 Bucket: {settings.S3_BUCKET}")
    logger.info(f"AWS Region: {settings.AWS_REGION}")
    
    # Initialize model loader
    model_loader = get_model_loader()
    
    try:
        model_loader.load_initial_model()
    except Exception as e:
        logger.error(f"Failed to load initial model: {e}")
        logger.warning("API will start without a model - predictions will fail until model is loaded")
    
    # Start hot-reload background thread
    model_loader.start_hot_reload()
    
    # Start drift detection service
    if settings.ENABLE_DRIFT_DETECTION:
        drift_service = get_drift_service()
        
        # Initialize with current model's baseline
        if model_loader.baseline:
            drift_service.update_baseline(
                model_loader.baseline, 
                model_loader.current_version or "unknown"
            )
        
        drift_service.start()
        logger.info("Drift detection service started")
    
    # Set model info metric
    if model_loader.current_version:
        metrics.model_info.info({
            "version": model_loader.current_version,
            "bucket": settings.S3_BUCKET,
            "environment": settings.ENVIRONMENT,
        })
    
    logger.info("API ready to serve requests")
    
    yield
    
    # Shutdown
    logger.info("Shutting down ML Serving API...")
    model_loader.stop_hot_reload()
    
    if settings.ENABLE_DRIFT_DETECTION:
        drift_service = get_drift_service()
        drift_service.stop()
        logger.info("Drift detection service stopped")
    
    logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="ML Serving API",
    description="Production ML model serving with hot-reloading and drift detection",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Request ID middleware (for tracing)
app.add_middleware(RequestIDMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(prediction.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "ML Serving API",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "endpoints": {
            "health": "/health",
            "readiness": "/ready",
            "predict": "/v1/predict",
            "batch_predict": "/v1/predict/batch",
            "model_info": "/v1/model/info",
            "metrics": "/metrics",
        }
    }


@app.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus exposition format.
    """
    if not settings.ENABLE_PROMETHEUS:
        return {"error": "Prometheus metrics disabled"}
    
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,  # Set to True for development
        log_level=settings.LOG_LEVEL.lower(),
    )
