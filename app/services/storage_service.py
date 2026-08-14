import os
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    class ClientError(Exception): pass
import hashlib

class StorageService:
    def __init__(self):
        if boto3 is not None:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID', 'dummy'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY', 'dummy'),
                endpoint_url=os.environ.get('S3_ENDPOINT_URL', None),
                region_name=os.environ.get('AWS_REGION', 'us-east-1')
            )
        else:
            self.s3_client = None
        self.bucket_name = os.environ.get('S3_BUCKET_NAME', 'campusx-storage')

    def upload_file(self, file_obj, filename, content_type):
        try:
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                filename,
                ExtraArgs={'ContentType': content_type}
            )
            return f"s3://{self.bucket_name}/{filename}"
        except ClientError as e:
            raise RuntimeError(f"Failed to upload to S3: {e}")

    def presign_url(self, file_key, expiration=3600):
        try:
            response = self.s3_client.generate_presigned_url('get_object',
                                                            Params={'Bucket': self.bucket_name,
                                                                    'Key': file_key},
                                                            ExpiresIn=expiration)
            return response
        except ClientError as e:
            raise RuntimeError(f"Failed to generate presigned URL: {e}")

    def presign_upload_url(self, file_key, expiration=3600):
        try:
            response = self.s3_client.generate_presigned_post(self.bucket_name,
                                                              file_key,
                                                              ExpiresIn=expiration)
            return response
        except ClientError as e:
            raise RuntimeError(f"Failed to generate presigned upload URL: {e}")

    def delete_file(self, file_key):
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
            return True
        except ClientError as e:
            raise RuntimeError(f"Failed to delete file: {e}")

    def calculate_sha256(self, file_obj):
        sha256_hash = hashlib.sha256()
        for byte_block in iter(lambda: file_obj.read(4096), b""):
            sha256_hash.update(byte_block)
        file_obj.seek(0)
        return sha256_hash.hexdigest()
