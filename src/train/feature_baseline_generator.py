import logging
from typing import Any
import numpy as np
import pandas as pd

logger: logging.Logger = logging.getLogger(__name__)


class FeatureBaselineGenerator:
    """Generate baseline statistics for features only."""

    @staticmethod
    def generate_feature_baseline(features: pd.DataFrame) -> dict[str, Any]:
        """
        Generate baseline statistics for features.
        
        Args:
            features: Feature DataFrame
        
        Returns:
            Feature statistics dictionary
        """
        logger.info(f"Generating feature baseline for {len(features)} samples")

        feature_stats: dict[str, Any] = {}

        for col in features.columns:
            if pd.api.types.is_numeric_dtype(features[col]):
                feature_stats[col] = {
                    "type": "numeric",
                    "mean": float(features[col].mean()),
                    "std": float(features[col].std()),
                    "min": float(features[col].min()),
                    "max": float(features[col].max()),
                    "percentiles": {
                        "p25": float(features[col].quantile(0.25)),
                        "p50": float(features[col].quantile(0.50)),
                        "p75": float(features[col].quantile(0.75)),
                        "p95": float(features[col].quantile(0.95)),
                    },
                    "missing_rate": float(features[col].isnull().mean()),
                }
            else:
                value_counts: pd.Series = features[col].value_counts(normalize=True)
                feature_stats[col] = {
                    "type": "categorical",
                    "n_unique": int(features[col].nunique()),
                    "missing_rate": float(features[col].isnull().mean()),
                    "top_categories": value_counts.head(10).to_dict(),
                }

        logger.info(f"Generated baseline for {len(feature_stats)} features")
        return {
            "n_samples": len(features),
            "feature_statistics": feature_stats,
        }
