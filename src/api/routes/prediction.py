import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.schemas.prediction import (
    PredictionRequest,
    PredictionResponse,
    BatchPredictionRequest,
    BatchPredictionResponse,
    ModelInfoResponse,
)
from src.api.services.predictor import Predictor
from src.api.dependencies import get_predictor, get_prediction_logger
from src.api.middleware import get_request_id
from src.monitoring.prediction_logger import PredictionLogger
from src.monitoring import metrics
from src.utils import settings

logger: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["predictions"])

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@router.post("/predict", response_model=PredictionResponse)
@limiter.limit("50/minute")  # Higher limit for single predictions
async def predict(
    request: Request,
    prediction_request: PredictionRequest,
    predictor: Predictor = Depends(get_predictor),
    prediction_logger: PredictionLogger = Depends(get_prediction_logger)
) -> PredictionResponse:
    """
    Make a prediction for a single instance.
    
    Validates input schema and returns prediction with model version.
    Rate limit: 50 requests per minute per IP.
    """
    request_id = get_request_id(request)
    start_time = datetime.utcnow()
    
    try:
        logger.info(f"Prediction request received", extra={"request_id": request_id})
        result = predictor.predict(prediction_request.features)
        
        # Record metrics
        latency = (datetime.utcnow() - start_time).total_seconds()
        metrics.prediction_requests_total.labels(
            endpoint="/v1/predict",
            model_version=result["model_version"],
            status="success"
        ).inc()
        metrics.prediction_latency_seconds.labels(
            endpoint="/v1/predict",
            model_version=result["model_version"]
        ).observe(latency)
        
        # Log prediction for drift detection
        if settings.ENABLE_DRIFT_DETECTION:
            prediction_logger.log({
                "features": prediction_request.features,
                "prediction": result["prediction"],
                "prediction_class": result["prediction_class"],
                "model_version": result["model_version"],
                "timestamp": start_time,
                "request_id": request_id,
            })
        
        logger.info(
            f"Prediction successful",
            extra={
                "request_id": request_id,
                "model_version": result["model_version"],
                "prediction": result["prediction"],
                "latency_ms": latency * 1000,
            }
        )
        return PredictionResponse(**result)
    
    except ValueError as e:
        metrics.prediction_errors_total.labels(
            endpoint="/v1/predict",
            error_type="validation"
        ).inc()
        logger.warning(f"Validation error: {e}", extra={"request_id": request_id})
        raise HTTPException(status_code=400, detail=str(e))
    
    except RuntimeError as e:
        metrics.prediction_errors_total.labels(
            endpoint="/v1/predict",
            error_type="runtime"
        ).inc()
        logger.error(f"Runtime error: {e}", extra={"request_id": request_id})
        raise HTTPException(status_code=503, detail=str(e))
    
    except Exception as e:
        metrics.prediction_errors_total.labels(
            endpoint="/v1/predict",
            error_type="internal"
        ).inc()
        logger.error(f"Unexpected error: {e}", exc_info=True, extra={"request_id": request_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/predict/batch", response_model=BatchPredictionResponse)
@limiter.limit("20/minute")  # Lower limit for batch predictions
async def predict_batch(
    request: Request,
    prediction_request: BatchPredictionRequest,
    predictor: Predictor = Depends(get_predictor),
    prediction_logger: PredictionLogger = Depends(get_prediction_logger)
) -> BatchPredictionResponse:
    """
    Make predictions for multiple instances.
    Batch endpoint for efficient processing of multiple predictions.
    Rate limit: 20 requests per minute per IP.
    """
    request_id = get_request_id(request)
    batch_size = len(prediction_request.instances)
    start_time = datetime.utcnow()
    
    try:
        logger.info(f"Batch prediction request received", extra={"request_id": request_id, "batch_size": batch_size})
        result = predictor.predict_batch(prediction_request.instances)
        
        # Record metrics
        latency = (datetime.utcnow() - start_time).total_seconds()
        metrics.prediction_requests_total.labels(
            endpoint="/v1/predict/batch",
            model_version=result["model_version"],
            status="success"
        ).inc(batch_size)  # Increment by batch size
        metrics.prediction_latency_seconds.labels(
            endpoint="/v1/predict/batch",
            model_version=result["model_version"]
        ).observe(latency)
        
        # Log predictions for drift detection
        if settings.ENABLE_DRIFT_DETECTION:
            for features, pred_dict in zip(
                prediction_request.instances, 
                result["predictions"]
            ):
                prediction_logger.log({
                    "features": features,
                    "prediction": pred_dict["prediction"],
                    "prediction_class": pred_dict["prediction_class"],
                    "model_version": result["model_version"],
                    "timestamp": start_time,
                    "request_id": request_id,
                })
        
        logger.info(
            f"Batch prediction successful",
            extra={
                "request_id": request_id,
                "model_version": result["model_version"],
                "batch_size": batch_size,
                "latency_ms": latency * 1000,
            }
        )
        return BatchPredictionResponse(**result)
    
    except ValueError as e:
        metrics.prediction_errors_total.labels(
            endpoint="/v1/predict/batch",
            error_type="validation"
        ).inc()
        logger.warning(f"Validation error: {e}", extra={"request_id": request_id})
        raise HTTPException(status_code=400, detail=str(e))
    
    except RuntimeError as e:
        metrics.prediction_errors_total.labels(
            endpoint="/v1/predict/batch",
            error_type="runtime"
        ).inc()
        logger.error(f"Runtime error: {e}", extra={"request_id": request_id})
        raise HTTPException(status_code=503, detail=str(e))
    
    except Exception as e:
        metrics.prediction_errors_total.labels(
            endpoint="/v1/predict/batch",
            error_type="internal"
        ).inc()
        logger.error(f"Unexpected error: {e}", exc_info=True, extra={"request_id": request_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/model/info", response_model=ModelInfoResponse)
async def get_model_info(predictor: Predictor = Depends(get_predictor)) -> ModelInfoResponse:
    """
    Get information about the currently loaded model.
    
    Returns model version, schema, features, and metadata.
    """
    try:
        info = predictor.model_loader.get_model_info()
        return ModelInfoResponse(**info)
    
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
