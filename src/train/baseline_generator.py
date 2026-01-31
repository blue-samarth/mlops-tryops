import logging
from typing import Any
import numpy as np
import pandas as pd

from src.train.feature_baseline_generator import FeatureBaselineGenerator
from src.train.prediction_baseline_generator import PredictionBaselineGenerator

logger: logging.Logger = logging.getLogger(__name__)


class BaselineGenerator:
    """Unified baseline generator composing feature and prediction baselines."""

    def __init__(self, features: pd.DataFrame, predictions: np.ndarray | None = None):
        """
        Initialize baseline generator.
        
        Args:
            features: Feature DataFrame
            predictions: Model predictions (optional)
        """
        self.features: pd.DataFrame = features
        self.predictions: np.ndarray | None = predictions
        logger.info(f"Initialized baseline generator with {len(features)} samples")

    def generate_baseline(self) -> dict[str, Any]:
        """
        Generate complete baseline statistics.
        
        Returns:
            Baseline statistics dictionary
        """
        baseline: dict[str, Any] = FeatureBaselineGenerator.generate_feature_baseline(self.features)

        if self.predictions is not None:
            baseline["prediction_statistics"] = PredictionBaselineGenerator.generate_prediction_baseline(
                self.predictions
            )

        logger.info("Generated complete baseline statistics")
        return baseline
