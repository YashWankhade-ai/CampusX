from sqlalchemy import select, func, desc
from typing import List
from app.repositories.base_repository import BaseRepository
from app.models.search import SearchLog
import uuid

class SearchRepository(BaseRepository[SearchLog]):
    def __init__(self, db_session=None):
        super().__init__(model_class=SearchLog, db_session=db_session)


    async def log_query(self, query: str, user_id: uuid.UUID = None, results_count: int = 0) -> SearchLog:
        log = SearchLog(query=query, user_id=user_id, results_count=results_count)
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def get_trending(self, limit: int = 5) -> List[str]:
        stmt = select(SearchLog.query, func.count(SearchLog.id).label('q_count')).where(
            SearchLog.is_deleted == False
        ).group_by(SearchLog.query).order_by(desc('q_count')).limit(limit)
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]
