from app.models.analytics import AnalyticsEvent
from app.extensions import db
from app.services.storage_service import StorageService
from datetime import datetime, timezone

class DownloadService:
    def __init__(self):
        self.storage = StorageService()

    def generate_presigned_url(self, file_key, user_id=None):
        url = self.storage.presign_url(file_key)
        if user_id:
            self.record_download_event(user_id, file_key)
        return url

    def record_download_event(self, user_id, file_key):
        event = AnalyticsEvent(
            user_id=user_id,
            event_type='download',
            resource_key=file_key,
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(event)
        db.session.commit()
