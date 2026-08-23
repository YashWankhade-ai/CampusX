"""Analytics Repository — Sprint 10.

Synchronous SQLAlchemy repository (Flask is sync — no async here).
All queries accept institution_id to enforce tenant isolation.
Aggregation is done in the database, not in Python loops.
"""
import uuid
import logging
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import func, and_

from app.extensions import db
from app.models.analytics import EventLog, ResourceView
from app.models.resource import StudyMaterial

logger = logging.getLogger(__name__)

# Allowed event types — only these are stored
ALLOWED_EVENT_TYPES = frozenset({
    "resource.uploaded",
    "resource.approved",
    "resource.rejected",
    "resource.changes_requested",
    "resource.viewed",
    "search.performed",
})


def record_event(
    event_type: str,
    user_id: Optional[str] = None,
    institution_id: Optional[str] = None,
    event_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Record an application event.

    Silently drops events with unknown types.
    Never raises — analytics failures must not break primary operations.
    Sensitive fields (passwords, tokens, paths) must NOT be in event_data.
    """
    if event_type not in ALLOWED_EVENT_TYPES:
        logger.debug("Dropping unknown event type: %s", event_type)
        return

    try:
        uid = uuid.UUID(user_id) if user_id else None
        iid = uuid.UUID(institution_id) if institution_id else None
        event = EventLog(
            user_id=uid,
            institution_id=iid,
            event_type=event_type,
            event_data=event_data or {},
        )
        db.session.add(event)
        db.session.flush()  # Write in current transaction — caller commits
    except Exception:
        logger.warning("Failed to record analytics event: %s", event_type, exc_info=True)


def record_resource_view(
    resource_id: str,
    user_id: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> None:
    """Record a resource view. Never raises."""
    try:
        view = ResourceView(
            resource_id=uuid.UUID(resource_id),
            user_id=uuid.UUID(user_id) if user_id else None,
            institution_id=uuid.UUID(institution_id) if institution_id else None,
        )
        db.session.add(view)
        db.session.flush()
    except Exception:
        logger.warning("Failed to record resource view", exc_info=True)


# ── Aggregation queries ────────────────────────────────────────────────────

def count_events_by_type(
    institution_id: Optional[str] = None,
    since: Optional[datetime] = None,
) -> Dict[str, int]:
    """Return {event_type: count} for institution, optionally filtered by date."""
    query = db.session.query(
        EventLog.event_type,
        func.count(EventLog.id).label("cnt"),
    ).filter(EventLog.is_deleted == False)

    if institution_id:
        try:
            iid = uuid.UUID(institution_id)
            query = query.filter(EventLog.institution_id == iid)
        except (ValueError, TypeError):
            pass

    if since:
        query = query.filter(EventLog.created_at >= since)

    rows = query.group_by(EventLog.event_type).all()
    return {row.event_type: row.cnt for row in rows}


def count_user_events(
    user_id: str,
    event_type: Optional[str] = None,
) -> int:
    """Count events for a specific user, optionally filtered by type."""
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return 0

    query = db.session.query(func.count(EventLog.id)).filter(
        EventLog.user_id == uid,
        EventLog.is_deleted == False,
    )
    if event_type:
        query = query.filter(EventLog.event_type == event_type)
    return query.scalar() or 0


def count_approved_resources(institution_id: Optional[str] = None) -> int:
    """Count APPROVED study materials, optionally scoped to institution via author join."""
    from app.models.user import User

    query = db.session.query(func.count(StudyMaterial.id)).filter(
        StudyMaterial.status == "APPROVED",
        StudyMaterial.is_deleted == False,
    )
    if institution_id:
        try:
            iid = uuid.UUID(institution_id)
            query = query.join(User, StudyMaterial.author_id == User.id).filter(
                User.institution_id == iid
            )
        except (ValueError, TypeError):
            pass
    return query.scalar() or 0


def count_pending_resources(institution_id: Optional[str] = None) -> int:
    """Count resources waiting for review."""
    from app.models.user import User

    query = db.session.query(func.count(StudyMaterial.id)).filter(
        StudyMaterial.status.in_(["PENDING", "CHANGES_REQUESTED"]),
        StudyMaterial.is_deleted == False,
    )
    if institution_id:
        try:
            iid = uuid.UUID(institution_id)
            query = query.join(User, StudyMaterial.author_id == User.id).filter(
                User.institution_id == iid
            )
        except (ValueError, TypeError):
            pass
    return query.scalar() or 0


def count_user_uploads(user_id: str) -> int:
    """Count total resources uploaded by a user (any status)."""
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return 0
    return db.session.query(func.count(StudyMaterial.id)).filter(
        StudyMaterial.author_id == uid,
        StudyMaterial.is_deleted == False,
    ).scalar() or 0


def count_user_approved_uploads(user_id: str) -> int:
    """Count APPROVED resources uploaded by a user."""
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return 0
    return db.session.query(func.count(StudyMaterial.id)).filter(
        StudyMaterial.author_id == uid,
        StudyMaterial.status == "APPROVED",
        StudyMaterial.is_deleted == False,
    ).scalar() or 0


def count_user_approvals_given(user_id: str) -> int:
    """Count approval decisions made by a reviewer."""
    from app.models.approval import ApprovalAction
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return 0
    return db.session.query(func.count(ApprovalAction.id)).filter(
        ApprovalAction.approver_id == uid,
        ApprovalAction.action == "approved",
    ).scalar() or 0
