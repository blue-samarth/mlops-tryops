import pandas as pd
import numpy as np
import pytest

from src.train.schema_generator import SchemaGenerator


class TestSchemaGenerator:
    """Test suite for SchemaGenerator."""
    
    @pytest.fixture
    def sample_dataframe(self):
        """Create sample DataFrame for testing."""
        return pd.DataFrame({
            "age": [25, 30, 35, 40, 45],
            "income": [50000, 60000, 70000, 80000, 90000],
            "credit_score": [650, 700, 750, 800, 850],
            "city": ["NYC", "LA", "NYC", "SF", "LA"],
            "approved": [0, 1, 1, 1, 0]
        })
    
    def test_generate_schema_basic(self, sample_dataframe):
        """Test basic schema generation."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        assert "structural_schema" in schema
        assert "descriptive_stats" in schema
        assert "schema_hash" in schema
        assert "n_features" in schema
        assert "feature_names" in schema
        
        assert schema["n_features"] == 4
        assert len(schema["feature_names"]) == 4
        assert "approved" not in schema["feature_names"]
    
    def test_generate_schema_structural_schema(self, sample_dataframe):
        """Test structural schema components."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        structural = schema["structural_schema"]
        assert len(structural) == 4
        
        # Check first feature
        age_schema = structural[0]
        assert age_schema["name"] == "age"
        assert age_schema["position"] == 0
        assert "int" in age_schema["dtype"].lower() or "float" in age_schema["dtype"].lower()
    
    def test_generate_schema_numeric_stats(self, sample_dataframe):
        """Test numeric feature statistics."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        stats = schema["descriptive_stats"]
        age_stats = stats["age"]
        
        assert age_stats["type"] == "numeric"
        assert age_stats["min"] == 25
        assert age_stats["max"] == 45
        assert age_stats["mean"] == 35
        assert age_stats["num_unique"] == 5
        assert age_stats["num_missing"] == 0
        assert age_stats["missing_rate"] == 0.0
    
    def test_generate_schema_categorical_stats(self, sample_dataframe):
        """Test categorical feature statistics."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        stats = schema["descriptive_stats"]
        city_stats = stats["city"]
        
        assert city_stats["type"] == "categorical"
        assert city_stats["num_unique"] == 3
        assert city_stats["num_missing"] == 0
    
    def test_generate_schema_with_missing_values(self):
        """Test schema generation with missing values."""
        df = pd.DataFrame({
            "feature1": [1, 2, None, 4, 5],
            "feature2": ["a", "b", "c", None, "e"]
        })
        
        schema = SchemaGenerator.generate_schema(df)
        
        stats = schema["descriptive_stats"]
        
        assert stats["feature1"]["num_missing"] == 1
        assert stats["feature1"]["missing_rate"] == 0.2
        assert stats["feature2"]["num_missing"] == 1
    
    def test_generate_schema_no_target_column(self, sample_dataframe):
        """Test schema generation without target column."""
        schema = SchemaGenerator.generate_schema(sample_dataframe)
        
        # Should include all columns
        assert schema["n_features"] == 5
        assert "approved" in schema["feature_names"]
    
    def test_schema_hash_consistency(self, sample_dataframe):
        """Test schema hash is consistent for same structure."""
        schema1 = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        schema2 = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        assert schema1["schema_hash"] == schema2["schema_hash"]
    
    def test_schema_hash_changes_with_structure(self, sample_dataframe):
        """Test schema hash changes when structure changes."""
        schema1 = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        # Add new column
        df_modified = sample_dataframe.copy()
        df_modified["new_feature"] = [1, 2, 3, 4, 5]
        schema2 = SchemaGenerator.generate_schema(df_modified, target_column="approved")
        
        assert schema1["schema_hash"] != schema2["schema_hash"]
    
    def test_schema_hash_unchanged_by_stats(self, sample_dataframe):
        """Test schema hash doesn't change when only stats change."""
        schema1 = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        # Change values but keep structure
        df_modified = sample_dataframe.copy()
        df_modified["age"] = [100, 200, 300, 400, 500]
        schema2 = SchemaGenerator.generate_schema(df_modified, target_column="approved")
        
        # Structure is same, so hash should match
        assert schema1["schema_hash"] == schema2["schema_hash"]
    
    def test_validate_schema_compatibility_success(self, sample_dataframe):
        """Test successful schema validation."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        # Same data should be compatible
        is_compatible, errors = SchemaGenerator.validate_schema_compatibility(
            sample_dataframe,
            schema,
            target_column="approved"
        )
        
        assert is_compatible is True
        assert len(errors) == 0
    
    def test_validate_schema_feature_count_mismatch(self, sample_dataframe):
        """Test validation fails with feature count mismatch."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        # Remove a column
        df_modified = sample_dataframe.drop(columns=["age"])
        
        is_compatible, errors = SchemaGenerator.validate_schema_compatibility(
            df_modified,
            schema,
            target_column="approved"
        )
        
        assert is_compatible is False
        assert any("Feature count mismatch" in error for error in errors)
    
    def test_validate_schema_feature_names_mismatch(self, sample_dataframe):
        """Test validation fails with feature name mismatch."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        # Rename a column
        df_modified = sample_dataframe.rename(columns={"age": "years"})
        
        is_compatible, errors = SchemaGenerator.validate_schema_compatibility(
            df_modified,
            schema,
            target_column="approved"
        )
        
        assert is_compatible is False
        assert any("Feature names/order mismatch" in error for error in errors)
    
    def test_validate_schema_dtype_mismatch(self, sample_dataframe):
        """Test validation fails with dtype mismatch."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        # Change dtype
        df_modified = sample_dataframe.copy()
        df_modified["age"] = df_modified["age"].astype(str)
        
        is_compatible, errors = SchemaGenerator.validate_schema_compatibility(
            df_modified,
            schema,
            target_column="approved"
        )
        
        assert is_compatible is False
        assert any("Data type mismatch" in error for error in errors)
    
    def test_validate_schema_feature_order_matters(self, sample_dataframe):
        """Test validation checks feature order."""
        schema = SchemaGenerator.generate_schema(sample_dataframe, target_column="approved")
        
        # Reorder columns
        df_modified = sample_dataframe[["approved", "city", "credit_score", "income", "age"]]
        
        is_compatible, errors = SchemaGenerator.validate_schema_compatibility(
            df_modified,
            schema,
            target_column="approved"
        )
        
        assert is_compatible is False
