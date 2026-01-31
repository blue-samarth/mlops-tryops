import json
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
import pytest
from botocore.exceptions import ClientError

from src.utils.s3_operations import S3Operations


class TestS3Operations:
    """Test suite for S3Operations."""
    
    @pytest.fixture
    def mock_boto3_client(self):
        """Mock boto3 S3 client."""
        with patch('boto3.client') as mock:
            client = MagicMock()
            mock.return_value = client
            yield client
    
    def test_initialization(self, mock_boto3_client):
        """Test S3Operations initialization."""
        s3_ops = S3Operations(bucket_name="test-bucket", region_name="us-west-2")
        
        assert s3_ops.bucket_name == "test-bucket"
        assert s3_ops.region_name == "us-west-2"
    
    def test_upload_file_success(self, mock_boto3_client, tmp_path):
        """Test successful file upload."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.upload_file(str(test_file), "path/test.txt")
        
        assert result is True
        mock_boto3_client.upload_file.assert_called_once()
    
    def test_upload_file_with_metadata(self, mock_boto3_client, tmp_path):
        """Test file upload with metadata."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        metadata = {"key1": "value1", "key2": "value2"}
        
        result = s3_ops.upload_file(str(test_file), "path/test.txt", metadata=metadata)
        
        assert result is True
        call_args = mock_boto3_client.upload_file.call_args
        assert call_args[1]['ExtraArgs']['Metadata'] == metadata
    
    def test_upload_file_json_content_type(self, mock_boto3_client, tmp_path):
        """Test JSON file gets correct content type."""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"key": "value"}')
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.upload_file(str(test_file), "path/test.json")
        
        assert result is True
        call_args = mock_boto3_client.upload_file.call_args
        assert call_args[1]['ExtraArgs']['ContentType'] == "application/json"
    
    def test_upload_file_onnx_content_type(self, mock_boto3_client, tmp_path):
        """Test ONNX file gets correct content type."""
        test_file = tmp_path / "model.onnx"
        test_file.write_bytes(b"fake onnx content")
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.upload_file(str(test_file), "models/model.onnx")
        
        assert result is True
        call_args = mock_boto3_client.upload_file.call_args
        assert call_args[1]['ExtraArgs']['ContentType'] == "application/octet-stream"
    
    def test_upload_file_failure(self, mock_boto3_client, tmp_path):
        """Test file upload failure handling."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        mock_boto3_client.upload_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}},
            "upload_file"
        )
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.upload_file(str(test_file), "path/test.txt")
        
        assert result is False
    
    def test_download_file_success(self, mock_boto3_client, tmp_path):
        """Test successful file download."""
        local_path = tmp_path / "downloaded.txt"
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.download_file("path/test.txt", str(local_path))
        
        assert result is True
        mock_boto3_client.download_file.assert_called_once()
    
    def test_download_file_creates_directory(self, mock_boto3_client, tmp_path):
        """Test download creates parent directories."""
        local_path = tmp_path / "subdir" / "file.txt"
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.download_file("path/test.txt", str(local_path))
        
        assert result is True
        assert local_path.parent.exists()
    
    def test_download_file_failure(self, mock_boto3_client, tmp_path):
        """Test file download failure handling."""
        local_path = tmp_path / "downloaded.txt"
        
        mock_boto3_client.download_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
            "download_file"
        )
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.download_file("path/missing.txt", str(local_path))
        
        assert result is False
    
    def test_upload_json_success(self, mock_boto3_client, tmp_path):
        """Test JSON upload."""
        data = {"key": "value", "number": 42}
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_file = MagicMock()
            mock_file.name = str(tmp_path / "temp.json")
            mock_temp.return_value.__enter__.return_value = mock_file
            
            # Create actual temp file for test
            Path(mock_file.name).write_text(json.dumps(data, indent=2))
            
            s3_ops = S3Operations(bucket_name="test-bucket")
            result = s3_ops.upload_json(data, "path/data.json")
        
        assert result is True
    
    def test_download_json_success(self, mock_boto3_client):
        """Test JSON download."""
        data = {"key": "value", "number": 42}
        
        mock_response = MagicMock()
        mock_response["Body"].read.return_value = json.dumps(data).encode('utf-8')
        mock_boto3_client.get_object.return_value = mock_response
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.download_json("path/data.json")
        
        assert result == data
    
    def test_download_json_not_found(self, mock_boto3_client):
        """Test JSON download when file not found."""
        mock_boto3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Key not found"}},
            "get_object"
        )
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.download_json("path/missing.json")
        
        assert result is None
    
    def test_object_exists_true(self, mock_boto3_client):
        """Test checking object exists."""
        mock_boto3_client.head_object.return_value = {"ContentLength": 100}
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.object_exists("path/file.txt")
        
        assert result is True
    
    def test_object_exists_false(self, mock_boto3_client):
        """Test checking object doesn't exist."""
        mock_boto3_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "head_object"
        )
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.object_exists("path/missing.txt")
        
        assert result is False
    
    def test_list_objects_success(self, mock_boto3_client):
        """Test listing objects."""
        mock_boto3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "models/v1.onnx"},
                {"Key": "models/v2.onnx"}
            ]
        }
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.list_objects("models/")
        
        assert len(result) == 2
        assert "models/v1.onnx" in result
    
    def test_list_objects_empty(self, mock_boto3_client):
        """Test listing objects when none exist."""
        mock_boto3_client.list_objects_v2.return_value = {}
        
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.list_objects("empty/")
        
        assert result == []
    
    def test_get_s3_uri(self, mock_boto3_client):
        """Test generating S3 URI."""
        s3_ops = S3Operations(bucket_name="test-bucket")
        uri = s3_ops.get_s3_uri("path/to/file.txt")
        
        assert uri == "s3://test-bucket/path/to/file.txt"
    
    def test_copy_object_success(self, mock_boto3_client):
        """Test copying object."""
        s3_ops = S3Operations(bucket_name="test-bucket")
        result = s3_ops.copy_object("source/file.txt", "dest/file.txt")
        
        assert result is True
        mock_boto3_client.copy_object.assert_called_once()
