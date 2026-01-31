import pytest
import numpy as np
import pandas as pd

from src.monitoring.drift_detector import DriftDetector


class TestDriftDetector:
    """Test DriftDetector functionality."""
    
    def test_initialization(self, sample_baseline):
        """Test detector initialization."""
        detector = DriftDetector(sample_baseline)
        
        assert detector.baseline == sample_baseline
        assert len(detector.baseline_samples) == 3  # 3 numeric features
    
    def test_baseline_samples_generation(self, sample_baseline):
        """Test baseline sample generation."""
        detector = DriftDetector(sample_baseline)
        
        # Check samples were generated for numeric features
        assert 'age' in detector.baseline_samples
        assert 'income' in detector.baseline_samples
        assert 'credit_score' in detector.baseline_samples
        
        # Check sample size
        assert len(detector.baseline_samples['age']) == 10000
        
        # Check samples follow baseline distribution (approximately)
        age_samples = detector.baseline_samples['age']
        assert abs(age_samples.mean() - 45.0) < 2  # Within 2 units
        assert abs(age_samples.std() - 10.0) < 2
    
    def test_detect_no_drift(self, sample_baseline, sample_training_data):
        """Test detection when no drift present."""
        detector = DriftDetector(sample_baseline)
        
        drift = detector.detect_feature_drift(sample_training_data[['age', 'income', 'credit_score']])
        
        # PSI should be low for all features
        assert drift['age']['psi'] < 0.1
        assert drift['income']['psi'] < 0.1
        assert drift['credit_score']['psi'] < 0.1
    
    def test_detect_feature_drift(self, sample_baseline, sample_drifted_data):
        """Test detection of actual drift."""
        detector = DriftDetector(sample_baseline)
        
        drift = detector.detect_feature_drift(sample_drifted_data[['age', 'income', 'credit_score']])
        
        # Age should show drift (mean shifted from 45 to 55)
        assert drift['age']['psi'] > 0.1
        assert drift['age']['mean_shift'] > 5
    
    def test_psi_calculation(self):
        """Test PSI calculation directly."""
        actual = np.array([0.25, 0.25, 0.25, 0.25])
        expected = np.array([0.25, 0.25, 0.25, 0.25])
        
        psi = DriftDetector._calculate_psi(actual, expected)
        
        # No difference = PSI near 0
        assert abs(psi) < 0.01
    
    def test_psi_with_drift(self):
        """Test PSI with actual drift."""
        actual = np.array([0.4, 0.3, 0.2, 0.1])
        expected = np.array([0.25, 0.25, 0.25, 0.25])
        
        psi = DriftDetector._calculate_psi(actual, expected)
        
        # Should have positive PSI
        assert psi > 0.1
    
    def test_ks_test_no_drift(self, sample_baseline):
        """Test KS test when distributions are same."""
        detector = DriftDetector(sample_baseline)
        
        # Generate data from same distribution
        np.random.seed(42)
        current_data = pd.DataFrame({
            'age': np.random.normal(45, 10, 1000).clip(25, 70)
        })
        
        drift = detector.detect_feature_drift(current_data)
        
        # p-value should be high (distributions are similar)
        assert drift['age']['ks_pvalue'] > 0.1
    
    def test_ks_test_with_drift(self, sample_baseline):
        """Test KS test when distributions differ."""
        detector = DriftDetector(sample_baseline)
        
        # Generate data from different distribution (shifted mean)
        np.random.seed(42)
        current_data = pd.DataFrame({
            'age': np.random.normal(60, 10, 1000).clip(25, 70)
        })
        
        drift = detector.detect_feature_drift(current_data)
        
        # p-value should be low (distributions differ)
        assert drift['age']['ks_pvalue'] < 0.1
    
    def test_missing_feature_in_current_data(self, sample_baseline):
        """Test handling of missing features."""
        detector = DriftDetector(sample_baseline)
        
        # Data missing 'credit_score' feature
        current_data = pd.DataFrame({
            'age': np.random.normal(45, 10, 100),
            'income': np.random.normal(65000, 20000, 100)
        })
        
        drift = detector.detect_feature_drift(current_data)
        
        # Should have drift for age and income, but not credit_score
        assert 'age' in drift
        assert 'income' in drift
        assert 'credit_score' not in drift
    
    def test_null_values_handling(self, sample_baseline):
        """Test handling of null values in current data."""
        detector = DriftDetector(sample_baseline)
        
        current_data = pd.DataFrame({
            'age': [45, None, 50, None, 55] * 20,
            'income': np.random.normal(65000, 20000, 100),
            'credit_score': np.random.normal(680, 70, 100)
        })
        
        drift = detector.detect_feature_drift(current_data)
        
        # Should still calculate drift (nulls dropped)
        assert 'age' in drift
        assert drift['age']['psi'] is not None
    
    def test_prediction_drift_detection(self, sample_baseline):
        """Test prediction drift detection."""
        detector = DriftDetector(sample_baseline)
        
        # Predictions similar to baseline (mean=0.5)
        current_preds = np.random.uniform(0.4, 0.6, 1000)
        
        drift = detector.detect_prediction_drift(current_preds)
        
        # Should have low drift
        assert 'mean_shift' in drift
        assert drift['mean_shift'] < 0.1
    
    def test_prediction_drift_with_shift(self, sample_baseline):
        """Test prediction drift with actual shift."""
        detector = DriftDetector(sample_baseline)
        
        # Predictions shifted higher (mean~0.8)
        current_preds = np.random.uniform(0.7, 0.9, 1000)
        
        drift = detector.detect_prediction_drift(current_preds)
        
        # Should detect shift
        assert drift['mean_shift'] > 0.2
    
    def test_empty_baseline(self):
        """Test behavior with empty baseline."""
        detector = DriftDetector({})
        
        current_data = pd.DataFrame({
            'age': np.random.normal(45, 10, 100)
        })
        
        drift = detector.detect_feature_drift(current_data)
        
        # Should return empty dict (no features in baseline)
        assert drift == {}
    
    def test_error_handling_invalid_data(self, sample_baseline):
        """Test error handling with invalid data."""
        detector = DriftDetector(sample_baseline)
        
        # Create data with non-numeric values
        current_data = pd.DataFrame({
            'age': ['invalid', 'data', 'here'] * 33 + ['more']
        })
        
        # Should handle gracefully
        drift = detector.detect_feature_drift(current_data)
        
        # May have None values for failed calculations
        if 'age' in drift:
            assert drift['age']['psi'] is None or isinstance(drift['age']['psi'], float)
    
    def test_cached_samples_consistency(self, sample_baseline):
        """Test that cached samples are used consistently."""
        detector = DriftDetector(sample_baseline)
        
        # Run drift detection twice
        current_data = pd.DataFrame({
            'age': np.random.normal(50, 10, 100),
            'income': np.random.normal(70000, 20000, 100),
            'credit_score': np.random.normal(700, 70, 100)
        })
        
        drift1 = detector.detect_feature_drift(current_data)
        drift2 = detector.detect_feature_drift(current_data)
        
        # Results should be identical (same cached samples)
        assert drift1['age']['ks_statistic'] == drift2['age']['ks_statistic']
        assert drift1['age']['ks_pvalue'] == drift2['age']['ks_pvalue']
