import logging
from typing import Any
import numpy as np
import pandas as pd

from src.api.services.model_loader import ModelLoader
from src.train.schema_generator import SchemaGenerator

logger: logging.Logger = logging.getLogger(__name__)


class Predictor:
    """
    Handles model predictions with schema validation.
    """
    
    def __init__(self, model_loader: ModelLoader): self.model_loader = model_loader
    
    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Make prediction for single instance.
        
        Args:
            features: Feature dictionary
        
        Returns:
            Prediction result with probability and class
        
        Raises:
            RuntimeError: If model not loaded
            ValueError: If schema validation fails
        """
        if not self.model_loader.is_loaded(): raise RuntimeError("Model not loaded")

        df: pd.DataFrame = pd.DataFrame([features])
        self._validate_schema(df)

        model_info: dict[str, Any] = self.model_loader.get_model_info()
        feature_names: list[str] = model_info["feature_names"]

        try:
            X = df[feature_names].values.astype(np.float32)
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"Invalid feature values: {e}")
        
        # Validate for inf/nan values (security check)
        if not np.isfinite(X).all():
            invalid_features = [
                feature_names[i]
                for i in range(X.shape[1])
                if not np.isfinite(X[:, i]).all()
            ]
            raise ValueError(f"Invalid values (inf/nan) in features: {invalid_features}")

        with self.model_loader.model_lock:
            model = self.model_loader.model
            if model is None:
                raise RuntimeError("Model not loaded yet — cannot get input/output names")
            
            input_name  = model.get_inputs()[0].name
            label_name  = model.get_outputs()[0].name
            prob_name   = model.get_outputs()[1].name
            
            outputs = model.run([label_name, prob_name], {input_name: X})
            
            predicted_class = int(outputs[0][0])
            probabilities = outputs[1][0]
            
            if len(probabilities) == 2: probability = float(probabilities[1])
            else: probability = float(probabilities[predicted_class])
        
        return {
            "model_version": self.model_loader.current_version,
            "prediction": probability,
            "prediction_class": predicted_class,
            "schema_hash": model_info["schema_hash"],
        }
    
    def predict_batch(self, instances: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Make predictions for multiple instances.
        
        Args:
            instances: List of feature dictionaries
        
        Returns:
            Batch prediction results
        
        Raises:
            RuntimeError: If model not loaded
            ValueError: If schema validation fails
        """
        if not self.model_loader.is_loaded(): raise RuntimeError("Model not loaded")

        df: pd.DataFrame = pd.DataFrame(instances)
        self._validate_schema(df)

        model_info: dict[str, Any] = self.model_loader.get_model_info()
        feature_names: list[str] = model_info["feature_names"]

        try:
            X: np.ndarray = df[feature_names].values.astype(np.float32)
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"Invalid feature values in batch: {e}")
        
        # Validate for inf/nan values (security check)
        if not np.isfinite(X).all():
            invalid_features = [
                feature_names[i]
                for i in range(X.shape[1])
                if not np.isfinite(X[:, i]).all()
            ]
            raise ValueError(f"Invalid values (inf/nan) in batch features: {invalid_features}")

        with self.model_loader.model_lock:
            model = self.model_loader.model
            if model is None:
                raise RuntimeError("Model not loaded yet — cannot get input/output names")
            
            input_name = model.get_inputs()[0].name
            label_name = model.get_outputs()[0].name
            prob_name = model.get_outputs()[1].name
            
            outputs = model.run([label_name, prob_name], {input_name: X} )
            
            predicted_classes = outputs[0]
            probabilities = outputs[1]

            predictions = []
            for i in range(len(instances)):
                predicted_class = int(predicted_classes[i])
                probs = probabilities[i]
                
                if len(probs) == 2: probability = float(probs[1])
                else:
                    probability = float(probs[predicted_class])
                
                predictions.append({"prediction": probability, "prediction_class": predicted_class, })
        
        return {
            "model_version": self.model_loader.current_version,
            "predictions": predictions,
            "schema_hash": model_info["schema_hash"],
        }
    
    def _validate_schema(self, df: pd.DataFrame) -> None:
        """
        Validate dataframe against model schema.
        
        Args:
            df: DataFrame to validate
        
        Raises:
            ValueError: If validation fails
        """
        metadata: dict[str, Any] | None = self.model_loader.metadata
        if not metadata: raise RuntimeError("Model metadata not available")

        schema = metadata.get("schema")
        if not schema: raise RuntimeError("Model schema not available")
        
        is_compatible, errors = SchemaGenerator.validate_schema_compatibility(new_data=df, existing_schema=schema)

        if not is_compatible:
            error_msg = "; ".join(errors)
            raise ValueError(f"Schema validation failed: {error_msg}")
