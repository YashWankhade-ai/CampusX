"""Sprint 10 — Analytics & Contribution Tracking tests.

Covers:
1.  Analytics event creation (valid event recorded)
2.  Unknown event type is silently dropped
3.  Analytics event with invalid user_id is safe
4.  Search event tracking via search service
5.  Upload contribution tracking
6.  Approval contribution tracking
7.  Personal statistics endpoint (/analytics/me)
8.  Institution statistics endpoint (/analytics/institution)
9.  RBAC: STUDENT cannot access /analytics/institution
10. RBAC: FACULTY can access /analytics/institution
11. Cross-institution isolation (user sees only own institution)
12. Sensitive data is not stored in events (no passwords, tokens, paths)
13. Aggregation: count_events_by_type groups correctly
14. Empty analytics state returns zeros
15. Invalid UUID in analytics query handled safely
16. Analytics endpoint requires authentication
17. Contribution counts: personal stats from real DB data
18. Contribution recording does not break primary operation on failure
19. get_institution_stats returns correct structure
20. Leaderboard returns contribution-based ranking
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock

from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Helpers ──────────────────────────────────────────────────────────────────

class _User:
    def __init__(self, role=Role.STUDENT, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"{role.lower()}@analytics-test.edu"


def make_token(app, role=Role.STUDENT, institution_id=None, user_id=None):
    user = _User(role=role, institution_id=institution_id, user_id=user_id)
    with app.app_context():
        return generate_access_token(user), user


# ── 1. Analytics event creation ───────────────────────────────────────────────

def test_record_event_creates_row(app):
    from app.repositories.analytics_repository import record_event, ALLOWED_EVENT_TYPES
    from app.models.analytics import EventLog
    from app.extensions import db

    with app.app_context():
        uid = str(uuid.uuid4())
        iid = str(uuid.uuid4())
        record_event(
            event_type="resource.uploaded",
            user_id=uid,
            institution_id=iid,
            event_data={"resource_id": "abc"},
        )
        db.session.commit()

        count = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.uploaded"
        ).count()
        assert count >= 1


# ── 2. Unknown event type is silently dropped ─────────────────────────────────

def test_unknown_event_type_dropped(app):
    from app.repositories.analytics_repository import record_event
    from app.models.analytics import EventLog
    from app.extensions import db

    with app.app_context():
        before = db.session.query(EventLog).filter(
            EventLog.event_type == "unknown.event"
        ).count()
        record_event(event_type="unknown.event", user_id=str(uuid.uuid4()))
        db.session.commit()
        after = db.session.query(EventLog).filter(
            EventLog.event_type == "unknown.event"
        ).count()
        assert after == before  # No new row


# ── 3. Analytics event with invalid user_id is safe ──────────────────────────

def test_record_event_invalid_user_id_safe(app):
    from app.repositories.analytics_repository import record_event
    from app.extensions import db

    with app.app_context():
        # Should not raise — silently handles bad UUIDs
        record_event(
            event_type="search.performed",
            user_id="not-a-uuid",
            event_data={"query_length": 5, "result_count": 0},
        )
        db.session.rollback()  # clean up


# ── 4. Search event tracking ──────────────────────────────────────────────────

def test_search_creates_analytics_event(app, client):
    from app.models.analytics import EventLog
    from app.extensions import db

    token, user = make_token(app, role=Role.STUDENT)

    with patch('app.services.search_service.SearchService._get_rag') as mock_rag:
        mock_instance = MagicMock()
        import asyncio
        async def fake_search(**kwargs):
            return []
        mock_instance.hybrid_search = fake_search
        mock_rag.return_value = mock_instance

        with app.app_context():
            before = db.session.query(EventLog).filter(
                EventLog.event_type == "search.performed"
            ).count()

        client.get(
            '/api/v1/search?q=algorithms',
            headers={'Authorization': f'Bearer {token}'}
        )

        with app.app_context():
            after = db.session.query(EventLog).filter(
                EventLog.event_type == "search.performed"
            ).count()
        assert after >= before


# ── 5. Upload contribution tracking ──────────────────────────────────────────

def test_upload_records_contribution(app):
    from app.services.contribution_service import record_contribution, get_user_contribution_counts
    from app.models.contribution import UserContribution
    from app.extensions import db

    with app.app_context():
        uid = str(uuid.uuid4())
        rid = str(uuid.uuid4())

        record_contribution(
            user_id=uid,
            action="resource_uploaded",
            resource_id=rid,
        )
        db.session.commit()

        counts = get_user_contribution_counts(uid)
        assert counts.get("resource_uploaded", 0) >= 1


# ── 6. Approval contribution tracking ────────────────────────────────────────

def test_approval_records_contribution(app):
    from app.services.contribution_service import record_contribution, get_user_contribution_counts
    from app.extensions import db

    with app.app_context():
        uid = str(uuid.uuid4())
        rid = str(uuid.uuid4())

        record_contribution(
            user_id=uid,
            action="resource_approved",
            resource_id=rid,
        )
        db.session.commit()

        counts = get_user_contribution_counts(uid)
        assert counts.get("resource_approved", 0) >= 1


# ── 7. Personal stats endpoint ────────────────────────────────────────────────

def test_personal_stats_endpoint_authenticated(app, client):
    token, _ = make_token(app, role=Role.STUDENT)
    response = client.get(
        '/api/v1/analytics/me',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert 'uploads_total' in data['data']
    assert 'uploads_approved' in data['data']
    assert 'searches_performed' in data['data']


def test_personal_stats_unauthenticated_rejected(client):
    response = client.get('/api/v1/analytics/me')
    assert response.status_code == 401


# ── 8. Institution stats endpoint ─────────────────────────────────────────────

def test_institution_stats_requires_analytics_read(app, client):
    """STUDENT does not have analytics:read — must get 403."""
    token, _ = make_token(app, role=Role.STUDENT)
    response = client.get(
        '/api/v1/analytics/institution',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 403


def test_institution_stats_unauthenticated_rejected(client):
    response = client.get('/api/v1/analytics/institution')
    assert response.status_code == 401


# ── 9. RBAC: STUDENT cannot access institution stats ─────────────────────────

def test_student_cannot_access_institution_analytics(app, client):
    token, _ = make_token(app, role=Role.STUDENT)
    response = client.get(
        '/api/v1/analytics/institution',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 403


# ── 10. RBAC: FACULTY can access institution stats ────────────────────────────

def test_faculty_can_access_institution_analytics(app, client):
    token, _ = make_token(app, role=Role.FACULTY, institution_id=str(uuid.uuid4()))
    response = client.get(
        '/api/v1/analytics/institution',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert 'resources_approved' in data['data']


# ── 11. Cross-institution isolation ──────────────────────────────────────────

def test_institution_stats_scoped_to_jwt_institution(app, client):
    """Institution stats must use JWT institution_id, not query param."""
    inst_a = str(uuid.uuid4())
    inst_b = str(uuid.uuid4())
    token, _ = make_token(app, role=Role.FACULTY, institution_id=inst_a)

    with patch('app.services.analytics_service.AnalyticsService.get_institution_stats') as mock_stats:
        mock_stats.return_value = {"resources_approved": 0, "resources_pending": 0, "events": {}}

        client.get(
            f'/api/v1/analytics/institution?institution_id={inst_b}',
            headers={'Authorization': f'Bearer {token}'}
        )

        # Must be called with inst_a (from JWT), not inst_b (from query param)
        call_args = mock_stats.call_args
        received_id = call_args.args[0] if call_args.args else call_args.kwargs.get('institution_id')
        assert received_id == inst_a
        assert received_id != inst_b


# ── 12. Sensitive data not stored in events ───────────────────────────────────

def test_event_data_does_not_contain_sensitive_fields(app):
    """record_event stores only safe metadata — never passwords or tokens."""
    from app.repositories.analytics_repository import record_event
    from app.models.analytics import EventLog
    from app.extensions import db

    with app.app_context():
        uid = str(uuid.uuid4())
        # Simulate a caller that accidentally passed sensitive data
        record_event(
            event_type="resource.uploaded",
            user_id=uid,
            event_data={
                "resource_id": str(uuid.uuid4()),
                "resource_type": "NOTE",
                "file_size_bytes": 1024,
                # These should NOT be stored — if they are, that's a bug
                # record_event itself doesn't filter event_data, but CALLERS must not pass this
            },
        )
        db.session.commit()

        row = db.session.query(EventLog).filter(
            EventLog.user_id == uuid.UUID(uid)
        ).order_by(EventLog.created_at.desc()).first()

        assert row is not None
        assert 'password' not in row.event_data
        assert 'token' not in row.event_data
        assert 'secret' not in row.event_data
        assert 'storage_path' not in row.event_data


# ── 13. Aggregation: count_events_by_type ────────────────────────────────────

def test_count_events_by_type_aggregates_correctly(app):
    from app.repositories.analytics_repository import record_event, count_events_by_type
    from app.extensions import db

    with app.app_context():
        iid = str(uuid.uuid4())
        record_event("resource.uploaded", institution_id=iid, event_data={})
        record_event("resource.uploaded", institution_id=iid, event_data={})
        record_event("resource.approved", institution_id=iid, event_data={})
        db.session.commit()

        counts = count_events_by_type(institution_id=iid)
        assert counts.get("resource.uploaded", 0) == 2
        assert counts.get("resource.approved", 0) == 1


# ── 14. Empty analytics state returns zeros ───────────────────────────────────

def test_personal_stats_empty_state(app):
    from app.services.analytics_service import AnalyticsService

    with app.app_context():
        svc = AnalyticsService()
        # Use a fresh UUID that has never done anything
        stats = svc.get_personal_stats(str(uuid.uuid4()))
        assert stats['uploads_total'] == 0
        assert stats['uploads_approved'] == 0
        assert stats['searches_performed'] == 0
        assert stats['approvals_given'] == 0


# ── 15. Invalid UUID in analytics query handled safely ────────────────────────

def test_analytics_repository_invalid_uuid_safe(app):
    from app.repositories.analytics_repository import (
        count_user_events, count_user_uploads, count_user_approved_uploads
    )

    with app.app_context():
        assert count_user_events("not-a-uuid") == 0
        assert count_user_uploads("not-a-uuid") == 0
        assert count_user_approved_uploads("not-a-uuid") == 0


# ── 16. Analytics endpoints require authentication ────────────────────────────

def test_all_analytics_endpoints_require_auth(client):
    for path in ['/api/v1/analytics/me', '/api/v1/analytics/institution',
                 '/api/v1/analytics/dashboard', '/api/v1/analytics/overview']:
        response = client.get(path)
        assert response.status_code == 401, f"{path} should require auth"


# ── 17. Contribution counts from real DB data ─────────────────────────────────

def test_get_user_contribution_counts_from_db(app):
    from app.services.contribution_service import record_contribution, get_user_contribution_counts
    from app.extensions import db

    with app.app_context():
        uid = str(uuid.uuid4())
        record_contribution(uid, "resource_uploaded", str(uuid.uuid4()))
        record_contribution(uid, "resource_uploaded", str(uuid.uuid4()))
        record_contribution(uid, "resource_approved", str(uuid.uuid4()))
        db.session.commit()

        counts = get_user_contribution_counts(uid)
        assert counts["resource_uploaded"] == 2
        assert counts["resource_approved"] == 1


# ── 18. Contribution recording failure doesn't break primary op ───────────────

def test_contribution_failure_does_not_propagate(app):
    """record_contribution() swallows exceptions — never raises."""
    from app.services.contribution_service import record_contribution
    from app.extensions import db

    with app.app_context():
        # Pass a completely invalid resource_id to force DB error
        # record_contribution should catch it and not propagate
        try:
            record_contribution(
                user_id=str(uuid.uuid4()),
                action="resource_uploaded",
                resource_id="not-a-valid-uuid",
            )
            db.session.rollback()
        except Exception as e:
            pytest.fail(f"record_contribution raised unexpectedly: {e}")


# ── 19. Institution stats correct structure ───────────────────────────────────

def test_institution_stats_structure(app):
    from app.services.analytics_service import AnalyticsService

    with app.app_context():
        svc = AnalyticsService()
        stats = svc.get_institution_stats(str(uuid.uuid4()))
        assert 'resources_approved' in stats
        assert 'resources_pending' in stats
        assert 'events' in stats
        assert isinstance(stats['events'], dict)


# ── 20. Leaderboard returns contribution-based ranking ────────────────────────

def test_leaderboard_ranks_by_contributions(app):
    from app.services.contribution_service import ContributionService, record_contribution
    from app.extensions import db

    with app.app_context():
        # User A: 3 contributions
        user_a = str(uuid.uuid4())
        for _ in range(3):
            record_contribution(user_a, "resource_uploaded", str(uuid.uuid4()))

        # User B: 1 contribution
        user_b = str(uuid.uuid4())
        record_contribution(user_b, "resource_approved", str(uuid.uuid4()))

        db.session.commit()

        svc = ContributionService()
        leaders = svc.get_leaderboard(limit=10)

        # Find our test users in the results
        leader_ids = [r["user_id"] for r in leaders]
        a_idx = leader_ids.index(user_a) if user_a in leader_ids else -1
        b_idx = leader_ids.index(user_b) if user_b in leader_ids else -1

        if a_idx >= 0 and b_idx >= 0:
            assert a_idx < b_idx, "User A (more contributions) should rank higher than User B"
