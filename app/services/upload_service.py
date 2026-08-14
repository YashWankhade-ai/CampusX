import hashlib
from app.models import FileMetadata, StudyMaterial
from app.extensions import db
from app.services.storage_service import StorageService

class UploadService:
    def __init__(self):
        self.storage = StorageService()

    def process_upload(self, user_id, file_obj, filename, content_type):
        is_valid, msg = self.validate_file(file_obj, filename)
        if not is_valid:
            raise ValueError(msg)
        
        file_hash = self.storage.calculate_sha256(file_obj)
        existing = self.deduplicate_by_hash(file_hash)
        if existing:
            return existing

        file_obj.seek(0)
        s3_url = self.storage.upload_file(file_obj, filename, content_type)
        
        # Create metadata
        metadata = FileMetadata(
            original_filename=filename,
            content_type=content_type,
            file_hash=file_hash,
            storage_url=s3_url,
            uploader_id=user_id,
            size_bytes=len(file_obj.read())
        )
        db.session.add(metadata)
        db.session.commit()
        return metadata

    def validate_file(self, file_obj, filename):
        if not filename:
            return False, "No filename"
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        if size > 50 * 1024 * 1024:
            return False, "File too large"
        return True, "Valid"

    def deduplicate_by_hash(self, file_hash):
        return db.session.query(FileMetadata).filter_by(file_hash=file_hash).first()

    def create_upload_request(self, user_id, expected_filename, expected_size):
        if expected_size > 50 * 1024 * 1024:
            raise ValueError("Expected size too large")
        return self.storage.presign_upload_url(expected_filename)
