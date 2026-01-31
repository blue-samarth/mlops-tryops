from typing import Any
from pydantic import BaseModel, Field, field_validator
import numpy as np

from src.utils import settings


class PredictionRequest(BaseModel):
    """Request model for predictions."""
    
    features: dict[str, Any] = Field(..., description="Feature values as dictionary")
    
    @field_validator('features')
    @classmethod
    def validate_features(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate features is not empty and within size limits."""
        if not v: raise ValueError("Features dictionary cannot be empty")
        
        # Validate per-instance size to prevent DoS (max 100 features)
        if len(v) > 100:
            raise ValueError(f"Too many features ({len(v)}). Maximum 100 features allowed per instance.")
        
        # Validate individual feature names (max 256 chars)
        for key in v.keys():
            if len(str(key)) > 256:
                raise ValueError(f"Feature name too long: {str(key)[:50]}... (max 256 chars)")
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "features": {
                    "age": 45,
                    "income": 75000,
                    "credit_score": 720
                }
            }
        }


class PredictionResponse(BaseModel):
    """Response model for predictions."""
    
    model_version: str = Field(..., description="Model version used for prediction")
    prediction: float = Field(..., description="Predicted probability")
    prediction_class: int = Field(..., description="Predicted class (0 or 1)")
    schema_hash: str = Field(..., description="Schema hash used for validation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "model_version": "v20250125_143022_abc123",
                "prediction": 0.7234,
                "prediction_class": 1,
                "schema_hash": "a1b2c3d4e5f6g7h8"
            }
        }


class BatchPredictionRequest(BaseModel):
    """Request model for batch predictions."""
    
    instances: list[dict[str, Any]] = Field(..., description="List of feature dictionaries")
    
    @field_validator('instances')
    @classmethod
    def validate_instances(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate instances is not empty and has reasonable size."""
        if not v: raise ValueError("Instances list cannot be empty")
        if len(v) > settings.MAX_BATCH_SIZE:
            raise ValueError(f"Batch size cannot exceed {settings.MAX_BATCH_SIZE} instances")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "instances": [
                    {"age": 45, "income": 75000, "credit_score": 720},
                    {"age": 32, "income": 55000, "credit_score": 680}
                ]
            }
        }


class BatchPredictionResponse(BaseModel):
    """Response model for batch predictions."""
    
    model_version: str = Field(..., description="Model version used for prediction")
    predictions: list[dict[str, Any]] = Field(..., description="List of predictions")
    schema_hash: str = Field(..., description="Schema hash used for validation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "model_version": "v20250125_143022_abc123",
                "predictions": [
                    {"prediction": 0.7234, "prediction_class": 1},
                    {"prediction": 0.4521, "prediction_class": 0}
                ],
                "schema_hash": "a1b2c3d4e5f6g7h8"
            }
        }


class HealthResponse(BaseModel):
    """Response model for health check."""
    
    status: str = Field(..., description="Service status")
    model_version: str | None = Field(None, description="Current model version")
    model_loaded: bool = Field(..., description="Whether model is loaded")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "model_version": "v20250125_143022_abc123",
                "model_loaded": True
            }
        }


class ModelInfoResponse(BaseModel):
    """Response model for model information."""
    
    model_version: str = Field(..., description="Current model version")
    schema_hash: str = Field(..., description="Schema hash")
    feature_names: list[str] = Field(..., description="Expected feature names")
    n_features: int = Field(..., description="Number of features")
    model_type: str = Field(..., description="Model type")
    promoted_at: str | None = Field(None, description="Promotion timestamp")
    promoted_by: str | None = Field(None, description="Who promoted the model")
    
    class Config:
        json_schema_extra = {
            "example": {
                "model_version": "v20250125_143022_abc123",
                "schema_hash": "a1b2c3d4e5f6g7h8",
                "feature_names": ["age", "income", "credit_score"],
                "n_features": 3,
                "model_type": "logistic_regression",
                "promoted_at": "2025-01-25T14:30:22Z",
                "promoted_by": "data_scientist"
            }
        }
