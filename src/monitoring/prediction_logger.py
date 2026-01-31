"""
Thread-safe circular buffer for prediction logging.
Stores recent predictions in memory for drift detection.
"""
import logging
import threading
from collections import deque
from typing import Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PredictionLogger:
    """
    Thread-safe circular buffer for storing recent predictions.
    
    Uses deque with maxlen for automatic eviction of old predictions.
    All operations are thread-safe for concurrent API requests.
    """
    
    def __init__(self, max_size: int = 10000):
        """
        Initialize prediction logger.
        
        Args:
            max_size: Maximum number of predictions to store (default: 10000)
        """
        self.buffer: deque = deque(maxlen=max_size)
        self.lock = threading.Lock()
        self.max_size = max_size
        
        logger.info(f"Initialized PredictionLogger with buffer size {max_size}")
    
    def log(self, prediction_data: dict[str, Any]) -> None:
        """
        Log a prediction to the buffer.
        
        Args:
            prediction_data: Dictionary containing:
                - features: dict of feature values
                - prediction: float (probability)
                - prediction_class: int
                - model_version: str
                - timestamp: datetime (added if not present)
                - request_id: str (optional)
        """
        if "timestamp" not in prediction_data:
            prediction_data["timestamp"] = datetime.utcnow()
        
        with self.lock:
            self.buffer.append(prediction_data)
    
    def get_snapshot(self, window_size: int | None = None) -> list[dict[str, Any]]:
        """
        Get a snapshot of recent predictions.
        
        Args:
            window_size: Number of recent predictions to return.
                        If None, returns all predictions in buffer.
        
        Returns:
            List of prediction dictionaries (most recent last)
        """
        import copy
        
        with self.lock:
            if window_size is None:
                # Deep copy to prevent external mutation
                return copy.deepcopy(list(self.buffer))
            else:
                # Get last N predictions with deep copy
                snapshot = list(self.buffer)[-window_size:] if len(self.buffer) >= window_size else list(self.buffer)
                return copy.deepcopy(snapshot)
    
    def get_count(self) -> int:
        """
        Get current number of predictions in buffer.
        
        Returns:
            Number of predictions stored
        """
        with self.lock:
            return len(self.buffer)
    
    def clear(self) -> None:
        """
        Clear all predictions from buffer.
        Useful for testing or after drift analysis.
        """
        with self.lock:
            self.buffer.clear()
            logger.info("Prediction buffer cleared")
    
    def get_statistics(self) -> dict[str, Any]:
        """
        Get buffer statistics.
        
        Returns:
            Dictionary with buffer metadata
        """
        with self.lock:
            count = len(self.buffer)
            if count == 0:
                return {
                    "count": 0,
                    "max_size": self.max_size,
                    "utilization": 0.0,
                    "oldest": None,
                    "newest": None,
                }
            
            oldest = self.buffer[0]["timestamp"]
            newest = self.buffer[-1]["timestamp"]
            
            return {
                "count": count,
                "max_size": self.max_size,
                "utilization": count / self.max_size,
                "oldest": oldest.isoformat() if isinstance(oldest, datetime) else oldest,
                "newest": newest.isoformat() if isinstance(newest, datetime) else newest,
                "time_span_seconds": (newest - oldest).total_seconds() if isinstance(oldest, datetime) and isinstance(newest, datetime) else None,
            }
