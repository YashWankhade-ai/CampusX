from typing import TypeVar, Generic, Type, Any, Sequence, Optional
import uuid
from sqlalchemy import select, update, func, or_
from app.models.base import BaseModel
from app.extensions import db
import math

T = TypeVar("T", bound=BaseModel)

class BaseRepository(Generic[T]):
    def __init__(self, model_class: Optional[Type[T]] = None, db_session: Optional[Any] = None):
        self.model_class = model_class
        self.db = db_session if db_session is not None else db.session

    def get_by_id(self, id: uuid.UUID) -> Optional[T]:
        if not self.model_class:
            return None
        return self.db.query(self.model_class).filter(self.model_class.id == id, self.model_class.is_deleted == False).first()

    def list_paginated(
        self,
        page: int = 1,
        per_page: int = 10,
        filters: dict[str, Any] = None,
        sort_by: str = "created_at",
        order: str = "desc",
        search_query: str = None,
        search_fields: list[str] = None
    ) -> dict[str, Any]:
        if not self.model_class:
            return {"items": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0}

        query = self.db.query(self.model_class).filter(self.model_class.is_deleted == False)

        if filters:
            for key, value in filters.items():
                if value is not None and hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)

        if search_query and search_fields:
            search_conditions = []
            for field in search_fields:
                if hasattr(self.model_class, field):
                    search_conditions.append(getattr(self.model_class, field).ilike(f"%{search_query}%"))
            if search_conditions:
                query = query.filter(or_(*search_conditions))

        total_count = query.count()

        if hasattr(self.model_class, sort_by):
            sort_column = getattr(self.model_class, sort_by)
            if order.lower() == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())

        offset = (page - 1) * per_page
        items = query.offset(offset).limit(per_page).all()

        return {
            "items": items,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": math.ceil(total_count / per_page) if per_page else 0
        }

    def create(self, **kwargs) -> T:
        instance = self.model_class(**kwargs)
        self.db.add(instance)
        self.db.commit()
        return instance

    def update(self, id: uuid.UUID, **kwargs) -> Optional[T]:
        instance = self.get_by_id(id)
        if instance:
            for k, v in kwargs.items():
                setattr(instance, k, v)
            self.db.commit()
        return instance

    def soft_delete(self, id: uuid.UUID) -> bool:
        from datetime import datetime, timezone
        instance = self.get_by_id(id)
        if instance:
            instance.is_deleted = True
            instance.deleted_at = datetime.now(timezone.utc)
            self.db.commit()
            return True
        return False

    def hard_delete(self, id: uuid.UUID) -> bool:
        instance = self.get_by_id(id)
        if instance:
            self.db.delete(instance)
            self.db.commit()
            return True
        return False
