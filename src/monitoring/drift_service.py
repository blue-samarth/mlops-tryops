import logging
import threading
import time
from typing import Any
import pandas as pd
import numpy as np

from src.monitoring.prediction_logger import PredictionLogger
from src.monitoring.drift_detector import DriftDetector
from src.monitoring import metrics
from src.utils import settings

logger = logging.getLogger(__name__)


class DriftService:
    """
    Background service that periodically checks for drift.
    
    Runs in a separate thread, polls prediction buffer, calculates drift,
    and emits alerts and Prometheus metrics.
    """
    
    def __init__(self, prediction_logger: PredictionLogger, baseline: dict[str, Any] | None = None, model_version: str | None = None,):
        """
        Initialize drift service.
        
        Args:
            prediction_logger: PredictionLogger instance
            baseline: Baseline statistics (can be updated later)
            model_version: Current model version
        """
        self.prediction_logger = prediction_logger
        self.baseline = baseline
        self.model_version = model_version
        
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        
        self.last_check_time: float = 0
        self.last_check_count: int = 0
        
        logger.info("Initialized DriftService")
    
    def update_baseline(self, baseline: dict[str, Any], model_version: str) -> None:
        """
        Update baseline when model changes (hot-reload).
        
        Args:
            baseline: New baseline statistics
            model_version: New model version
        """
        self.baseline = baseline
        self.model_version = model_version
        logger.info(f"Updated baseline to model version {model_version}")
    
    def start(self) -> None:
        """Start drift monitoring background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Drift service already running")
            return
        
        if not settings.ENABLE_DRIFT_DETECTION:
            logger.info("Drift detection disabled in settings")
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._thread.start()
        
        logger.info(
            f"Started drift monitoring (interval: {settings.DRIFT_CHECK_INTERVAL}s, "
            f"window: {settings.DRIFT_WINDOW_SIZE} predictions)"
        )
    
    def stop(self) -> None:
        """Stop drift monitoring background thread."""
        if not self._thread: return
        
        logger.info("Stopping drift monitoring...")
        self._stop_event.set()
        
        if self._thread.is_alive(): self._thread.join(timeout=5)
        
        logger.info("Drift monitoring stopped")
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop running in background thread."""
        while not self._stop_event.is_set():
            try:
                # Check if enough time has passed
                time_since_check = time.time() - self.last_check_time
                
                # Check if enough predictions accumulated
                current_count = self.prediction_logger.get_count()
                predictions_since_check = current_count - self.last_check_count
                
                should_check = (
                    time_since_check >= settings.DRIFT_CHECK_INTERVAL
                    or predictions_since_check >= settings.DRIFT_WINDOW_SIZE
                )
                
                if should_check and current_count >= settings.DRIFT_WINDOW_SIZE:
                    self._run_drift_check()
                    self.last_check_time = time.time()
                    self.last_check_count = current_count
                
                # Update buffer metrics
                buffer_stats = self.prediction_logger.get_statistics()
                metrics.prediction_buffer_size.set(buffer_stats["count"])
                metrics.prediction_buffer_utilization.set(buffer_stats["utilization"])
                
            except Exception as e:
                logger.error(f"Error in drift monitoring loop: {e}", exc_info=True)

            self._stop_event.wait(timeout=60)
    
    def _run_drift_check(self) -> None:
        """
        Run drift detection check.
        
        Retrieves recent predictions, calculates drift scores,
        emits alerts and metrics.
        """
        if not self.baseline:
            logger.warning("No baseline available, skipping drift check")
            return
        
        start_time = time.time()
        
        try:
            # Get recent predictions
            predictions = self.prediction_logger.get_snapshot(window_size=settings.DRIFT_WINDOW_SIZE)
            
            if len(predictions) < settings.DRIFT_WINDOW_SIZE:
                logger.info(
                    f"Not enough predictions for drift check "
                    f"({len(predictions)}/{settings.DRIFT_WINDOW_SIZE})"
                )
                return
            
            logger.info(f"Running drift check on {len(predictions)} predictions")
            
            features_list = [p["features"] for p in predictions]
            prediction_values = np.array([p["prediction"] for p in predictions])
            features_df = pd.DataFrame(features_list)            
            detector = DriftDetector(self.baseline)
            feature_drift = detector.detect_feature_drift(features_df)

            prediction_drift = detector.detect_prediction_drift(prediction_values)

            self._process_drift_results(feature_drift, prediction_drift)

            duration = time.time() - start_time
            metrics.drift_check_duration_seconds.observe(duration)
            
            logger.info(f"Drift check completed in {duration:.2f}s")
        
        except Exception as e:
            logger.error(f"Error running drift check: {e}", exc_info=True)
    
    def _process_drift_results(self, feature_drift: dict[str, dict[str, float | None]], prediction_drift: dict[str, float | None]) -> None:
        """
        Process drift results, emit alerts and metrics.
        
        Args:
            feature_drift: Feature drift results (values can be None if calculation fails)
            prediction_drift: Prediction drift results (values can be None if calculation fails)
        """
        for feature_name, drift_metrics in feature_drift.items():
            psi = drift_metrics.get("psi")
            ks_pvalue = drift_metrics.get("ks_pvalue")
            
            if psi is not None:
                metrics.drift_score.labels(model_version=self.model_version or "unknown", feature=feature_name, metric_type="psi").set(psi)
                
                if psi > settings.DRIFT_PSI_THRESHOLD:
                    logger.warning(
                        f"Feature drift detected: {feature_name}",
                        extra={
                            "feature": feature_name,
                            "psi": psi,
                            "threshold": settings.DRIFT_PSI_THRESHOLD,
                            "model_version": self.model_version,
                        }
                    )
                    
                    metrics.drift_alerts_total.labels(model_version=self.model_version or "unknown", feature=feature_name, drift_type="psi").inc()
            
            if ks_pvalue is not None:
                metrics.drift_score.labels(model_version=self.model_version or "unknown", feature=feature_name, metric_type="ks_pvalue").set(ks_pvalue)
                
                # Alert if KS test shows significant drift (p < threshold)
                if ks_pvalue < settings.DRIFT_KS_THRESHOLD:
                    logger.warning(
                        f"Distribution drift detected (KS test): {feature_name}",
                        extra={
                            "feature": feature_name,
                            "ks_pvalue": ks_pvalue,
                            "threshold": settings.DRIFT_KS_THRESHOLD,
                            "model_version": self.model_version,
                        }
                    )
                    
                    metrics.drift_alerts_total.labels(model_version=self.model_version or "unknown", feature=feature_name, drift_type="ks_test").inc()
        
        # Process prediction drift
        pred_psi = prediction_drift.get("psi")
        if pred_psi is not None:
            metrics.drift_score.labels(model_version=self.model_version or "unknown", feature="prediction", metric_type="psi").set(pred_psi)
            
            if pred_psi > settings.DRIFT_PSI_THRESHOLD:
                logger.warning(
                    "Prediction drift detected",
                    extra={
                        "psi": pred_psi,
                        "threshold": settings.DRIFT_PSI_THRESHOLD,
                        "model_version": self.model_version,
                    }
                )
                
                metrics.drift_alerts_total.labels(model_version=self.model_version or "unknown", feature="prediction", drift_type="psi").inc()
