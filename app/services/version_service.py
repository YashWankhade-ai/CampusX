import uuid
from app.models import ResourceVersion
from app.extensions import db
from datetime import datetime, timezone

class VersionService:
    def create_new_version(self, resource_id, file_metadata_id, version_notes=""):
        version = ResourceVersion(
            resource_id=resource_id,
            file_metadata_id=file_metadata_id,
            version_number=str(uuid.uuid4())[:8],
            notes=version_notes,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(version)
        db.session.commit()
        return version

    def list_versions(self, resource_id):
        return db.session.query(ResourceVersion).filter_by(resource_id=resource_id).order_by(ResourceVersion.created_at.desc()).all()
