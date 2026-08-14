from sqlalchemy import select
from app.repositories.base_repository import BaseRepository
from app.models.audit import AuditLog
import uuid

class AuditRepository(BaseRepository[AuditLog]):
    def __init__(self, db_session=None):
        super().__init__(model_class=AuditLog, db_session=db_session)


    async def log_audit_event(self, action: str, entity_name: str, entity_id: str, user_id: uuid.UUID = None, details: dict = None) -> AuditLog:
        log = AuditLog(action=action, entity_name=entity_name, entity_id=entity_id, user_id=user_id, details=details)
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log
