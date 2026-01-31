import logging
from datetime import datetime, timezone
from typing import Any
from src.utils.s3_operations import S3Operations

logger: logging.Logger = logging.getLogger(__name__)

class ServingPointerManager:
    """
    Manage serving pointers for explicit model versioning.
    This implements the "Single Source of Truth" pattern where
    s3://bucket/serving/production.json points to the current model.
    """
    def __init__(self, s3_bucket: str, environment: str = "production", region: str = "us-east-1"):
        """
        Initialize serving pointer manager.
        Args:
            s3_bucket: S3 bucket name
            environment: Environment name (production, staging, etc.)
            region: AWS region
        """
        self.s3_ops: S3Operations = S3Operations(bucket_name=s3_bucket, region_name=region)
        self.environment: str = environment
        self.pointer_key: str = f"serving/{environment}.json"
        self.history_prefix: str = f"serving/history/{environment}_"
        logger.info(f"Initialized ServingPointerManager for {environment}")

    def get_current_pointer(self) -> dict[str, Any] | None:
        """
        Get the current serving pointer.
        Returns:
            Pointer data or None if not found
        """
        pointer: dict[str, Any] | None = self.s3_ops.download_json(self.pointer_key)
        if pointer: logger.info(f"Current {self.environment} model: {pointer.get('model_version')}")
        else:
            logger.warning(f"No serving pointer found at {self.pointer_key}")
        return pointer

    def promote_model(self, model_version: str, promoted_by: str = "system", promotion_reason: str = "", ) -> dict[str, Any]:
        """
        Promote a model to the serving environment.
        This is an atomic operation that:
        1. Saves current pointer to history
        2. Updates pointer to new model
        3. Validates new model exists
        Args:
            model_version: Model version to promote (e.g., v20250118_120000_abc123)
            promoted_by: Who/what promoted the model
            promotion_reason: Reason for promotion
        Returns:
            New pointer data
        Raises:
            ValueError: If model doesn't exist
        """
        if not model_version.startswith("v"):
            raise ValueError(
                f"Invalid model version format: {model_version}. "
                f"Expected format: v20250118_120000_abc123" 
            )
        model_key: str = f"models/{model_version}.onnx"
        metadata_key: str = f"metadata/{model_version}.json"
        baseline_key: str = f"baselines/{model_version}_baseline.json"

        if not self.s3_ops.object_exists(model_key): raise ValueError(f"Model not found: {model_key}")
        if not self.s3_ops.object_exists(metadata_key): raise ValueError(f"Metadata not found: {metadata_key}")
        if not self.s3_ops.object_exists(baseline_key): raise ValueError(f"Baseline not found: {baseline_key}")

        current_pointer: dict[str, Any] | None = self.get_current_pointer()
        previous_version: str | None = current_pointer.get("model_version") if current_pointer else None
        metadata: dict[str, Any] | None = self.s3_ops.download_json(metadata_key)
        assert isinstance(metadata, dict)

        required_fields: list[str] = ["schema", "metrics", "model_type"]
        for field in required_fields:
            if field not in metadata: raise ValueError(f"Invalid metadata: missing '{field}' field")

        if current_pointer:
            timestamp: str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            history_key: str = f"{self.history_prefix}{timestamp}.json"
            self.s3_ops.upload_json(current_pointer, history_key)
            logger.info(f"Saved previous pointer to history: {history_key}")

        new_pointer: dict[str, Any] = {
            "model_version": model_version,
            "model_path": self.s3_ops.get_s3_uri(model_key),
            "metadata_path": self.s3_ops.get_s3_uri(metadata_key),
            "baseline_path": self.s3_ops.get_s3_uri(baseline_key),
            "schema_hash": metadata.get("schema", {}).get("schema_hash") if isinstance(metadata, dict) else None,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "promoted_by": promoted_by,
            "promotion_reason": promotion_reason,
            "previous_version": previous_version,
            "rollback_to": previous_version,
            "environment": self.environment,
            "approved": True
        }

        success: bool = self.s3_ops.upload_json(new_pointer, self.pointer_key)
        if not success: raise RuntimeError(f"Failed to update serving pointer: {self.pointer_key}")
        logger.info(f"Promoted {model_version} to {self.environment} (previous: {previous_version})")
        return new_pointer

    def rollback(self) -> dict[str, Any]:
        """
        Rollback to the previous model version.
        Returns:
            Pointer data after rollback
        Raises:
            ValueError: If no previous version exists
        """
        current_pointer: dict[str, Any] | None = self.get_current_pointer()
        if not current_pointer: raise ValueError("No current pointer found - cannot rollback")

        previous_version: str | None = current_pointer.get("previous_version")
        if not previous_version: raise ValueError("No previous version in pointer - cannot rollback")

        logger.warning(f"Rolling back from {current_pointer['model_version']} to {previous_version}")
        return self.promote_model(model_version=previous_version, promoted_by="system_rollback", promotion_reason=f"Rollback from {current_pointer['model_version']}",)

    def get_promotion_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get promotion history.
        Args:
            limit: Maximum number of history entries to return
        Returns:
            List of historical pointers (most recent first)
        """
        history_keys: list[str] = self.s3_ops.list_objects(self.history_prefix)
        history_keys.sort(reverse=True)  # Most recent first

        history: list[dict[str, Any]] = []
        for key in history_keys[:limit]:
            pointer = self.s3_ops.download_json(key)
            if pointer: history.append(pointer)

        logger.info(f"Retrieved {len(history)} history entries")
        return history

    def validate_pointer(self, pointer: dict[str, Any]) -> bool:
        """
        Validate that a pointer's referenced files exist.
        Args:
            pointer: Pointer data to validate
        Returns:
            True if all files exist, False otherwise
        """
        required_keys: list[str] = ["model_path", "metadata_path", "baseline_path"]
        for key in required_keys:
            if key not in pointer:
                logger.error(f"Missing required key in pointer: {key}")
                return False

            s3_uri: str = pointer[key]
            if not s3_uri.startswith(f"s3://{self.s3_ops.bucket_name}/"):
                logger.error(f"Invalid S3 URI: {s3_uri}")
                return False

            s3_key: str = s3_uri.replace(f"s3://{self.s3_ops.bucket_name}/", "")
            if not self.s3_ops.object_exists(s3_key):
                logger.error(f"Referenced file does not exist: {s3_uri}")
                return False

        logger.info("Pointer validation passed")
        return True
