import json
import re
from typing import Any
import logging
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.utils.config import settings

logger: logging.Logger = logging.getLogger(__name__)

VERSION_PATTERN = re.compile(r"^v\d{8}_\d{6}_[a-f0-9]{6}$")


class S3Operations:
    """
    S3 operations with retry logic and IAM role support.
    
    Security Note: This class uses IAM roles by default (no hardcoded credentials).
    boto3.client() will automatically use:
    - EC2 instance profile (in AWS)
    - ECS task role (in ECS)
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - ~/.aws/credentials file (for local development)
    """

    def __init__(self, bucket_name: str, region_name: str | None = None):
        """
        Initialize S3 operations client.
        
        Args:
            bucket_name: S3 bucket name
            region_name: AWS region (defaults to settings.AWS_REGION)
        
        Note: Credentials are loaded from IAM role/environment, NOT passed as parameters.
        """
        self.bucket_name: str = bucket_name
        self.region_name: str = region_name or settings.AWS_REGION
        
        # Use IAM role - no hardcoded credentials
        self.s3_client = boto3.client('s3', region_name=self.region_name)
        
        logger.info(f"Initialized S3Operations for bucket {bucket_name} in {self.region_name}")

    @retry(
        stop=stop_after_attempt(settings.S3_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=settings.S3_RETRY_MIN_WAIT, max=settings.S3_RETRY_MAX_WAIT),
        retry=retry_if_exception_type(ClientError),
        reraise=True
    )
    def upload_file(self, local_path: str, s3_key: str, metadata: dict[str, str] | None = None, content_type: str | None = None) -> bool:
        """
        Upload a file to S3 with automatic retry on transient failures.
        
        Args:
            local_path: Local file path
            s3_key: S3 object key (path in bucket)
            metadata: Optional metadata to attach to the S3 object
            content_type: Optional content type (auto-detected if not provided)
        
        Returns:
            True if successful, False otherwise
        
        Raises:
            ClientError: After all retry attempts exhausted
        """
        try:
            extra_args: dict[str, Any] = {}
            if metadata: extra_args["Metadata"] = metadata
            if content_type: extra_args["ContentType"] = content_type
            elif s3_key.endswith('.json'): extra_args["ContentType"] = "application/json"
            elif s3_key.endswith('.onnx'): extra_args["ContentType"] = "application/octet-stream"

            self.s3_client.upload_file(local_path, self.bucket_name, s3_key, ExtraArgs=extra_args if extra_args else None)
            logger.info(f"Uploaded {local_path} to s3://{self.bucket_name}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to upload {local_path} after retries: {e}")
            return False

    @retry(
        stop=stop_after_attempt(settings.S3_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=settings.S3_RETRY_MIN_WAIT, max=settings.S3_RETRY_MAX_WAIT),
        retry=retry_if_exception_type(ClientError),
        reraise=True
    )
    def download_file(self, s3_key: str, local_path: str) -> bool:
        """
        Download a file from S3 with automatic retry on transient failures.
        
        Args:
            s3_key: S3 object key
            local_path: Local destination path
        
        Returns:
            True if successful, False otherwise
        
        Raises:
            ClientError: After all retry attempts exhausted
        """
        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            logger.info(f"Downloaded s3://{self.bucket_name}/{s3_key} to {local_path}")
            return True
        except ClientError as e:
            logger.error(f"Failed to download {s3_key} after retries: {e}")
            return False

    @retry(
        stop=stop_after_attempt(settings.S3_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=settings.S3_RETRY_MIN_WAIT, max=settings.S3_RETRY_MAX_WAIT),
        retry=retry_if_exception_type(ClientError),
        reraise=True
    )
    def upload_json(self, data: dict[str, Any], s3_key: str) -> bool:
        """
        Upload JSON data to S3 with automatic retry on transient failures.
        
        Args:
            data: Dictionary to upload as JSON
            s3_key: S3 object key
        
        Returns:
            True if successful, False otherwise
        
        Raises:
            ClientError: After all retry attempts exhausted
        """
        try:
            json_str: str = json.dumps(data, indent=2)
            self.s3_client.put_object(Bucket=self.bucket_name, Key=s3_key, Body=json_str, ContentType="application/json")
            logger.info(f"Uploaded JSON to s3://{self.bucket_name}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to upload JSON to {s3_key} after retries: {e}")
            return False

    @retry(
        stop=stop_after_attempt(settings.S3_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=settings.S3_RETRY_MIN_WAIT, max=settings.S3_RETRY_MAX_WAIT),
        retry=retry_if_exception_type(ClientError),
        reraise=True
    )
    def download_json(self, s3_key: str) -> dict[str, Any] | None:
        """
        Download and parse JSON from S3 with automatic retry on transient failures.
        
        Args:
            s3_key: S3 object key
        
        Returns:
            Parsed JSON as dictionary, or None if failed
        
        Raises:
            ClientError: After all retry attempts exhausted
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            json_str: str = response["Body"].read().decode("utf-8")
            data: dict[str, Any] = json.loads(json_str)
            logger.info(f"Downloaded JSON from s3://{self.bucket_name}/{s3_key}")
            return data
        except ClientError as e:
            logger.error(f"Failed to download JSON from {s3_key} after retries: {e}")
            return None

    def list_objects(self, prefix: str, max_keys: int = 1000) -> list[str]:
        """
        List objects with a given prefix.
        Args:
            prefix: S3 key prefix
            max_keys: Maximum number of keys to return
        Returns:
            List of object keys
        """
        try:
            response: dict[str, Any] = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys)
            if "Contents" not in response: return []
            return [obj["Key"] for obj in response["Contents"]]
        except ClientError as e:
            logger.error(f"Failed to list objects with prefix {prefix}: {e}")
            return []

    def object_exists(self, s3_key: str) -> bool:
        """
        Check if an object exists in S3.
        Args:
            s3_key: S3 object key
        Returns:
            True if exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError: return False

    def copy_object(self, source_key: str, dest_key: str) -> bool:
        """
        Copy an object within the same bucket.
        Args:
            source_key: Source S3 key
            dest_key: Destination S3 key
        Returns:
            True if successful, False otherwise
        """
        try:
            copy_source: dict[str, str] = {"Bucket": self.bucket_name, "Key": source_key}
            self.s3_client.copy_object(CopySource=copy_source, Bucket=self.bucket_name, Key=dest_key)
            logger.info(f"Copied {source_key} to {dest_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to copy {source_key} to {dest_key}: {e}")
            return False

    def get_s3_uri(self, s3_key: str) -> str: return f"s3://{self.bucket_name}/{s3_key}"
