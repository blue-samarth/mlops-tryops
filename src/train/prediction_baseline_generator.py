import logging
from typing import Any
import numpy as np

logger: logging.Logger = logging.getLogger(__name__)


class PredictionBaselineGenerator:
    """Generate baseline statistics for predictions only."""

    @staticmethod
    def generate_prediction_baseline(predictions: np.ndarray) -> dict[str, Any]:
        """
        Generate baseline statistics for model predictions.
        
        Args:
            predictions: Model predictions array
        
        Returns:
            Prediction statistics dictionary
        """
        logger.info(f"Generating prediction baseline for {len(predictions)} samples")

        if len(predictions.shape) == 1 or predictions.shape[1] == 1:
            preds = predictions.flatten()
            return {
                "type": "binary_classification",
                "mean_probability": float(preds.mean()),
                "std_probability": float(preds.std()),
                "percentiles": {
                    "p25": float(np.percentile(preds, 25)),
                    "p50": float(np.percentile(preds, 50)),
                    "p75": float(np.percentile(preds, 75)),
                    "p95": float(np.percentile(preds, 95)),
                },
                "histogram": PredictionBaselineGenerator._compute_histogram(preds, bins=20),
            }
        else:
            return {
                "type": "multiclass_classification",
                "n_classes": int(predictions.shape[1]),
                "class_distributions": [
                    {
                        "class_idx": i,
                        "mean": float(predictions[:, i].mean()),
                        "std": float(predictions[:, i].std()),
                    }
                    for i in range(predictions.shape[1])
                ],
            }

    @staticmethod
    def _compute_histogram(data: np.ndarray, bins: int = 20) -> dict[str, Any]:
        """Compute histogram for drift detection."""
        counts, bin_edges = np.histogram(data, bins=bins)
        return {
            "counts": counts.tolist(),
            "bin_edges": bin_edges.tolist(),
        }
