import logging
from typing import Any
import pandas as pd

logger: logging.Logger = logging.getLogger(__name__)


class SchemaValidator:
    """
    Validates data against model schemas.
    Lightweight version for API usage - no schema generation.
    """

    @staticmethod
    def validate_schema_compatibility(new_data: pd.DataFrame, existing_schema: dict[str, Any], target_column: str | None = None ) -> tuple[bool, list[str]]:
        """
        Validate if new data is compatible with existing schema.
        
        Args:
            new_data: New DataFrame to validate
            existing_schema: Existing schema to validate against
            target_column: Optional target column to exclude from validation
        
        Returns:
            Tuple of (is_compatible, list_of_errors)
        """
        errors: list[str] = []
        feature_columns: list[str] = ([col for col in new_data.columns if col != target_column] if target_column else list(new_data.columns))
        if "n_features" in existing_schema and len(feature_columns) != existing_schema["n_features"]: errors.append(f"Feature count mismatch: {len(feature_columns)} vs {existing_schema['n_features']}")
        
        if "feature_names" in existing_schema:
            expected_names: list[str] = existing_schema["feature_names"]
            if feature_columns != expected_names: errors.append(f"Feature names/order mismatch: {feature_columns} vs {expected_names}")
        
        if "structural_schema" in existing_schema:
            for feature_def in existing_schema["structural_schema"]:
                col_name: str = feature_def["name"]
                if col_name in new_data.columns:
                    expected_dtype: str = feature_def["dtype"]
                    actual_dtype: str = str(new_data[col_name].dtype)
                    if actual_dtype != expected_dtype: errors.append(f"Data type mismatch for '{col_name}': {actual_dtype} vs {expected_dtype}")
        
        is_compatible: bool = len(errors) == 0
        if is_compatible: logger.info("Schema validation passed")
        else:
            logger.error(f"Schema validation failed: {errors}")
        
        return is_compatible, errors
