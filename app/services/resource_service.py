import uuid
import logging

from app.services.upload_service import UploadService
from app.services.download_service import DownloadService
from app.services.version_service import VersionService
from app.repositories.resource_repository import ResourceRepository
from app.extensions import db

logger = logging.getLogger(__name__)

# Statuses visible to regular users (STUDENT, FACULTY, MODERATOR, etc.)
PUBLIC_STATUSES = frozenset({"APPROVED"})
# Statuses additionally visible to the resource author and reviewers
AUTHOR_VISIBLE_STATUSES = frozenset({"APPROVED", "PENDING", "CHANGES_REQUESTED", "REJECTED"})


class ResourceService:
    def __init__(self):
        self.upload_service = UploadService()
        self.download_service = DownloadService()
        self.version_service = VersionService()
        self.repository = ResourceRepository()

    def get_resource(self, resource_id: str):
        return self.repository.get_by_id(resource_id)

    def get_resource_detail(
        self,
        resource_id: str,
        viewer_id: str,
        viewer_institution_id: str,
        viewer_role: str,
    ) -> dict | None:
        """Return safe resource metadata after enforcing all access rules.

        Rules (in order):
        1. Resource must exist and not be soft-deleted.
        2. Institution isolation: resource author must belong to the same institution as viewer.
        3. Visibility: only APPROVED resources are visible to regular users.
           The resource author can see their own resource in any status.
           Roles with resources:approve (MODERATOR, INSTITUTION_ADMIN, SUPER_ADMIN) can see any status.
        4. Returns a safe dict — NO storage_path, NO file paths.

        Returns None if any check fails (caller returns 404 — never leaks existence).
        """
        try:
            rid = uuid.UUID(resource_id)
        except (ValueError, TypeError):
            return None

        from app.models.resource import StudyMaterial
        from app.models.user import User

        resource = db.session.query(StudyMaterial).filter(
            StudyMaterial.id == rid,
            StudyMaterial.is_deleted == False,
        ).first()

        if not resource:
            return None

        # ── Institution isolation ────────────────────────────────────────
        author = db.session.query(User).filter(User.id == resource.author_id).first()
        if not author:
            return None

        try:
            viewer_iid = uuid.UUID(viewer_institution_id) if viewer_institution_id else None
        except (ValueError, TypeError):
            viewer_iid = None

        if author.institution_id != viewer_iid:
            # Fail closed — treat as not found, never reveal cross-institution data
            return None

        # ── Visibility enforcement ───────────────────────────────────────
        is_own_resource = str(resource.author_id) == str(viewer_id)
        can_approve = viewer_role in ("MODERATOR", "INSTITUTION_ADMIN", "SUPER_ADMIN")

        if resource.status not in PUBLIC_STATUSES:
            # Non-approved resources: only author and reviewers may see them
            if not (is_own_resource or can_approve):
                return None

        # ── Safe metadata dict — NO storage paths, NO internal paths ────
        subj_name = resource.subject.name if resource.subject else None
        subj_code = resource.subject.code if resource.subject else None
        return {
            "id": str(resource.id),
            "title": resource.title,
            "description": resource.description,
            "status": resource.status,
            "material_type": resource.material_type.value,
            "author_id": str(resource.author_id),
            "faculty_name": resource.faculty_name,
            "department_name": resource.department_name,
            "subject_id": str(resource.subject_id) if resource.subject_id else None,
            "subject_name": subj_name,
            "subject_code": subj_code,
            "topic_id": str(resource.topic_id) if resource.topic_id else None,
            "created_at": resource.created_at.isoformat() if resource.created_at else None,
            "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
        }

    def list_resources(self, page: int = 1, limit: int = 20, subject_id: str = None, category_id: str = None, sort_by: str = "created_at", search: str = None):
        return self.repository.list_paginated(
            page=page,
            per_page=limit,
            filters={"subject_id": subject_id, "category_id": category_id, "status": "APPROVED"},
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
        if user_id:
            try:
                self.download_service.record_download_event(user_id, resource_id)
            except Exception:
                pass
        return f"/api/v1/resources/{resource_id}/file"
