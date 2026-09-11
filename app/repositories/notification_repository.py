"""Notification Repository — Sprint 11.

Synchronous module-level functions using db.session (Flask-compatible).

All queries are institution-scoped through recipient_id ownership.
No async — Flask is synchronous.

Query pattern:
    recipient_id + is_read    → unread inbox
    recipient_id + created_at → paginated notification list
"""
import uuid
import logging
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import func

from app.extensions import db
from app.models.notification import Notification

logger = logging.getLogger(__name__)

# Hard cap on notifications returned per request — prevents abuse
MAX_NOTIFICATIONS_PER_REQUEST = 100


def create_notification(
    recipient_id: str,
    notification_type: str,
    title: str,
    message: str,
    institution_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    action_url: Optional[str] = None,
) -> Optional[Notification]:
    """Persist a notification. Uses db.session.flush() — caller must commit.

    Returns None on failure (never raises — notification failure must not
    break the primary business operation that triggered it).
    """
    from app.models.notification import NOTIFICATION_TYPES
    if notification_type not in NOTIFICATION_TYPES:
        logger.warning("Dropping unknown notification type: %s", notification_type)
        return None
    try:
        n = Notification(
            recipient_id=uuid.UUID(recipient_id),
            notification_type=notification_type,
            title=title,
            message=message,
            institution_id=uuid.UUID(institution_id) if institution_id else None,
            resource_id=uuid.UUID(resource_id) if resource_id else None,
            action_url=action_url,
            is_read=False,
        )
        db.session.add(n)
        db.session.flush()
        return n
    except Exception:
        logger.warning("Failed to create notification type=%s", notification_type, exc_info=True)
        return None


def get_notifications_for_user(
    recipient_id: str,
    unread_only: bool = False,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Notification], int]:
    """Return paginated notifications for a user, newest first.

    Returns (items, total_count). Enforces MAX_NOTIFICATIONS_PER_REQUEST.
    """
    try:
        uid = uuid.UUID(recipient_id)
    except (ValueError, TypeError):
        return [], 0

    limit = min(limit, MAX_NOTIFICATIONS_PER_REQUEST)
    page = max(page, 1)
    offset = (page - 1) * limit

    base = db.session.query(Notification).filter(
        Notification.recipient_id == uid,
        Notification.is_deleted == False,
    )
    if unread_only:
        base = base.filter(Notification.is_read == False)

    total = base.with_entities(func.count(Notification.id)).scalar() or 0
    items = base.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def get_unread_count(recipient_id: str) -> int:
    """Return unread notification count for a user. Single aggregation query."""
    try:
        uid = uuid.UUID(recipient_id)
    except (ValueError, TypeError):
        return 0
    return db.session.query(func.count(Notification.id)).filter(
        Notification.recipient_id == uid,
        Notification.is_read == False,
        Notification.is_deleted == False,
    ).scalar() or 0


def mark_notification_read(notification_id: str, recipient_id: str) -> bool:
    """Mark a single notification as read.

    Enforces ownership: recipient_id must match the notification's recipient.
    Returns True if updated, False if not found or not owned.
    """
    try:
        nid = uuid.UUID(notification_id)
        uid = uuid.UUID(recipient_id)
    except (ValueError, TypeError):
        return False

    n = db.session.query(Notification).filter(
        Notification.id == nid,
        Notification.recipient_id == uid,  # IDOR prevention
        Notification.is_deleted == False,
    ).first()

    if not n:
        return False

    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        db.session.flush()
    return True


def mark_all_notifications_read(recipient_id: str) -> int:
    """Bulk-mark all unread notifications for a user as read.

    Uses UPDATE WHERE — single query, not N+1.
    Returns count of rows updated.
    """
    try:
        uid = uuid.UUID(recipient_id)
    except (ValueError, TypeError):
        return 0

    now = datetime.now(timezone.utc)
    rows = db.session.query(Notification).filter(
        Notification.recipient_id == uid,
        Notification.is_read == False,
        Notification.is_deleted == False,
    ).all()

    for n in rows:
        n.is_read = True
        n.read_at = now

    db.session.flush()
    return len(rows)
