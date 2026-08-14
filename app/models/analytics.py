import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, JSON
from app.models.base import BaseModel

class EventLog(BaseModel):
    __tablename__ = "event_logs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    event_data: Mapped[dict] = mapped_column(JSON)

AnalyticsEvent = EventLog

class DailyMetric(BaseModel):
    __tablename__ = "daily_metrics"
    metric_date: Mapped[str] = mapped_column(String(50), index=True) # YYYY-MM-DD
    metric_name: Mapped[str] = mapped_column(String(100))
    metric_value: Mapped[float] = mapped_column(default=0.0)

class ResourceView(BaseModel):
    __tablename__ = "resource_views"
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("study_materials.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    view_duration_seconds: Mapped[int] = mapped_column(default=0)
