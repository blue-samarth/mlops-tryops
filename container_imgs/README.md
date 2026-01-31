# Container Images

Docker configurations for MLOps project with modern uv package management.

## Files

- **`Dockerfile.api`** - Production API runtime (~200MB)
- **`Dockerfile.train`** - Training batch job (~380MB)  
- **`docker-compose.yml`** - Local development orchestration
- **`.dockerignore`** - Excludes unnecessary files from images

## Quick Start

### Simple Workflow (Recommended)

```bash
# From project root
chmod +x run.sh

# Full workflow: Train + Start API
./run.sh all

# Individual commands
./run.sh train      # Train model only
./run.sh api        # Start API only
./run.sh stop       # Stop all services
./run.sh logs       # View API logs
./run.sh clean      # Remove everything
```

### Manual Commands

```bash
# Train model
docker-compose -f container_imgs/docker-compose.yml --profile train up training

# Start API
docker-compose -f container_imgs/docker-compose.yml up -d api

# Test prediction
curl -X POST http://localhost:8000/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"features": {"age": 35, "income": 65000, "credit_score": 720, "employment_years": 5, "debt_ratio": 0.25}}'

# Get model info
curl http://localhost:8000/v1/model/info

# Stop all
docker-compose -f container_imgs/docker-compose.yml down
```

## Environment Variables

### Local Development (docker-compose)

```bash
# Training parameters
DATA_PATH=/app/data/training_data.csv
TARGET_COLUMN=approved
TEST_SIZE=0.2

# Example
DATA_PATH=/app/data/training_data.csv TARGET_COLUMN=approved ./run.sh all
```

### Production Environment

```bash
AWS_REGION=us-east-1
S3_BUCKET=mlops-project-models
ENVIRONMENT=production
LOG_LEVEL=INFO
LOCAL_STORAGE_MODE=false
```

## Architecture

### Local Mode (Development)
- **Storage**: Volume mounts (`./models`, `./data`)
- **Local Storage**: Filesystem-based (no AWS required)
- **Training**: Runs on-demand via compose
- **API**: Auto-loads latest model from `./models/`

### Production Mode (AWS)
- **Storage**: S3 buckets
- **API**: EKS deployment with Istio
- **Training**: ECS Fargate (EventBridge scheduled)
- **Hot-reload**: ServingPointer S3 object polling

## Build Details

### Modern Features
- **uv 0.9.7**: Fast Python package manager
- **Multi-stage builds**: Optimized for size and security
- **BuildKit cache mounts**: 12x faster cached builds
- **Build metadata**: Git commit, build date, version labels
- **OCI-compliant labels**: Standardized image metadata

### Security
- Non-root user (`mlops:1000`)
- PYTHONHASHSEED=random
- No secrets in images
- Minimal base image (Debian Bookworm Slim)

### Performance
- MALLOC_ARENA_MAX=2
- Thread limiting (OMP_NUM_THREADS=4)
- ONNX Runtime optimizations

## Image Sizes

- API: ~200MB
- Training: ~380MB

## Volume Mounts

```yaml
volumes:
  - ./src:/app/src:ro          # Source code (read-only)
  - ./data:/app/data:rw        # Training data
  - ./models:/app/models:rw    # Model artifacts
  - ./outputs:/app/outputs:rw  # Training outputs
```

## Endpoints

- `http://localhost:8000` - Root
- `http://localhost:8000/health` - Health check
- `http://localhost:8000/docs` - OpenAPI docs
- `http://localhost:8000/v1/predict` - Single prediction
- `http://localhost:8000/v1/model/info` - Model metadata

## Troubleshooting

### Model not loading
```bash
# Check models directory
ls -la models/models/

# Check API logs
docker logs mlops-api-dev

# Restart API
docker-compose -f container_imgs/docker-compose.yml restart api
```

### Training fails
```bash
# Check training logs
docker-compose -f container_imgs/docker-compose.yml logs training

# Verify data exists
ls -la data/training_data.csv

# Run with custom data
DATA_PATH=/app/data/your_data.csv TARGET_COLUMN=your_target ./run.sh train
```

### Port already in use
```bash
# Find process using port 8000
lsof -i :8000

# Or change port in docker-compose.yml
ports:
  - "8001:8000"
```
