from sqlalchemy import select
from typing import List
from app.repositories.base_repository import BaseRepository
from app.models.approval import ApprovalRequest
import uuid

class ApprovalRepository(BaseRepository[ApprovalRequest]):
    def __init__(self, db_session=None):
        super().__init__(model_class=ApprovalRequest, db_session=db_session)


    async def find_pending(self, limit: int = 10, offset: int = 0) -> List[ApprovalRequest]:
        stmt = select(self.model_class).where(
            self.model_class.status == 'pending',
            self.model_class.is_deleted == False
        ).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_by_reviewer(self, reviewer_id: uuid.UUID, limit: int = 10) -> List[ApprovalRequest]:
        # Simple implementation assuming the reviewer will see pending requests matching their role or explicitly assigned
        # Assuming workflow logic handles assignment, returning generic query for now
        stmt = select(self.model_class).where(
            self.model_class.status == 'pending',
            self.model_class.is_deleted == False
        ).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
