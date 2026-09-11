"""Sprint 11 — Notifications System tests.

Covers:
1.  Notification creation via repository
2.  Notification persisted (appears in DB)
3.  User retrieves own notifications (GET /)
4.  User cannot retrieve another user's notifications (IDOR prevention)
5.  Unread filter (GET /unread)
6.  Mark single notification read (POST /<id>/read)
7.  Marking another user's notification returns 404 (IDOR prevention)
8.  Mark all notifications read (POST /read-all)
9.  Pagination: page 1 of 2
10. Result limit enforced (max 100)
11. Unknown notification type is silently dropped
12. notify_resource_approved creates notification for author
13. notify_resource_rejected creates notification with reason
14. notify_resource_changes_requested creates notification with feedback
15. Email task is queued (mocked Celery)
16. Email delivery failure does not affect notification persistence
17. GET /notifications/ requires authentication
18. GET /notifications/unread requires authentication
19. GET /notifications/count requires authentication
20. Unread count via /count endpoint
21. Invalid UUID on mark-read returns 404
22. Notification content does not contain sensitive fields
23. Cross-institution: notifications from institution A not visible to institution B user
24. notify_resource_uploaded creates notifications for moderators
25. Notification failure does not break primary operation (upload)
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models.notification import Notification, NOTIFICATION_TYPES
from app.models.user import User
from app.models.resource import StudyMaterial, MaterialType
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeUser:
    def __init__(self, role=Role.STUDENT, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"u_{uuid.uuid4().hex[:6]}@notif-test.edu"


def _token(app, role=Role.STUDENT, institution_id=None, user_id=None):
    u = _FakeUser(role=role, institution_id=institution_id, user_id=user_id)
    with app.app_context():
        return generate_access_token(u), u


def _make_db_user(institution_id, user_id=None, role=Role.STUDENT):
    uid = uuid.UUID(user_id) if user_id else uuid.uuid4()
    iid = uuid.UUID(institution_id)
    email = f"u_{uid.hex[:8]}@notif.edu"
    u = User(
        id=uid,
        email=email,
        email_normalized=email.lower(),
        full_name="Test User",
        password_hash="hashed",
        institution_id=iid,
        role=role,
        status="active",
    )
    db.session.add(u)
    db.session.flush()
    return str(uid)


def _create_notification(recipient_id, notification_type="resource.approved",
                          institution_id=None, is_read=False):
    from app.repositories.notification_repository import create_notification
    n = create_notification(
        recipient_id=recipient_id,
        notification_type=notification_type,
        title="Test Notification",
        message="Test message body",
        institution_id=institution_id,
    )
    db.session.commit()
    return n


# ── 1. Notification creation via repository ───────────────────────────────────

def test_create_notification_persists(app):
    from app.repositories.notification_repository import create_notification
    with app.app_context():
        inst = str(uuid.uuid4())
        uid = _make_db_user(inst)
        n = create_notification(
            recipient_id=uid,
            notification_type="resource.approved",
            title="Approved",
            message="Your resource was approved",
            institution_id=inst,
        )
        db.session.commit()
        assert n is not None
        assert n.id is not None
        assert n.is_read is False


# ── 2. Notification persisted (appears in DB) ─────────────────────────────────

def test_notification_appears_in_db(app):
    from app.repositories.notification_repository import create_notification, get_notifications_for_user
    with app.app_context():
        inst = str(uuid.uuid4())
        uid = _make_db_user(inst)
        create_notification(
            recipient_id=uid,
            notification_type="resource.rejected",
            title="Rejected",
            message="Your resource was rejected",
        )
        db.session.commit()
        items, total = get_notifications_for_user(uid)
        assert total >= 1
        assert any(n.notification_type == "resource.rejected" for n in items)


# ── 3. User retrieves own notifications ───────────────────────────────────────

def test_get_own_notifications_endpoint(app, client):
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)
        _create_notification(uid, institution_id=inst)

    response = client.get(
        '/api/v1/notifications/',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)
    assert data['meta']['total'] >= 1


# ── 4. User cannot retrieve another user's notifications (IDOR) ───────────────

def test_idor_prevention_notifications(app, client):
    """Notifications are recipient-scoped — user B cannot see user A's notifications."""
    inst = str(uuid.uuid4())
    uid_a = str(uuid.uuid4())
    uid_b = str(uuid.uuid4())

    # Token for user B
    token_b, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid_b)

    with app.app_context():
        _make_db_user(inst, user_id=uid_a)
        _make_db_user(inst, user_id=uid_b)
        _create_notification(uid_a, institution_id=inst)  # Notification for A

    response = client.get(
        '/api/v1/notifications/',
        headers={'Authorization': f'Bearer {token_b}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    # B must not see A's notifications
    for n in data['data']:
        assert n.get('notification_type') != 'resource.approved' or True  # count-based check below

    # Verify count: B has no notifications of their own
    assert data['meta']['total'] == 0


# ── 5. Unread filter ──────────────────────────────────────────────────────────

def test_unread_filter(app, client):
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)
        # Create one read and one unread
        n_unread = _create_notification(uid, institution_id=inst)
        n_read = _create_notification(uid, notification_type="resource.rejected", institution_id=inst)
        n_read.is_read = True
        db.session.commit()

    response = client.get(
        '/api/v1/notifications/unread',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    for n in data['data']:
        assert n['is_read'] is False


# ── 6. Mark single notification read ──────────────────────────────────────────

def test_mark_single_notification_read(app, client):
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)
        n = _create_notification(uid, institution_id=inst)
        nid = str(n.id)

    response = client.post(
        f'/api/v1/notifications/{nid}/read',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200

    with app.app_context():
        updated = db.session.query(Notification).filter(
            Notification.id == uuid.UUID(nid)
        ).first()
        assert updated.is_read is True
        assert updated.read_at is not None


# ── 7. Marking another user's notification returns 404 ────────────────────────

def test_mark_other_users_notification_returns_404(app, client):
    """IDOR: user B cannot mark user A's notification as read."""
    inst = str(uuid.uuid4())
    uid_a = str(uuid.uuid4())
    uid_b = str(uuid.uuid4())
    token_b, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid_b)

    with app.app_context():
        _make_db_user(inst, user_id=uid_a)
        _make_db_user(inst, user_id=uid_b)
        n = _create_notification(uid_a, institution_id=inst)
        nid = str(n.id)

    response = client.post(
        f'/api/v1/notifications/{nid}/read',
        headers={'Authorization': f'Bearer {token_b}'}
    )
    assert response.status_code == 404


# ── 8. Mark all notifications read ────────────────────────────────────────────

def test_mark_all_notifications_read(app, client):
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)
        _create_notification(uid, institution_id=inst)
        _create_notification(uid, notification_type="resource.rejected", institution_id=inst)

    response = client.post(
        '/api/v1/notifications/read-all',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['marked_read'] == 2

    with app.app_context():
        from app.repositories.notification_repository import get_unread_count
        count = get_unread_count(uid)
    assert count == 0


# ── 9. Pagination ─────────────────────────────────────────────────────────────

def test_pagination_page_1_of_2(app, client):
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)
        for _ in range(5):
            _create_notification(uid, institution_id=inst)

    # Request page 1 with limit 3
    response = client.get(
        '/api/v1/notifications/?page=1&limit=3',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['data']) == 3
    assert data['meta']['total'] == 5
    assert data['meta']['limit'] == 3


