"""Notification Service — Sprint 11.

Orchestrates in-app notification persistence and optional async email delivery.

Flow:
    Business event (upload / approval / rejection)
        ↓
    notify_*()  — creates DB record, fires email Celery task
        ↓
    Notification persisted (always, even if email fails)
        ↓
    Email task (async, retried 3×, skipped if SMTP not configured)

Ownership rules (enforced here AND in the repository):
    - Recipient is always resolved server-side from the resource author_id / JWT
    - Client cannot supply an arbitrary recipient_id

Institution isolation:
    - institution_id is denormalized from the author's JWT / DB record
    - All queries filter by recipient_id (which is already institution-scoped via auth)

Security:
    - notification content must not include passwords, tokens, paths, or credentials
    - Email delivery is async (Celery) — HTTP response is never blocked
"""
import uuid
import logging
from typing import Optional

from app.extensions import db
from app.repositories.notification_repository import (
    create_notification,
    get_notifications_for_user,
    get_unread_count,
    mark_notification_read,
    mark_all_notifications_read,
)

logger = logging.getLogger(__name__)

# Human-readable titles and messages for each notification type
_TEMPLATES = {
    "resource.uploaded": {
        "title": "New Resource Pending Review",
        "message": "A new resource \"{title}\" has been submitted and is awaiting review.",
    },
    "resource.approved": {
        "title": "Your Resource Was Approved",
        "message": "Your resource \"{title}\" has been approved and is now publicly available.",
    },
    "resource.rejected": {
        "title": "Your Resource Was Rejected",
        "message": "Your resource \"{title}\" was not approved. Reason: {reason}",
    },
    "resource.changes_requested": {
        "title": "Changes Requested",
        "message": "Changes have been requested for your resource \"{title}\". Feedback: {feedback}",
    },
}


def _render(notification_type: str, **kwargs) -> tuple[str, str]:
    """Render title + message for a notification type."""
    tpl = _TEMPLATES.get(notification_type, {})
    title = tpl.get("title", notification_type)
    message = tpl.get("message", "").format_map({k: (v or "") for k, v in kwargs.items()})
    return title, message


def _queue_email(recipient_email: str, subject: str, body: str) -> None:
    """Queue an async email notification via Celery. Never raises."""
    if not recipient_email:
        return
    try:
        from app.tasks.email import send_notification_email
        send_notification_email.delay(recipient_email, subject, body)
    except Exception:
        logger.warning("Failed to queue notification email", exc_info=True)


def _get_user_email(user_id: str) -> Optional[str]:
    """Look up the user's email from the DB. Returns None on failure."""
    try:
        from app.models.user import User
        user = db.session.query(User).filter(
            User.id == uuid.UUID(user_id),
            User.is_deleted == False,
        ).first()
        return user.email if user else None
    except Exception:
        return None


# ── Public notification creators ─────────────────────────────────────────────

def notify_resource_uploaded(
    resource_id: str,
    resource_title: str,
    uploader_institution_id: str,
    moderator_ids: list[str],
) -> None:
    """Notify moderators/admins in the institution that a new resource is pending.

    Recipients: all moderator/admin user IDs in the institution (passed in by
    the caller — service does not query roles itself to avoid coupling).

    Called from upload_service after commit. Never raises.
    """
    if not moderator_ids:
        return
    notification_type = "resource.uploaded"
    title, message = _render(notification_type, title=resource_title)

    for mod_id in moderator_ids:
        try:
            n = create_notification(
                recipient_id=mod_id,
                notification_type=notification_type,
                title=title,
                message=message,
                institution_id=uploader_institution_id,
                resource_id=resource_id,
                action_url=f"/resources/{resource_id}",
            )
            if n:
                db.session.commit()
                email = _get_user_email(mod_id)
                _queue_email(email, title, message)
        except Exception:
            logger.warning("Failed to notify moderator %s of upload", mod_id, exc_info=True)


def notify_resource_approved(
    resource_id: str,
    resource_title: str,
    author_id: str,
    institution_id: str,
) -> None:
    """Notify the resource author that their resource was approved. Never raises."""
    notification_type = "resource.approved"
    title, message = _render(notification_type, title=resource_title)
    try:
        n = create_notification(
            recipient_id=author_id,
            notification_type=notification_type,
            title=title,
            message=message,
            institution_id=institution_id,
            resource_id=resource_id,
            action_url=f"/resources/{resource_id}",
        )
        if n:
            db.session.commit()
            email = _get_user_email(author_id)
            _queue_email(email, title, message)
    except Exception:
        logger.warning("Failed to send approved notification for resource %s", resource_id, exc_info=True)


def notify_resource_rejected(
    resource_id: str,
    resource_title: str,
    author_id: str,
    institution_id: str,
    reason: str = "",
) -> None:
    """Notify the resource author that their resource was rejected. Never raises."""
    notification_type = "resource.rejected"
    title, message = _render(notification_type, title=resource_title, reason=reason or "No reason provided")
    try:
        n = create_notification(
            recipient_id=author_id,
            notification_type=notification_type,
            title=title,
            message=message,
            institution_id=institution_id,
            resource_id=resource_id,
            action_url=f"/resources/{resource_id}",
        )
        if n:
            db.session.commit()
            email = _get_user_email(author_id)
            _queue_email(email, title, message)
    except Exception:
        logger.warning("Failed to send rejected notification for resource %s", resource_id, exc_info=True)


def notify_resource_changes_requested(
    resource_id: str,
    resource_title: str,
    author_id: str,
    institution_id: str,
    feedback: str = "",
) -> None:
    """Notify the resource author that changes were requested. Never raises."""
    notification_type = "resource.changes_requested"
    title, message = _render(notification_type, title=resource_title, feedback=feedback or "Please review the feedback")
    try:
        n = create_notification(
            recipient_id=author_id,
            notification_type=notification_type,
            title=title,
            message=message,
            institution_id=institution_id,
            resource_id=resource_id,
            action_url=f"/resources/{resource_id}",
        )
        if n:
            db.session.commit()
            email = _get_user_email(author_id)
            _queue_email(email, title, message)
    except Exception:
        logger.warning("Failed to send changes_requested notification for resource %s", resource_id, exc_info=True)


# ── User-facing retrieval/mutation ────────────────────────────────────────────

class NotificationService:
    """Thin wrapper over repository functions — primarily for blueprint use."""

    def get_notifications(
        self,
        recipient_id: str,
        unread_only: bool = False,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[dict], int]:
        """Return paginated safe notification dicts + total count."""
        items, total = get_notifications_for_user(
            recipient_id=recipient_id,
            unread_only=unread_only,
            page=page,
            limit=limit,
        )
        return [n.to_safe_dict() for n in items], total

    def get_unread_count(self, recipient_id: str) -> int:
        return get_unread_count(recipient_id)

    def mark_read(self, notification_id: str, recipient_id: str) -> bool:
        """Mark a notification read. Returns False if not found or not owned."""
        result = mark_notification_read(notification_id, recipient_id)
        if result:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                return False
        return result

    def mark_all_read(self, recipient_id: str) -> int:
        """Bulk mark all notifications as read. Returns count updated."""
        count = mark_all_notifications_read(recipient_id)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return 0
        return count
