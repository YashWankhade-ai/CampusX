from sqlalchemy import select, update
from typing import List
from app.repositories.base_repository import BaseRepository
from app.models.notification import Notification
import uuid

class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, db_session=None):
        super().__init__(model_class=Notification, db_session=db_session)


    async def get_unread(self, user_id: uuid.UUID, limit: int = 20) -> List[Notification]:
        stmt = select(self.model_class).where(
            self.model_class.user_id == user_id,
            self.model_class.is_read == False,
            self.model_class.is_deleted == False
        ).order_by(self.model_class.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def mark_all_read(self, user_id: uuid.UUID) -> bool:
        stmt = update(self.model_class).where(
            self.model_class.user_id == user_id,
            self.model_class.is_read == False,
            self.model_class.is_deleted == False
        ).values(is_read=True)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0