# ── 10. Result limit enforced ─────────────────────────────────────────────────

def test_result_limit_capped_at_100(app, client):
    """Requesting limit=999 must be capped to 100."""
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)

    response = client.get(
        '/api/v1/notifications/?limit=999',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['limit'] <= 100


# ── 11. Unknown notification type is silently dropped ─────────────────────────

def test_unknown_notification_type_dropped(app):
    from app.repositories.notification_repository import create_notification
    with app.app_context():
        inst = str(uuid.uuid4())
        uid = _make_db_user(inst)
        result = create_notification(
            recipient_id=uid,
            notification_type="unknown.type",
            title="Bad",
            message="This should not persist",
        )
        db.session.rollback()
        assert result is None


# ── 12. notify_resource_approved creates notification for author ───────────────

def test_notify_resource_approved_creates_notification(app):
    from app.services.notification_service import notify_resource_approved
    with app.app_context():
        inst = str(uuid.uuid4())
        author_id = _make_db_user(inst)
        resource_id = str(uuid.uuid4())

        with patch('app.services.notification_service._queue_email'):
            notify_resource_approved(
                resource_id=resource_id,
                resource_title="Data Structures Notes",
                author_id=author_id,
                institution_id=inst,
            )

        n = db.session.query(Notification).filter(
            Notification.recipient_id == uuid.UUID(author_id),
            Notification.notification_type == "resource.approved",
        ).first()
        assert n is not None
        assert "Data Structures Notes" in n.message


# ── 13. notify_resource_rejected creates notification with reason ──────────────

def test_notify_resource_rejected_includes_reason(app):
    from app.services.notification_service import notify_resource_rejected
    with app.app_context():
        inst = str(uuid.uuid4())
        author_id = _make_db_user(inst)

        with patch('app.services.notification_service._queue_email'):
            notify_resource_rejected(
                resource_id=str(uuid.uuid4()),
                resource_title="Lecture Notes",
                author_id=author_id,
                institution_id=inst,
                reason="Poor quality scan",
            )

        n = db.session.query(Notification).filter(
            Notification.recipient_id == uuid.UUID(author_id),
            Notification.notification_type == "resource.rejected",
        ).first()
        assert n is not None
        assert "Poor quality scan" in n.message


# ── 14. notify_resource_changes_requested includes feedback ───────────────────

def test_notify_changes_requested_includes_feedback(app):
    from app.services.notification_service import notify_resource_changes_requested
    with app.app_context():
        inst = str(uuid.uuid4())
        author_id = _make_db_user(inst)

        with patch('app.services.notification_service._queue_email'):
            notify_resource_changes_requested(
                resource_id=str(uuid.uuid4()),
                resource_title="Assignment Guide",
                author_id=author_id,
                institution_id=inst,
                feedback="Please add table of contents",
            )

        n = db.session.query(Notification).filter(
            Notification.recipient_id == uuid.UUID(author_id),
            Notification.notification_type == "resource.changes_requested",
        ).first()
        assert n is not None
        assert "Please add table of contents" in n.message


# ── 15. Email task is queued ──────────────────────────────────────────────────

def test_email_task_queued_on_approval_notification(app):
    from app.services.notification_service import notify_resource_approved
    with app.app_context():
        inst = str(uuid.uuid4())
        author_id = _make_db_user(inst)

        with patch('app.services.notification_service._queue_email') as mock_email:
            notify_resource_approved(
                resource_id=str(uuid.uuid4()),
                resource_title="Test Resource",
                author_id=author_id,
                institution_id=inst,
            )
            assert mock_email.called


# ── 16. Email delivery failure does not affect notification persistence ─────────

def test_email_failure_does_not_prevent_notification_persistence(app):
    from app.services.notification_service import notify_resource_approved
    with app.app_context():
        inst = str(uuid.uuid4())
        author_id = _make_db_user(inst)

        with patch('app.services.notification_service._queue_email', side_effect=Exception("SMTP down")):
            notify_resource_approved(
                resource_id=str(uuid.uuid4()),
                resource_title="Resilience Test",
                author_id=author_id,
                institution_id=inst,
            )

        # Notification must still be persisted despite email failure
        n = db.session.query(Notification).filter(
            Notification.recipient_id == uuid.UUID(author_id),
            Notification.notification_type == "resource.approved",
        ).first()
        assert n is not None


# ── 17–19. Auth required on all endpoints ────────────────────────────────────

def test_notifications_list_requires_auth(client):
    assert client.get('/api/v1/notifications/').status_code == 401


def test_notifications_unread_requires_auth(client):
    assert client.get('/api/v1/notifications/unread').status_code == 401


def test_notifications_count_requires_auth(client):
    assert client.get('/api/v1/notifications/count').status_code == 401


# ── 20. Unread count endpoint ─────────────────────────────────────────────────

def test_unread_count_endpoint(app, client):
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)
        _create_notification(uid, institution_id=inst)
        _create_notification(uid, notification_type="resource.rejected", institution_id=inst)

    response = client.get(
        '/api/v1/notifications/count',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['unread_count'] == 2


# ── 21. Invalid UUID on mark-read returns 404 ─────────────────────────────────

def test_invalid_uuid_mark_read_returns_404(app, client):
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)

    response = client.post(
        '/api/v1/notifications/not-a-uuid/read',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 404


# ── 22. Notification content does not contain sensitive fields ────────────────

def test_notification_response_safe_fields_only(app, client):
    inst = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst, user_id=uid)

    with app.app_context():
        _make_db_user(inst, user_id=uid)
        _create_notification(uid, institution_id=inst)

    response = client.get(
        '/api/v1/notifications/',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    for n in response.get_json()['data']:
        sensitive = {'recipient_id', 'password', 'token', 'secret', 'storage_path',
                     'institution_id', 'email'}
        for field in sensitive:
            assert field not in n, f"Sensitive field '{field}' found in notification response"


# ── 23. Cross-institution isolation ──────────────────────────────────────────

def test_cross_institution_notifications_not_visible(app, client):
    """User in institution B cannot see notifications created for institution A."""
    inst_a = str(uuid.uuid4())
    inst_b = str(uuid.uuid4())
    uid_a = str(uuid.uuid4())
    uid_b = str(uuid.uuid4())
    token_b, _ = _token(app, role=Role.STUDENT, institution_id=inst_b, user_id=uid_b)

    with app.app_context():
        _make_db_user(inst_a, user_id=uid_a)
        _make_db_user(inst_b, user_id=uid_b)
        # Create a notification for user A (institution A)
        _create_notification(uid_a, institution_id=inst_a)

    # User B's list must be empty
    response = client.get(
        '/api/v1/notifications/',
        headers={'Authorization': f'Bearer {token_b}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['total'] == 0


# ── 24. notify_resource_uploaded notifies moderators ─────────────────────────

def test_notify_resource_uploaded_creates_for_moderators(app):
    from app.services.notification_service import notify_resource_uploaded
    with app.app_context():
        inst = str(uuid.uuid4())
        mod_id = _make_db_user(inst, role=Role.MODERATOR)

        with patch('app.services.notification_service._queue_email'):
            notify_resource_uploaded(
                resource_id=str(uuid.uuid4()),
                resource_title="Chemistry Notes",
                uploader_institution_id=inst,
                moderator_ids=[mod_id],
            )

        n = db.session.query(Notification).filter(
            Notification.recipient_id == uuid.UUID(mod_id),
            Notification.notification_type == "resource.uploaded",
        ).first()
        assert n is not None
        assert "Chemistry Notes" in n.message


# ── 25. Notification failure does not break primary operation ─────────────────

def test_notification_failure_does_not_break_primary_operation(app):
    """notify_resource_approved must not raise even if DB is in bad state."""
    from app.services.notification_service import notify_resource_approved
    with app.app_context():
        # Pass a completely invalid author_id to force an error
        try:
            notify_resource_approved(
                resource_id=str(uuid.uuid4()),
                resource_title="Test",
                author_id="not-a-uuid",  # Invalid — will fail
                institution_id=str(uuid.uuid4()),
            )
        except Exception as e:
            pytest.fail(f"notify_resource_approved raised unexpectedly: {e}")
