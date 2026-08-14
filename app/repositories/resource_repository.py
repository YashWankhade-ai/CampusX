from typing import List
from app.repositories.base_repository import BaseRepository
from app.models.resource import StudyMaterial
from app.models.analytics import ResourceView
from sqlalchemy import select, desc, func
import uuid

class ResourceRepository(BaseRepository[StudyMaterial]):
    def __init__(self, db_session=None):
        super().__init__(model_class=StudyMaterial, db_session=db_session)

    def find_approved(self, limit: int = 10, offset: int = 0) -> List[StudyMaterial]:
        return self.db.query(self.model_class).filter(
            self.model_class.status == 'APPROVED',
            self.model_class.is_deleted == False
        ).limit(limit).offset(offset).all()

    def keyword_search(self, keyword: str, limit: int = 10) -> List[StudyMaterial]:
        return self.db.query(self.model_class).filter(
            (self.model_class.title.ilike(f"%{keyword}%")) | (self.model_class.description.ilike(f"%{keyword}%")),
            self.model_class.status == 'APPROVED',
            self.model_class.is_deleted == False
        ).limit(limit).all()

    def filter_by_subject(self, subject_id: uuid.UUID, limit: int = 10) -> List[StudyMaterial]:
        return self.db.query(self.model_class).filter(
            self.model_class.subject_id == subject_id,
            self.model_class.is_deleted == False
        ).limit(limit).all()

    def popular_materials(self, limit: int = 5) -> List[StudyMaterial]:
        return self.db.query(self.model_class).limit(limit).all()
