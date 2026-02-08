import hashlib
import json
import logging
from typing import Any
import numpy as np
import pandas as pd

from src.utils.schema_validator import SchemaValidator

logger: logging.Logger = logging.getLogger(__name__)

class SchemaGenerator:
    """
    Generate and manage data schemas for training datasets.
    """

    @staticmethod
    def generate_schema(data: pd.DataFrame, target_column: str | None = None) -> dict[str, Any]:
        """
        Generate schema with separated structural and descriptive components.
        
        Args:
            data: Input DataFrame
            target_column: Optional target column to exclude from schema
        
        Returns:
            Schema dictionary with structural_schema, descriptive_stats, and hash
        """
        feature_columns: list[str] = (
            [col for col in data.columns if col != target_column]
            if target_column
            else list(data.columns)
        )

        structural_schema: list[dict[str, Any]] = []
        descriptive_stats: dict[str, Any] = {}

        for idx, column in enumerate(feature_columns):
            col_data = data[column]
            dtype_str: str = str(col_data.dtype)

            structural_schema.append({
                "name": column,
                "position": idx,
                "dtype": dtype_str,
            })

            descriptive_stats[column] = {
                "num_unique": int(col_data.nunique()),
                "num_missing": int(col_data.isnull().sum()),
                "missing_rate": float(col_data.isnull().mean()),
            }

            if np.issubdtype(col_data.dtype, np.number):
                descriptive_stats[column].update({
                    "type": "numeric",
                    "min": float(col_data.min()),
                    "max": float(col_data.max()),
                    "mean": float(col_data.mean()),
                    "std": float(col_data.std()),
                })
            else:
                descriptive_stats[column]["type"] = "categorical"

        schema_hash: str = SchemaGenerator._compute_structural_hash(structural_schema)

        logger.info(f"Generated schema for {len(feature_columns)} features (hash: {schema_hash})")

        return {
            "structural_schema": structural_schema,
            "descriptive_stats": descriptive_stats,
            "schema_hash": schema_hash,
            "n_features": len(feature_columns),
            "feature_names": feature_columns,
        }

    @staticmethod
    def _compute_structural_hash(structural_schema: list[dict[str, Any]]) -> str:
        """
        Compute hash of ONLY structural elements.
        Changes to stats (min/max/mean) do NOT change hash.
        
        Args:
            structural_schema: List of structural feature definitions
        
        Returns:
            32-character hash of structure (128 bits for collision resistance)
        """
        schema_str: str = json.dumps(structural_schema, sort_keys=True)
        return hashlib.sha256(schema_str.encode()).hexdigest()[:32]
    
    @staticmethod
    def validate_schema_compatibility(
        new_data: pd.DataFrame, 
        existing_schema: dict[str, Any], 
        target_column: str | None = None
    ) -> tuple[bool, list[str]]:
        """
        Validate if new data is compatible with existing schema.
        Delegates to SchemaValidator for consistency.
        
        Args:
            new_data: New DataFrame to validate
            existing_schema: Existing schema to validate against
            target_column: Optional target column to exclude from validation
        
        Returns:
            Tuple of (is_compatible, list_of_errors)
        """
        return SchemaValidator.validate_schema_compatibility(
            new_data=new_data,
            existing_schema=existing_schema,
            target_column=target_column
        )
