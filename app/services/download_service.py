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

    def record_download_event(self, user_id, file_key):
        """Record download analytics event. Scaffold — logs only."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Download recorded: user={user_id}, key={file_key}")
