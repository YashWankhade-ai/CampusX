from sqlalchemy import select, func
from typing import List
from app.repositories.base_repository import BaseRepository
from app.models.analytics import EventLog, DailyMetric
from datetime import date
import uuid

class AnalyticsRepository(BaseRepository[EventLog]):
    def __init__(self, db_session=None):
        super().__init__(model_class=EventLog, db_session=db_session)


    async def record_event(self, event_type: str, event_data: dict, user_id: uuid.UUID = None) -> EventLog:
        event = EventLog(event_type=event_type, event_data=event_data, user_id=user_id)
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def aggregate_daily(self, target_date: date) -> List[DailyMetric]:
        date_str = target_date.isoformat()
        stmt = select(DailyMetric).where(DailyMetric.metric_date == date_str, DailyMetric.is_deleted == False)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
