import os
import io
import shutil
from pathlib import Path
from flask import current_app

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    class ClientError(Exception): pass

class StorageBackend:
    def save(self, file_data, storage_key: str) -> str:
        raise NotImplementedError

    def get(self, storage_key: str) -> io.IOBase:
        raise NotImplementedError

    def delete(self, storage_key: str) -> bool:
        raise NotImplementedError

    def exists(self, storage_key: str) -> bool:
        raise NotImplementedError

    def get_url(self, storage_key: str) -> str:
        raise NotImplementedError

class LocalStorageBackend(StorageBackend):
    def __init__(self):
        self.upload_dir = current_app.config.get('UPLOAD_DIR', './uploads')

    def _get_abs_path(self, storage_key: str) -> str:
        # Prevent path traversal
        clean_key = storage_key.lstrip('/')
        if '..' in clean_key:
            raise ValueError("Path traversal detected in storage_key")

        path = os.path.abspath(os.path.join(self.upload_dir, clean_key))
        if not path.startswith(os.path.abspath(self.upload_dir)):
            raise ValueError("Path is outside upload directory")
        return path

    def save(self, file_data, storage_key: str) -> str:
        path = self._get_abs_path(storage_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_data.seek(0)
        with open(path, 'wb') as f:
            shutil.copyfileobj(file_data, f)
        file_data.seek(0)
        return storage_key

    def get(self, storage_key: str) -> io.IOBase:
        path = self._get_abs_path(storage_key)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {storage_key}")
        return open(path, 'rb')

    def delete(self, storage_key: str) -> bool:
        path = self._get_abs_path(storage_key)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def exists(self, storage_key: str) -> bool:
        path = self._get_abs_path(storage_key)
        return os.path.exists(path)

    def get_url(self, storage_key: str) -> str:
        path = self._get_abs_path(storage_key)
        return f"file://{path}"

class S3StorageBackend(StorageBackend):
    def __init__(self):
        if boto3 is None:
            raise RuntimeError("boto3 is not installed")

        self.bucket_name = current_app.config.get('S3_BUCKET', '')
        endpoint_url = current_app.config.get('S3_ENDPOINT_URL', '')
        region_name = current_app.config.get('S3_REGION', 'us-east-1')

        if not endpoint_url:
            endpoint_url = None

        # Get from environ so it doesn't crash if config is missing
        aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID', '')
        aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY', '')

        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id if aws_access_key_id else None,
            aws_secret_access_key=aws_secret_access_key if aws_secret_access_key else None,
            endpoint_url=endpoint_url,
            region_name=region_name
        )

    def save(self, file_data, storage_key: str) -> str:
        import mimetypes
        file_data.seek(0)
        content_type, _ = mimetypes.guess_type(storage_key)
        if not content_type:
            content_type = 'application/octet-stream'

        try:
            self.s3_client.upload_fileobj(
                file_data,
                self.bucket_name,
                storage_key,
                ExtraArgs={'ContentType': content_type}
            )
            file_data.seek(0)
            return storage_key
        except ClientError as e:
            raise RuntimeError(f"Failed to upload to S3: {e}")

    def get(self, storage_key: str) -> io.IOBase:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=storage_key)
            return response['Body']
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"File not found: {storage_key}")
            raise RuntimeError(f"Failed to get file from S3: {e}")

    def delete(self, storage_key: str) -> bool:
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except ClientError as e:
            raise RuntimeError(f"Failed to delete file from S3: {e}")

    def exists(self, storage_key: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise RuntimeError(f"Failed to check file existence in S3: {e}")

    def get_url(self, storage_key: str) -> str:
        try:
            response = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': storage_key},
                ExpiresIn=3600
            )
            return response
        except ClientError as e:
            raise RuntimeError(f"Failed to generate presigned URL: {e}")

def get_storage_backend() -> StorageBackend:
    backend_type = current_app.config.get('STORAGE_BACKEND', 'local')
    if backend_type == 's3':
        return S3StorageBackend()
    return LocalStorageBackend()
