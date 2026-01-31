from functools import lru_cache

from src.api.services.model_loader import ModelLoader
from src.api.services.predictor import Predictor
from src.monitoring.prediction_logger import PredictionLogger
from src.monitoring.drift_service import DriftService
from src.utils import settings


@lru_cache()
def get_model_loader() -> ModelLoader: 
    return ModelLoader()


@lru_cache()
def get_prediction_logger() -> PredictionLogger:
    """
    Get PredictionLogger singleton.
    
    Returns:
        PredictionLogger instance
    """
    return PredictionLogger(max_size=settings.DRIFT_WINDOW_SIZE * 10)


@lru_cache()
def get_drift_service() -> DriftService:
    """
    Get DriftService singleton.
    
    Returns:
        DriftService instance
    """
    prediction_logger = get_prediction_logger()
    return DriftService(prediction_logger)


def get_predictor() -> Predictor:
    """
    Get Predictor instance.
    
    Returns:
        Predictor instance
    """
    model_loader = get_model_loader()
    return Predictor(model_loader)

