import logging
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from src.utils.s3_operations import S3Operations
from src.utils.config import settings

logger: logging.Logger = logging.getLogger(__name__)


class ModelStorage:
    """Handle model artifact storage operations.
    
    Supports both S3 (production) and local filesystem (development) storage.
    Set LOCAL_STORAGE_MODE=true in environment to use local storage.
    """

    def __init__(self, s3_ops: S3Operations | None = None):
        self.s3_ops = s3_ops
        self.local_mode = settings.LOCAL_STORAGE_MODE
        
        if self.local_mode:
            self.storage_path = Path(settings.LOCAL_STORAGE_PATH)
            logger.info(f"Using local storage mode: {self.storage_path}")
            # Create directories
            (self.storage_path / "models").mkdir(parents=True, exist_ok=True)
            (self.storage_path / "metadata").mkdir(parents=True, exist_ok=True)
            (self.storage_path / "baselines").mkdir(parents=True, exist_ok=True)
        elif s3_ops is None:
            raise ValueError("s3_ops required when LOCAL_STORAGE_MODE=false")

    def upload_model(self, local_model_path: str, model_version: str, model_format: str = "onnx") -> str:
        """Upload a model file to storage (S3 or local filesystem)."""
        if self.local_mode:
            try:
                dest_path = self.storage_path / "models" / f"{model_version}.{model_format}"
                shutil.copy2(local_model_path, dest_path)
                logger.info(f"Saved model to {dest_path}")
                return str(dest_path)
            except (OSError, IOError) as e:
                raise RuntimeError(f"Failed to save model {model_version}: {e}")
        else:
            if self.s3_ops is None: raise RuntimeError("s3_ops required for S3 mode")
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
        """Upload model metadata to storage (S3 or local filesystem)."""
        if self.local_mode:
            try:
                dest_path = self.storage_path / "metadata" / f"{model_version}.json"
                with open(dest_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
                logger.info(f"Saved metadata to {dest_path}")
                return str(dest_path)
            except (OSError, IOError, TypeError) as e:
                raise RuntimeError(f"Failed to save metadata for {model_version}: {e}")
        else:
            if self.s3_ops is None: raise RuntimeError("s3_ops required for S3 mode")
            s3_key: str = f"metadata/{model_version}.json"
            success: bool = self.s3_ops.upload_json(metadata, s3_key)
            if not success: raise RuntimeError(f"Failed to upload metadata for {model_version}")
            return self.s3_ops.get_s3_uri(s3_key)

    def upload_baseline(self, baseline_stats: dict[str, Any], model_version: str) -> str:
        """Upload baseline statistics to storage (S3 or local filesystem)."""
        if self.local_mode:
            try:
                dest_path = self.storage_path / "baselines" / f"{model_version}_baseline.json"
                with open(dest_path, 'w') as f:
                    json.dump(baseline_stats, f, indent=2)
                logger.info(f"Saved baseline to {dest_path}")
                return str(dest_path)
            except (OSError, IOError, TypeError) as e:
                raise RuntimeError(f"Failed to save baseline for {model_version}: {e}")
        else:
            if self.s3_ops is None: raise RuntimeError("s3_ops required for S3 mode")
            s3_key: str = f"baselines/{model_version}_baseline.json"
            success: bool = self.s3_ops.upload_json(baseline_stats, s3_key)
            if not success: raise RuntimeError(f"Failed to upload baseline for {model_version}")
            return self.s3_ops.get_s3_uri(s3_key)

    def download_model(self, model_version: str, local_path: str, model_format: str = "onnx") -> bool:
        """Download model from storage."""
        if self.local_mode:
            source_path = self.storage_path / "models" / f"{model_version}.{model_format}"
            if not source_path.exists(): return False
            shutil.copy2(source_path, local_path)
            return True
        else:
            if self.s3_ops is None: raise RuntimeError("s3_ops required for S3 mode")
            return self.s3_ops.download_file(f"models/{model_version}.{model_format}", local_path)
    
    def get_model_metadata(self, model_version: str) -> dict[str, Any] | None:
        """Get model metadata from storage."""
        if self.local_mode:
            metadata_path = self.storage_path / "metadata" / f"{model_version}.json"
            if not metadata_path.exists(): return None
            with open(metadata_path, 'r') as f:
                return json.load(f)
        else:
            if self.s3_ops is None: raise RuntimeError("s3_ops required for S3 mode")
            return self.s3_ops.download_json(f"metadata/{model_version}.json")
    
    def get_baseline_stats(self, model_version: str) -> dict[str, Any] | None:
        """Get baseline statistics from storage."""
        if self.local_mode:
            baseline_path = self.storage_path / "baselines" / f"{model_version}_baseline.json"
            if not baseline_path.exists(): return None
            with open(baseline_path, 'r') as f:
                return json.load(f)
        else:
            if self.s3_ops is None: raise RuntimeError("s3_ops required for S3 mode")
            return self.s3_ops.download_json(f"baselines/{model_version}_baseline.json")

    def list_model_versions(self) -> list[str]:
        """List all available model versions."""
        if self.local_mode:
            models_dir = self.storage_path / "models"
            if not models_dir.exists(): return []
            versions = [f.stem for f in models_dir.glob("*.onnx")]
            return sorted(versions, reverse=True)
        else:
            if self.s3_ops is None: raise RuntimeError("s3_ops required for S3 mode")
            keys = self.s3_ops.list_objects(prefix="models/")
            versions = [
                key.replace("models/", "").replace(".onnx", "") for key in keys if key.endswith(".onnx")
            ]
            return sorted(versions, reverse=True)
