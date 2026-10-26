from app.extensions import db
from app.services.storage_service import get_storage_backend

class DownloadService:
    def __init__(self):
        self.storage = None

    def _get_storage(self):
        """Lazy-initialize storage backend (requires app context)."""
        if self.storage is None:
            self.storage = get_storage_backend()
        return self.storage

    def generate_presigned_url(self, file_key, user_id=None):
        storage = self._get_storage()
        url = storage.get_url(file_key)
        if user_id:
            self.record_download_event(user_id, file_key)
        return url

    def get_resource_file(self, resource_id: str):
        """Locates the StudyMaterial, MaterialVersion, and FileMetadata,
        and returns (abs_path, original_filename, mime_type).
        """
        import os
        import uuid
        from flask import current_app
        from app.models.resource import StudyMaterial, MaterialVersion, FileMetadata

        try:
            rid = uuid.UUID(str(resource_id))
        except (ValueError, TypeError):
            return None, None, None

        material = db.session.query(StudyMaterial).filter(
            StudyMaterial.id == rid,
            StudyMaterial.is_deleted == False
        ).first()

        if not material:
            return None, None, None

        version = db.session.query(MaterialVersion).filter_by(
            study_material_id=material.id
        ).order_by(MaterialVersion.version_number.desc()).first()

        if not version:
            return None, None, None

        file_meta = db.session.query(FileMetadata).filter_by(
            id=version.file_metadata_id
        ).first()

        if not file_meta:
            return None, None, None

        storage = self._get_storage()
        if hasattr(storage, '_get_abs_path'):
            try:
                abs_path = storage._get_abs_path(file_meta.storage_path)
                if os.path.exists(abs_path):
                    return abs_path, file_meta.original_name, file_meta.mime_type
            except Exception:
                pass

        upload_dir = current_app.config.get('UPLOAD_DIR', './uploads')
        cand_path = os.path.abspath(os.path.join(upload_dir, file_meta.storage_path))
        if os.path.exists(cand_path):
            return cand_path, file_meta.original_name, file_meta.mime_type

        return None, file_meta.original_name, file_meta.mime_type

    def record_download_event(self, user_id, file_key):
        """Record download analytics event. Scaffold — logs only."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Download recorded: user={user_id}, key={file_key}")
