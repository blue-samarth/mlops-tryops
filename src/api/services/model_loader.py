import logging
import threading
import tempfile
from pathlib import Path
from typing import Any
import onnxruntime as ort

from src.utils import ServingPointerManager, ModelStorage, S3Operations, settings

logger: logging.Logger = logging.getLogger(__name__)


class ModelLoader:
    """
    Manages model loading with hot-reloading support.
    Periodically checks serving pointer and reloads model if version changes.
    """
    
    def __init__(self, s3_bucket: str | None = None, environment: str | None = None):
        """
        Initialize model loader.
        
        Args:
            s3_bucket: S3 bucket name (defaults to settings, ignored in local mode)
            environment: Environment name (defaults to settings)
        """
        self.s3_bucket: str = s3_bucket or settings.S3_BUCKET
        self.environment: str = environment or settings.ENVIRONMENT
        self.local_mode = settings.LOCAL_STORAGE_MODE
        
        if self.local_mode:
            logger.info("Running in local storage mode - S3/ServingPointer disabled")
            self.pointer_manager = None  # type: ignore
            self.model_storage = ModelStorage(s3_ops=None)
        else:
            self.pointer_manager = ServingPointerManager(s3_bucket=self.s3_bucket, environment=self.environment, region=settings.AWS_REGION)
            s3_ops = S3Operations(bucket_name=self.s3_bucket, region_name=settings.AWS_REGION)
            self.model_storage = ModelStorage(s3_ops)

        self.model: ort.InferenceSession | None = None
        self.metadata: dict[str, Any] | None = None
        self.baseline: dict[str, Any] | None = None
        self.current_version: str | None = None
        self.model_lock = threading.Lock()

        self._reload_thread: threading.Thread | None = None
        self._stop_reload = threading.Event()
        
        logger.info(f"Initialized ModelLoader for {self.environment}")
    
    def load_initial_model(self) -> None:
        """Load initial model from serving pointer or local storage."""
        if self.local_mode:
            logger.info("Local storage mode - attempting to load latest model...")
            self._load_latest_local_model()
            return
        
        logger.info("Loading initial model...")
        if self.pointer_manager is None: raise RuntimeError("pointer_manager required for S3 mode")
        pointer = self.pointer_manager.get_current_pointer()
        
        if not pointer:
            logger.warning("No serving pointer found - model will be loaded when available")
            return
        
        self._load_model_from_pointer(pointer)
    
    def _load_latest_local_model(self) -> None:
        """Load the latest model from local storage."""
        # Get list of available models (already sorted by model_storage)
        versions = self.model_storage.list_model_versions()
        
        if not versions:
            logger.warning("No models found in local storage")
            return
        
        # Get latest version (already sorted in reverse order)
        latest_version = versions[0]
        logger.info(f"Found latest model: {latest_version}")
        
        with self.model_lock:
            if latest_version == self.current_version:
                logger.info(f"Model {latest_version} already loaded")
                return
            
            # In local mode, model files are already on disk
            models_dir = Path(settings.LOCAL_STORAGE_PATH) / "models"
            local_model_path = str(models_dir / f"{latest_version}.onnx")
            
            if not Path(local_model_path).exists():
                logger.error(f"Model file not found: {local_model_path}")
                return
            
            logger.info(f"Loading model from {local_model_path}...")
            
            session_options = ort.SessionOptions()
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            
            self.model = ort.InferenceSession(local_model_path, session_options)
            self.metadata = self.model_storage.get_model_metadata(latest_version)
            self.baseline = self.model_storage.get_baseline_stats(latest_version)
            
            if not self.metadata:
                logger.error(f"Failed to load metadata for {latest_version}")
                return
            
            self.current_version = latest_version
            
            logger.info(f"Successfully loaded model {latest_version}")
            logger.info(f"Schema hash: {self.metadata.get('schema', {}).get('schema_hash')}")
            logger.info(f"Metrics: {self.metadata.get('metrics')}")
    
    def _load_model_from_pointer(self, pointer: dict[str, Any]) -> None:
        """
        Load model from serving pointer data.
        
        Args:
            pointer: Serving pointer dictionary
        """
        model_version = pointer["model_version"]
        
        with self.model_lock:
            if model_version == self.current_version:
                logger.info(f"Model {model_version} already loaded")
                return
            
            logger.info(f"Loading model {model_version}...")
            
            # Use system temp directory with proper cleanup
            temp_dir = Path(tempfile.gettempdir()) / "mlops_models"
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_model_path = str(temp_dir / f"{model_version}.onnx")
            
            success = self.model_storage.download_model(model_version=model_version, local_path=local_model_path)
            if not success: raise RuntimeError(f"Failed to download model {model_version}")

            try:
                session_options = ort.SessionOptions()
                session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                
                self.model = ort.InferenceSession(local_model_path, session_options)

                self.metadata = self.model_storage.get_model_metadata(model_version)
                self.baseline = self.model_storage.get_baseline_stats(model_version)
            finally:
                # Clean up temporary file to prevent disk space exhaustion
                try:
                    Path(local_model_path).unlink()
                    logger.debug(f"Cleaned up temp model file: {local_model_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file: {e}")
            
            if not self.metadata: raise RuntimeError(f"Failed to load metadata for {model_version}")
            
            self.current_version = model_version
            
            logger.info(f"Successfully loaded model {model_version}")
            logger.info(f"Schema hash: {self.metadata.get('schema', {}).get('schema_hash')}")
            logger.info(f"Metrics: {self.metadata.get('metrics')}")
    
    def start_hot_reload(self) -> None:
        """Start background thread for hot-reloading."""
        if self.local_mode:
            logger.info("Local storage mode - hot-reload disabled")
            return
        
        if self._reload_thread and self._reload_thread.is_alive():
            logger.warning("Hot-reload thread already running")
            return
        
        self._stop_reload.clear()
        self._reload_thread = threading.Thread(target=self._reload_loop, daemon=True)
        self._reload_thread.start()
        
        logger.info(f"Started hot-reload thread (interval: {settings.MODEL_RELOAD_INTERVAL}s)")
    
    def stop_hot_reload(self) -> None:
        """Stop hot-reload thread."""
        if not self._reload_thread: return
        
        logger.info("Stopping hot-reload thread...")
        self._stop_reload.set()
        
        if self._reload_thread.is_alive(): self._reload_thread.join(timeout=5)
        
        logger.info("Hot-reload thread stopped")
    
    def _reload_loop(self) -> None:
        """Background loop to check for model updates."""
        while not self._stop_reload.is_set():
            try:
                pointer = self.pointer_manager.get_current_pointer()
                
                if pointer:
                    new_version = pointer["model_version"]
                    
                    # Check version inside lock to prevent race condition (TOCTOU)
                    should_reload = False
                    with self.model_lock:
                        if new_version != self.current_version:
                            should_reload = True
                    
                    if should_reload:
                        logger.info(f"Detected new model version: {new_version}")
                        self._load_model_from_pointer(pointer)
                        logger.info(f"Hot-reloaded model from {self.current_version} to {new_version}")
                
            except Exception as e: logger.error(f"Error in reload loop: {e}", exc_info=True)
            self._stop_reload.wait(timeout=settings.MODEL_RELOAD_INTERVAL)
    
    def get_model_info(self) -> dict[str, Any]:
        """
        Get current model information.
        
        Returns:
            Model info dictionary
        """
        with self.model_lock:
            if not self.model or not self.metadata:
                raise RuntimeError("No model loaded")
            
            schema = self.metadata.get("schema", {})
            
            # Get pointer info only if not in local mode
            pointer = None
            if self.pointer_manager is not None:
                pointer = self.pointer_manager.get_current_pointer()
            
            return {
                "model_version": self.current_version,
                "schema_hash": schema.get("schema_hash"),
                "feature_names": schema.get("feature_names", []),
                "n_features": schema.get("n_features"),
                "model_type": self.metadata.get("model_type"),
                "promoted_at": pointer.get("promoted_at") if pointer else None,
                "promoted_by": pointer.get("promoted_by") if pointer else None,
                "metrics": self.metadata.get("metrics"),
            }
    
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        with self.model_lock: return self.model is not None and self.metadata is not None
