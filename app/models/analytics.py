"""Analytics models — Sprint 10.

EventLog: generic application event store. Intentionally minimal.
UserContributionSummary: aggregated contribution counts per user (denormalised for fast reads).
ResourceView: records a user viewing/accessing a resource.

Privacy:
  - Passwords, JWTs, OTPs, storage credentials are NEVER stored here.
  - event_data stores only safe, non-sensitive metadata.
  - institution_id is indexed to enforce tenant isolation at query time.
"""
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, JSON, Integer, Index
from app.models.base import BaseModel


class EventLog(BaseModel):
    """Generic application event store.

    Supported event_type values (exhaustive list):
        resource.uploaded
        resource.approved
        resource.rejected
        resource.changes_requested
        resource.viewed
        search.performed

    event_data is a JSON dict with safe, non-sensitive metadata only.
    institution_id is denormalised here for efficient tenant-scoped queries.
    """
    __tablename__ = "event_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True  # No FK — institution table may not be migrated yet
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_event_logs_event_type", "event_type"),
        Index("ix_event_logs_user_id", "user_id"),
        Index("ix_event_logs_institution_id", "institution_id"),
        Index("ix_event_logs_created_at", "created_at"),
    )


# Alias kept for any existing imports
AnalyticsEvent = EventLog


class ResourceView(BaseModel):
    """Records a user accessing/viewing an approved resource."""
    __tablename__ = "resource_views"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_resource_views_resource_id", "resource_id"),
        Index("ix_resource_views_institution_id", "institution_id"),
    )


class DailyMetric(BaseModel):
    """Pre-aggregated daily metrics (populated by a background job, not used in Sprint 10)."""
    __tablename__ = "daily_metrics"

    metric_date: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[float] = mapped_column(default=0.0)
