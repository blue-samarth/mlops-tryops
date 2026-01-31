from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):

    # Storage Configuration
    LOCAL_STORAGE_MODE: bool = Field(default=False, description="Use local filesystem instead of S3 (for development)")
    LOCAL_STORAGE_PATH: str = Field(default="/app/models", description="Local storage path when LOCAL_STORAGE_MODE=true")
    
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")
    S3_BUCKET: str = Field(default="mlops-project-models", description="S3 bucket for models")

    ENVIRONMENT: str = Field(default="production", description="Deployment environment")
    MODEL_RELOAD_INTERVAL: int = Field(default=300, description="Model reload check interval (seconds)")

    API_HOST: str = Field(default="0.0.0.0", description="API host")
    API_PORT: int = Field(default=8000, description="API port")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # API Limits
    MAX_BATCH_SIZE: int = Field(default=1000, description="Maximum batch prediction size")
    RATE_LIMIT: str = Field(default="100/minute", description="API rate limit")

    # Retry Configuration
    S3_RETRY_ATTEMPTS: int = Field(default=3, description="Number of S3 retry attempts")
    S3_RETRY_MIN_WAIT: int = Field(default=2, description="Minimum retry wait time (seconds)")
    S3_RETRY_MAX_WAIT: int = Field(default=10, description="Maximum retry wait time (seconds)")

    # Drift Detection
    DRIFT_CHECK_INTERVAL: int = Field(default=3600, description="Drift check interval (seconds)")
    DRIFT_WINDOW_SIZE: int = Field(default=1000, description="Number of predictions for drift analysis")
    DRIFT_PSI_THRESHOLD: float = Field(default=0.2, description="PSI threshold for drift alert")
    DRIFT_KS_THRESHOLD: float = Field(default=0.1, description="KS test threshold")

    # Monitoring
    ENABLE_PROMETHEUS: bool = Field(default=True, description="Enable Prometheus metrics")
    ENABLE_DRIFT_DETECTION: bool = Field(default=True, description="Enable drift detection")

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
