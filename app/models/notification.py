"""Notification models — Sprint 11.

Notification: persisted in-app notification for a user.

notification_type values (exhaustive — do not add without architecture sign-off):
    resource.uploaded           — moderator/admin: a new resource is pending review
    resource.approved           — uploader: their resource was approved
    resource.rejected           — uploader: their resource was rejected
    resource.changes_requested  — uploader: changes were requested

institution_id is denormalized for efficient tenant-scoped queries.
read_at records the exact moment a notification was marked read (nullable = unread).

Design decisions:
- Notifications are APPEND-ONLY. Soft-delete is inherited from BaseModel but never
  used for ownership enforcement — recipient_id is always enforced server-side.
- action_url is optional: a relative path the frontend can navigate to on click.
- NotificationTemplate and UserDevice are kept as scaffolds per prior schema;
  they are not wired up in Sprint 11.
"""
import uuid
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Boolean, Text, DateTime, Index
from app.models.base import BaseModel


class Notification(BaseModel):
    """Persisted in-app notification."""
    __tablename__ = "notifications"

    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # notification_type must be one of NOTIFICATION_TYPES below
    notification_type: Mapped[str] = mapped_column(String(60), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional reference to the related entity (resource, etc.)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("study_materials.id", ondelete="SET NULL"), nullable=True
    )

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Optional relative URL for the frontend to navigate to on click
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        # Primary query pattern: all notifications for a user ordered by recency
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
        # Unread filter
        Index("ix_notifications_recipient_is_read", "recipient_id", "is_read"),
        # Institution-scoped admin queries
        Index("ix_notifications_institution_id", "institution_id"),
    )

    def to_safe_dict(self) -> dict:
        """Return only safe, non-sensitive fields."""
        return {
            "id": str(self.id),
            "notification_type": self.notification_type,
            "title": self.title,
            "message": self.message,
            "resource_id": str(self.resource_id) if self.resource_id else None,
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "action_url": self.action_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Architecture-supported notification types
NOTIFICATION_TYPES = frozenset({
    "resource.uploaded",
    "resource.approved",
    "resource.rejected",
    "resource.changes_requested",
})


class NotificationTemplate(BaseModel):
    """Scaffold — template-based notification text. Not wired in Sprint 11."""
    __tablename__ = "notification_templates"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    body_template: Mapped[str] = mapped_column(Text)


class UserDevice(BaseModel):
    """Scaffold — push device token. Not wired in Sprint 11."""
    __tablename__ = "user_devices"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    device_token: Mapped[str] = mapped_column(String(255), unique=True)
    platform: Mapped[str] = mapped_column(String(50))  # ios, android, web
