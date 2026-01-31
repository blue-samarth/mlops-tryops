from prometheus_client import Counter, Histogram, Gauge, Info

# API Metrics
prediction_requests_total = Counter(
    "prediction_requests_total",
    "Total number of prediction requests",
    ["endpoint", "model_version", "status"]
)

prediction_latency_seconds = Histogram(
    "prediction_latency_seconds",
    "Prediction request latency in seconds",
    ["endpoint", "model_version"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

prediction_errors_total = Counter(
    "prediction_errors_total",
    "Total number of prediction errors",
    ["endpoint", "error_type"]
)

# Model Metrics
model_info = Info(
    "model_info",
    "Information about the currently loaded model"
)

model_reload_total = Counter(
    "model_reload_total",
    "Total number of model reloads (hot-reload events)",
    ["from_version", "to_version"]
)

# Drift Metrics
drift_score = Gauge(
    "drift_score",
    "Drift score for features and predictions",
    ["model_version", "feature", "metric_type"]
)

drift_alerts_total = Counter(
    "drift_alerts_total",
    "Total number of drift alerts triggered",
    ["model_version", "feature", "drift_type"]
)

drift_check_duration_seconds = Histogram(
    "drift_check_duration_seconds",
    "Duration of drift detection checks",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
)

# Prediction Buffer Metrics
prediction_buffer_size = Gauge(
    "prediction_buffer_size",
    "Current number of predictions in buffer"
)

prediction_buffer_utilization = Gauge(
    "prediction_buffer_utilization",
    "Buffer utilization (0-1)"
)

# Schema Validation Metrics
schema_validation_errors_total = Counter(
    "schema_validation_errors_total",
    "Total number of schema validation errors",
    ["model_version", "error_type"]
)

# Rate Limiting Metrics
rate_limit_exceeded_total = Counter(
    "rate_limit_exceeded_total",
    "Total number of rate limit exceeded responses",
    ["endpoint"]
)
