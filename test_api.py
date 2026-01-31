#!/usr/bin/env python3
"""
Test script for the ML Serving API.
Run this to verify the API is working correctly.
"""
import sys
import time
import requests
from typing import Any


API_BASE_URL = "http://localhost:8000"


def test_health_check() -> bool:
    """Test health check endpoint."""
    print("Testing health check...")
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"  Error: {e}")
        return False


def test_readiness_check() -> bool:
    """Test readiness check endpoint."""
    print("\nTesting readiness check...")
    try:
        response = requests.get(f"{API_BASE_URL}/ready", timeout=5)
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"  Error: {e}")
        return False


def test_model_info() -> bool:
    """Test model info endpoint."""
    print("\nTesting model info...")
    try:
        response = requests.get(f"{API_BASE_URL}/v1/model/info", timeout=5)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Model Version: {data.get('model_version')}")
            print(f"  Schema Hash: {data.get('schema_hash')}")
            print(f"  Features: {data.get('feature_names')}")
            print(f"  Model Type: {data.get('model_type')}")
            return True
        else:
            print(f"  Response: {response.json()}")
            return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def test_prediction() -> bool:
    """Test prediction endpoint."""
    print("\nTesting prediction...")
    
    # Example prediction request
    # NOTE: Update these features to match your actual model schema
    payload = {
        "features": {
            "age": 45,
            "income": 75000,
            "credit_score": 720
        }
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/predict",
            json=payload,
            timeout=5
        )
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Model Version: {data.get('model_version')}")
            print(f"  Prediction: {data.get('prediction')}")
            print(f"  Predicted Class: {data.get('prediction_class')}")
            return True
        else:
            print(f"  Response: {response.json()}")
            return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def test_batch_prediction() -> bool:
    """Test batch prediction endpoint."""
    print("\nTesting batch prediction...")
    
    # Example batch prediction request
    payload = {
        "instances": [
            {"age": 45, "income": 75000, "credit_score": 720},
            {"age": 32, "income": 55000, "credit_score": 680},
            {"age": 55, "income": 95000, "credit_score": 750},
        ]
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/predict/batch",
            json=payload,
            timeout=5
        )
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Model Version: {data.get('model_version')}")
            print(f"  Number of Predictions: {len(data.get('predictions', []))}")
            for i, pred in enumerate(data.get('predictions', [])):
                print(f"    Instance {i}: prob={pred['prediction']:.4f}, class={pred['prediction_class']}")
            return True
        else:
            print(f"  Response: {response.json()}")
            return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("ML Serving API Test Suite")
    print("=" * 60)
    
    # Wait for server to start
    print("\nWaiting for server to start...")
    max_retries = 10
    for i in range(max_retries):
        try:
            requests.get(f"{API_BASE_URL}/health", timeout=2)
            print("Server is ready!")
            break
        except:
            if i < max_retries - 1:
                time.sleep(2)
            else:
                print("ERROR: Server did not start in time")
                sys.exit(1)
    
    print()
    
    # Run tests
    results = {
        "Health Check": test_health_check(),
        "Readiness Check": test_readiness_check(),
        "Model Info": test_model_info(),
        "Single Prediction": test_prediction(),
        "Batch Prediction": test_batch_prediction(),
    }
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:.<40} {status}")
    
    print("=" * 60)
    
    # Exit with appropriate code
    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
