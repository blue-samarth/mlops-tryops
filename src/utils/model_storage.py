import logging
from datetime import datetime, timezone
from typing import Any

from src.utils.s3_operations import S3Operations

logger: logging.Logger = logging.getLogger(__name__)


class ModelStorage:
    """Handle model artifact storage operations."""

    def __init__(self, s3_ops: S3Operations): self.s3_ops = s3_ops

    def upload_model(self, local_model_path: str, model_version: str, model_format: str = "onnx") -> str:
        """Upload a model file to S3."""
        s3_key: str = f"models/{model_version}.{model_format}"
        success: bool = self.s3_ops.upload_file(
            local_path=local_model_path,
            s3_key=s3_key,
            metadata={
                "model_version": model_version,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
},
            content_type="application/octet-stream",
        )
        if not success: raise RuntimeError(f"Failed to upload model {model_version}")
        return self.s3_ops.get_s3_uri(s3_key)

    def upload_metadata(self, metadata: dict[str, Any], model_version: str) -> str:
        """Upload model metadata to S3."""
        s3_key: str = f"metadata/{model_version}.json"
        success: bool = self.s3_ops.upload_json(metadata, s3_key)
        if not success: raise RuntimeError(f"Failed to upload metadata for {model_version}")
        return self.s3_ops.get_s3_uri(s3_key)

    def upload_baseline(self, baseline_stats: dict[str, Any], model_version: str) -> str:
        """Upload baseline statistics to S3."""
        s3_key: str = f"baselines/{model_version}_baseline.json"
        success: bool = self.s3_ops.upload_json(baseline_stats, s3_key)
        if not success: raise RuntimeError(f"Failed to upload baseline for {model_version}")
        return self.s3_ops.get_s3_uri(s3_key)

    def download_model(self, model_version: str, local_path: str, model_format: str = "onnx") -> bool: return self.s3_ops.download_file(f"models/{model_version}.{model_format}", local_path)
    def get_model_metadata(self, model_version: str) -> dict[str, Any] | None: return self.s3_ops.download_json(f"metadata/{model_version}.json")
    def get_baseline_stats(self, model_version: str) -> dict[str, Any] | None: return self.s3_ops.download_json(f"baselines/{model_version}_baseline.json")

    def list_model_versions(self) -> list[str]:
        """List all available model versions."""
        keys = self.s3_ops.list_objects(prefix="models/")
        versions = [
            key.replace("models/", "").replace(".onnx", "") for key in keys if key.endswith(".onnx")
        ]
        return sorted(versions, reverse=True)
