import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Integer
from app.models.base import BaseModel

class SearchQueryLog(BaseModel):
    __tablename__ = "search_query_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    query_string: Mapped[str] = mapped_column(String(500), index=True)
    results_count: Mapped[int] = mapped_column(Integer, default=0)

class SearchFilterLog(BaseModel):
    __tablename__ = "search_filter_logs"
    search_query_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("search_query_logs.id"))
    filter_name: Mapped[str] = mapped_column(String(100))
    filter_value: Mapped[str] = mapped_column(String(255))
