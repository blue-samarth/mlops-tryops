import time
import logging
import hashlib
import subprocess
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import onnx
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

from src.utils import S3Operations, settings
from src.utils.model_storage import ModelStorage
from src.train.schema_generator import SchemaGenerator
from src.train.baseline_generator import BaselineGenerator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger: logging.Logger = logging.getLogger(__name__)


def generate_model_version(prefix: str = "v") -> str:
    """Generate unique model version string."""
    timestamp: str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    hash_input: bytes = f"{timestamp}_{datetime.now(timezone.utc).microsecond}".encode()
    short_hash: str = hashlib.sha256(hash_input).hexdigest()[:6]
    return f"{prefix}{timestamp}_{short_hash}"


def get_git_commit() -> str | None:
    """Get current git commit hash."""
    try:
        result: subprocess.CompletedProcess = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


class ModelTrainer:
    """Main training pipeline."""
    
    def __init__(self, s3_bucket: str | None = None):
        """
        Initialize trainer.
        
        Args:
            s3_bucket: S3 bucket name (defaults to settings)
        """
        self.s3_bucket: str = s3_bucket or settings.S3_BUCKET
        s3_ops: S3Operations = S3Operations(bucket_name=self.s3_bucket, region_name=settings.AWS_REGION)
        self.model_storage: ModelStorage = ModelStorage(s3_ops)
        self.model_version: str = generate_model_version()
        self.git_commit: str | None = get_git_commit()
        
        logger.info(f"Initialized trainer for version: {self.model_version}")
    
    def train(self, data_path: str, target_column: str = "target", test_size: float = 0.2, random_state: int = 42, ) -> dict[str, Any]:
        """
        Complete training pipeline.
        Args:
            data_path: Path to training data CSV
            target_column: Name of target column
            test_size: Test split ratio
            random_state: Random seed
        Returns:
            Training results dictionary
        """
        start_time: float = time.time()
        logger.info(f"Loading data from {data_path}")
        
        df: pd.DataFrame = pd.read_csv(data_path)
        X: pd.DataFrame = df.drop(columns=[target_column])
        y: pd.Series = df[target_column]

        logger.info("Generating feature schema...")
        schema: dict[str, Any] = SchemaGenerator.generate_schema(X, target_column=None)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)
        logger.info(f"Train: {len(X_train)} samples, Test: {len(X_test)} samples")
        
        logger.info("Training Logistic Regression model...")
        model: LogisticRegression = LogisticRegression(max_iter=1000, random_state=random_state)
        model.fit(X_train, y_train)
        
        y_pred: np.ndarray = model.predict(X_test)
        y_proba: np.ndarray = model.predict_proba(X_test)[:, 1]
        
        metrics: dict[str, float] = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(precision_score(y_test, y_pred, average='binary')),
            "recall": float(recall_score(y_test, y_pred, average='binary')),
            "f1_score": float(f1_score(y_test, y_pred, average='binary')),
            "roc_auc": float(roc_auc_score(y_test, y_proba)),
        }
        logger.info(f"Metrics: {metrics}")
        
        logger.info("Converting to ONNX format...")
        onnx_model: onnx.ModelProto = self._convert_to_onnx(model, X_train)
        
        local_model_path: str = f"/tmp/{self.model_version}.onnx"
        onnx.save_model(onnx_model, local_model_path)
        
        logger.info("Generating baseline statistics...")
        baseline_gen: BaselineGenerator = BaselineGenerator(X_test, predictions=y_proba)
        baseline_stats: dict[str, Any] = baseline_gen.generate_baseline()
        
        metadata: dict[str, Any] = {
            "model_version": self.model_version,
            "model_type": "logistic_regression",
            "framework": "sklearn",
            "format": "onnx",
            "schema": schema,
            "metrics": metrics,
            "hyperparameters": model.get_params(),
            "training_samples": len(X_train),
            "test_samples": len(X_test),
            "training_duration_seconds": round(time.time() - start_time, 2),
            "git_commit": self.git_commit,
            "created_by": "training_pipeline",
        }
        
        logger.info("Uploading artifacts to S3...")
        model_uri: str = self.model_storage.upload_model(local_model_path, self.model_version)
        metadata_uri: str = self.model_storage.upload_metadata(metadata, self.model_version)
        baseline_uri: str = self.model_storage.upload_baseline(baseline_stats, self.model_version)

        Path(local_model_path).unlink()
        
        training_duration: float = time.time() - start_time
        logger.info(f"Training complete in {training_duration:.2f}s")
        logger.info(f"Model: {model_uri}")
        logger.info(f"Metadata: {metadata_uri}")
        logger.info(f"Baseline: {baseline_uri}")
        
        return {
            "model_version": self.model_version,
            "model_uri": model_uri,
            "metadata_uri": metadata_uri,
            "baseline_uri": baseline_uri,
            "metrics": metrics,
            "training_duration": training_duration,
        }
    
    def _convert_to_onnx(self, model: LogisticRegression, X_sample: pd.DataFrame) -> onnx.ModelProto:
        """Convert sklearn model to ONNX format."""
        n_features: int = X_sample.shape[1]
        initial_type: list[tuple[str, FloatTensorType]] = [("float_input", FloatTensorType([None, n_features]))]
        onnx_model: onnx.ModelProto = convert_sklearn(model, initial_types=initial_type, target_opset=12)
        logger.info(f"Converted to ONNX (opset 12, {n_features} features)")
        return onnx_model


if __name__ == "__main__":
    """Run training pipeline."""
    import argparse
    
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Train ML model")
    parser.add_argument("--data", type=str, required=True, help="Path to training data CSV")
    parser.add_argument("--target", type=str, default="target", help="Target column name")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test split ratio")
    
    args: argparse.Namespace = parser.parse_args()
    
    trainer: ModelTrainer = ModelTrainer()
    results: dict[str, Any] = trainer.train(data_path=args.data, target_column=args.target, test_size=args.test_size)
    
    print(f"\nTraining complete! Model version: {results['model_version']}")
    print(f"Metrics: {results['metrics']}")
