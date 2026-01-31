from fastapi import APIRouter, Depends
from src.api.schemas.prediction import HealthResponse
from src.api.services.model_loader import ModelLoader
from src.api.dependencies import get_model_loader

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(model_loader: ModelLoader = Depends(get_model_loader)) -> HealthResponse:
    """
    Health check endpoint.
    Returns current service status and model information.
    """
    is_loaded = model_loader.is_loaded()
    
    return HealthResponse(
        status="healthy" if is_loaded else "initializing",
        model_version=model_loader.current_version,
        model_loaded=is_loaded,
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness_check(model_loader: ModelLoader = Depends(get_model_loader)) -> HealthResponse:
    """
    Readiness check endpoint.
    Returns 200 only if model is loaded and ready to serve.
    """
    is_loaded = model_loader.is_loaded()
    
    if not is_loaded:
        return HealthResponse(
            status="not_ready",
            model_version=None,
            model_loaded=False,
        )
    
    return HealthResponse(
        status="ready",
        model_version=model_loader.current_version,
        model_loaded=True,
    )
