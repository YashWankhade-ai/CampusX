import uuid
from app.models.resource import StudyMaterial, FileMetadata, MaterialVersion, MaterialType
from app.extensions import db
from app.services.storage_service import get_storage_backend
from app.utils.file_validator import (
    validate_file, generate_safe_storage_key, calculate_checksum
)


class UploadService:
    def __init__(self):
        self._storage = None

    @property
    def storage(self):
        """Lazy-initialize storage backend (requires app context)."""
        if self._storage is None:
            self._storage = get_storage_backend()
        return self._storage

    def upload_resource(
        self,
        file,  # werkzeug FileStorage
        user_id: str,
        institution_id: str,
        title: str,
        description: str = '',
        subject_id: str = None,
        resource_type: str = 'NOTE',
        faculty_name: str = None,
        department_name: str = None,
    ) -> dict:
        """Complete upload flow with validation, storage, and DB persistence."""
        filename = file.filename
        content_type = file.content_type

        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        # 1. Validate file
        is_valid, errors = validate_file(filename, file_size, content_type)
        if not is_valid:
            raise ValueError(f"File validation failed: {', '.join(errors)}")

        try:
            material_type_enum = MaterialType[resource_type.upper()]
        except KeyError:
            material_type_enum = MaterialType.NOTE

        # 2. Calculate checksum
        checksum = calculate_checksum(file)

        # 3. Generate safe storage key
        storage_key = generate_safe_storage_key(institution_id, filename)

        # 4. Store file via storage backend
        stored_key = self.storage.save(file, storage_key)

        try:
            # 5. Create StudyMaterial record
            material = StudyMaterial(
                id=uuid.uuid4(),
                title=title,
                description=description,
                author_id=uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
                material_type=material_type_enum,
                status="PENDING",  # Requires approval before becoming available
                subject_id=uuid.UUID(subject_id) if subject_id else None,
                faculty_name=faculty_name,
                department_name=department_name,
            )

            # 6. Create FileMetadata record
            file_meta = FileMetadata(
                id=uuid.uuid4(),
                original_name=filename,
                mime_type=content_type,
                size_bytes=file_size,
                storage_path=stored_key,
                checksum=checksum
            )

            material_version = MaterialVersion(
                id=uuid.uuid4(),
                study_material_id=material.id,
                version_number=1,
                file_metadata_id=file_meta.id,
                change_summary="Initial upload"
            )

            db.session.add(material)
            db.session.add(file_meta)
            db.session.add(material_version)

            # 7. Record analytics + contribution events (flush only — committed below)
            from app.repositories.analytics_repository import record_event
            from app.services.contribution_service import record_contribution
            record_event(
                event_type="resource.uploaded",
                user_id=user_id,
                institution_id=institution_id,
                event_data={
                    "resource_id": str(material.id),
                    "resource_type": resource_type,
                    "file_size_bytes": file_size,
                },
            )
            record_contribution(
                user_id=user_id,
                action="resource_uploaded",
                resource_id=str(material.id),
                institution_id=institution_id,
            )

            db.session.commit()

            # 8. Return resource dict
            result = {
                "id": str(material.id),
                "title": material.title,
                "description": material.description,
                "resource_type": material.material_type.value,
                "status": material.status,
                "faculty_name": material.faculty_name,
                "department_name": material.department_name,
                "created_at": material.created_at.isoformat() if material.created_at else None
            }
        except Exception as e:
            # If DB fails, delete stored file (cleanup)
            db.session.rollback()
            try:
                self.storage.delete(stored_key)
            except Exception:
                pass  # Ignore cleanup errors
            raise e

        # 9. Notify moderators/admins — outside the transaction so failure never rolls back the upload
        try:
            from app.services.notification_service import notify_resource_uploaded
            from app.models.user import User
            roles_to_notify = ("MODERATOR", "INSTITUTION_ADMIN", "SUPER_ADMIN")
            if institution_id:
                import uuid as _uuid
                moderator_ids = [
                    str(u.id) for u in db.session.query(User).filter(
                        User.institution_id == _uuid.UUID(institution_id),
                        User.role.in_(roles_to_notify),
                        User.is_deleted == False,
                    ).all()
                ]
            else:
                moderator_ids = []
            notify_resource_uploaded(
                resource_id=result["id"],
                resource_title=title,
                uploader_institution_id=institution_id or "",
                moderator_ids=moderator_ids,
            )
        except Exception:
            pass  # Notification failure must not affect the upload result

        return result
