#!/usr/bin/env bash
set -e

# MLOps workflow orchestrator

COMPOSE_FILE="container_imgs/docker-compose.yml"

case "${1:-help}" in
  train)
    echo "Training model..."
    docker-compose -f $COMPOSE_FILE build training
    docker-compose -f $COMPOSE_FILE --profile train up training
    echo "Training complete. Model saved to ./models/"
    ;;
    
  api)
    echo "Starting API server..."
    docker-compose -f $COMPOSE_FILE up -d api
    echo "API running at http://localhost:8000"
    echo "  Health: http://localhost:8000/health"
    echo "  Docs: http://localhost:8000/docs"
    ;;
    
  all)
    echo "Training model..."
    docker-compose -f $COMPOSE_FILE build training
    docker-compose -f $COMPOSE_FILE --profile train up training
    
    echo ""
    echo "Starting API..."
    docker-compose -f $COMPOSE_FILE up -d api
    
    echo ""
    echo "Full workflow complete."
    echo "  API: http://localhost:8000"
    echo "  Model: $(ls -t models/models/*.onnx | head -1)"
    ;;
    
  stop)
    echo "Stopping all services..."
    docker-compose -f $COMPOSE_FILE down
    echo "Stopped."
    ;;
    
  logs)
    docker-compose -f $COMPOSE_FILE logs -f api
    ;;
    
  clean)
    echo "Cleaning up..."
    docker-compose -f $COMPOSE_FILE down -v
    rm -rf models/models/*.onnx models/metadata/*.json models/baselines/*.json 2>/dev/null || true
    echo "Clean."
    ;;
    
  help|*)
    cat << EOF
MLOps Workflow Commands:

  ./run.sh train    - Train a new model
  ./run.sh api      - Start API server
  ./run.sh all      - Train + Start API (full workflow)
  ./run.sh stop     - Stop all services
  ./run.sh logs     - View API logs
  ./run.sh clean    - Clean everything

Environment variables:
  DATA_PATH=/app/data/your_data.csv
  TARGET_COLUMN=your_target
  TEST_SIZE=0.3

Example:
  DATA_PATH=/app/data/training_data.csv TARGET_COLUMN=approved ./run.sh all
EOF
    ;;
esac
