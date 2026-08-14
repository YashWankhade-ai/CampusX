from app.services.upload_service import UploadService
from app.services.download_service import DownloadService
from app.services.version_service import VersionService
from app.repositories.resource_repository import ResourceRepository

class ResourceService:
    def __init__(self):
        self.upload_service = UploadService()
        self.download_service = DownloadService()
        self.version_service = VersionService()
        self.repository = ResourceRepository()

    def get_resource(self, resource_id: str):
        return self.repository.get_by_id(resource_id)

    def list_resources(self, page: int = 1, limit: int = 20, subject_id: str = None, category_id: str = None, sort_by: str = "created_at", search: str = None):
        return self.repository.list_paginated(
            page=page,
            per_page=limit,
            filters={"subject_id": subject_id, "category_id": category_id},
            sort_by=sort_by,
            search_query=search
        )

    def upload(self, file_storage, author_id: str, title: str, description: str = None, subject_id: str = None, topic_id: str = None):
        return self.upload_service.process_upload(
            file_storage=file_storage,
            author_id=author_id,
            title=title,
            description=description,
            subject_id=subject_id,
            topic_id=topic_id
        )

    def get_download_link(self, resource_id: str, user_id: str = None):
        return self.download_service.generate_presigned_url(resource_id=resource_id, user_id=user_id)
