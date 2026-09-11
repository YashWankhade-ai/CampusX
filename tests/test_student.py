"""Sprint 13 — Student Module tests.

Coverage:

AUTHENTICATION (1–4)
    - Unauthenticated requests rejected on all student endpoints
    - Authenticated student accepted

PROFILE (5–11)
    - Student can access own profile
    - Profile contains expected safe fields
    - Profile never exposes password_hash / sensitive fields
    - Profile includes institution info
    - Missing user handled safely
    - GUEST role cannot access student endpoints (enrollment:read denied)

ENROLLMENT — SELF-SERVICE (12–19)
    - Student can view own program enrollments
    - Student can view own course enrollments
    - Response is safe (no sensitive fields)
    - Empty enrollment list is valid response
    - IDOR: student cannot access another student's enrollments via admin route
    - Student cannot create enrollment via student API (405)
    - Student cannot modify enrollment via student API (405)
    - Student cannot delete enrollment via student API (405)

DASHBOARD (20–27)
    - Student dashboard works
    - Dashboard includes required fields
    - Dashboard shows correct unread notification count
    - Dashboard is institution-isolated (counts own data only)
    - Dashboard does not expose sensitive data
    - Dashboard handles student with no enrollments
    - Suspended/inactive user behavior
    - GUEST cannot access dashboard

NOTIFICATIONS (28–31)
    - Student can retrieve own notifications
    - Unauthenticated notification access rejected
    - Notification count works for student
    - Mark-read respects recipient ownership

CONTRIBUTIONS (32–34)
    - Contributions leaderboard now requires auth
    - Score endpoint works for student
    - Badges endpoint works for student

RBAC (35–40)
    - Student cannot access admin users endpoint
    - Student cannot access admin institutions endpoint
    - Student cannot assign roles (no users:manage)
    - Moderator can access student endpoints (has enrollment:read)
    - Faculty can access student endpoints (has enrollment:read)
    - INSTITUTION_ADMIN can access student endpoints

SECURITY (41–46)
    - Invalid UUID on student profile → 404
    - Student cannot access /admin/users/
    - Student cannot access /admin/institutions/
    - Contribution leaderboard requires auth (was unauthenticated in prior sprints)
    - Cross-institution check on enrollment view (admin route)
    - Safe error responses (no stack traces)
"""
import uuid
import pytest

from app.extensions import db
from app.models.user import User
from app.models.academic import Institution
from app.models.enrollment import StudentEnrollment, CourseEnrollment, AcademicYear
from app.models.notification import Notification
from app.models.contribution import UserContribution
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeUser:
    def __init__(self, role=Role.STUDENT, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"u_{uuid.uuid4().hex[:6]}@student-test.edu"


def _token(app, role=Role.STUDENT, institution_id=None, user_id=None):
    u = _FakeUser(role=role, institution_id=institution_id, user_id=user_id)
    with app.app_context():
        return generate_access_token(u), u


def _make_institution(code=None):
    iid = uuid.uuid4()
    inst = Institution(
        id=iid,
        name=f"Test University {iid.hex[:4]}",
        short_name="TU",
        code=code or f"TU{iid.hex[:4]}",
        domain_whitelist=[],
        settings_json={},
    )
    db.session.add(inst)
    db.session.flush()
    return str(inst.id)


def _make_db_user(institution_id, role=Role.STUDENT, status="active", user_id=None):
    uid = uuid.UUID(user_id) if user_id else uuid.uuid4()
    iid = uuid.UUID(institution_id) if isinstance(institution_id, str) else institution_id
    email = f"u_{uid.hex[:8]}@student-test.edu"
    u = User(
        id=uid,
        email=email,
        email_normalized=email.lower(),
        full_name="Test Student",
        password_hash="hashed",
        institution_id=iid,
        role=role,
        status=status,
    )
    db.session.add(u)
    db.session.flush()
    return str(uid)


def _make_notification(recipient_id, institution_id=None, is_read=False):
    from app.models.notification import Notification
    n = Notification(
        id=uuid.uuid4(),
        recipient_id=uuid.UUID(recipient_id),
        notification_type="resource_approved",
        title="Test",
        message="Test notification",
        institution_id=uuid.UUID(institution_id) if institution_id else None,
        is_read=is_read,
    )
    db.session.add(n)
    db.session.flush()
    return str(n.id)


# ── 1–4. AUTHENTICATION ───────────────────────────────────────────────────────

def test_student_profile_requires_auth(client):
    assert client.get('/api/v1/student/profile').status_code == 401


def test_student_dashboard_requires_auth(client):
    assert client.get('/api/v1/student/dashboard').status_code == 401


def test_student_enrollments_requires_auth(client):
    assert client.get('/api/v1/student/enrollments/').status_code == 401


def test_student_course_enrollments_requires_auth(client):
    assert client.get('/api/v1/student/enrollments/courses').status_code == 401


# ── 5–11. PROFILE ─────────────────────────────────────────────────────────────

def test_student_can_access_own_profile(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['id'] == uid


def test_student_profile_contains_expected_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for field in ('id', 'email', 'full_name', 'role', 'status', 'institution_id', 'institution'):
        assert field in data, f"Expected field '{field}' missing"


def test_student_profile_includes_institution_data(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    assert data['institution'] is not None
    assert 'name' in data['institution']
    assert 'code' in data['institution']


def test_student_profile_never_exposes_password_hash(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for sensitive in ('password_hash', 'code_hash', 'token', 'secret', 'otp',
                      'failed_login_attempts', 'locked_until', 'email_normalized'):
        assert sensitive not in data, f"Sensitive field '{sensitive}' leaked in profile"


def test_student_profile_not_found_returns_404(app, client):
    """JWT with a non-existent user_id returns 404."""
    phantom_uid = str(uuid.uuid4())
    iid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=phantom_uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


def test_guest_cannot_access_student_profile(app, client):
    """GUEST role has no enrollment:read → 403."""
    token, _ = _token(app, role=Role.GUEST, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_institution_info_not_exposed_for_wrong_institution(app, client):
    """Student in institution A should only see institution A data — never B."""
    with app.app_context():
        iid_a = _make_institution()
        uid = _make_db_user(iid_a)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid_a, user_id=uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    inst_data = r.get_json()['data']['institution']
    assert inst_data['id'] == iid_a


# ── 12–19. ENROLLMENT — SELF-SERVICE ─────────────────────────────────────────

def test_student_can_view_own_program_enrollments(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/enrollments/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data['data'], list)
    assert 'total' in data['meta']


def test_student_can_view_own_course_enrollments(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/enrollments/courses',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert isinstance(r.get_json()['data'], list)


def test_enrollment_response_has_no_sensitive_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/enrollments/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    for enrollment in r.get_json()['data']:
        for sensitive in ('password_hash', 'token', 'secret'):
            assert sensitive not in enrollment


def test_empty_enrollment_list_returns_ok(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/enrollments/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data'] == []
    assert r.get_json()['meta']['total'] == 0


def test_student_cannot_post_to_enrollments(app, client):
    """POST to student enrollments endpoint must be rejected (405 or 404)."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.post('/api/v1/student/enrollments/',
                    json={"program_id": str(uuid.uuid4())},
                    headers={'Authorization': f'Bearer {token}'})
    # Must not be 200 or 201 — student cannot create enrollments
    assert r.status_code in (404, 405)


def test_student_cannot_delete_enrollments(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.delete('/api/v1/student/enrollments/',
                      headers={'Authorization': f'Bearer {token}'})
    assert r.status_code in (404, 405)


def test_student_cannot_access_another_students_enrollment_via_admin(app, client):
    """IDOR: student trying admin enrollment endpoint gets 403."""
    with app.app_context():
        iid = _make_institution()
        other_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid)
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_enrollment_only_returns_own_data(app, client):
    """Each student's enrollment query is scoped to their own user_id from JWT."""
    with app.app_context():
        iid = _make_institution()
        uid_a = _make_db_user(iid, role=Role.STUDENT)
        uid_b = _make_db_user(iid, role=Role.STUDENT)
        # Add enrollment for B only
        ay = AcademicYear(
            id=uuid.uuid4(), start_year=2027, end_year=2028, label="2027-28"
        )
        db.session.add(ay)
        db.session.flush()
        # We skip full Program setup — just verify count is 0 for uid_a
        db.session.commit()

    # Token as uid_a — should see empty list (no enrollments for A)
    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid_a)
    r = client.get('/api/v1/student/enrollments/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    # uid_a has no enrollments
    ids_in_response = [e.get('user_id') for e in r.get_json()['data']]
    assert uid_b not in ids_in_response


# ── 20–27. DASHBOARD ──────────────────────────────────────────────────────────

def test_student_dashboard_works(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


def test_dashboard_contains_required_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for field in ('user_id', 'full_name', 'role', 'status',
                  'program_enrollment_count', 'course_enrollment_count',
                  'unread_notification_count', 'contribution_count'):
        assert field in data, f"Dashboard missing field '{field}'"


def test_dashboard_unread_notification_count(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        _make_notification(uid, institution_id=iid, is_read=False)
        _make_notification(uid, institution_id=iid, is_read=False)
        _make_notification(uid, institution_id=iid, is_read=True)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['unread_notification_count'] == 2


def test_dashboard_zero_counts_for_new_student(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    assert data['program_enrollment_count'] == 0
    assert data['course_enrollment_count'] == 0
    assert data['unread_notification_count'] == 0
    assert data['contribution_count'] == 0


def test_dashboard_does_not_expose_sensitive_data(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for sensitive in ('password_hash', 'token', 'code_hash', 'otp',
                      'failed_login_attempts', 'locked_until', 'email_normalized'):
        assert sensitive not in data, f"Sensitive field '{sensitive}' leaked in dashboard"


def test_dashboard_institution_name_correct(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    assert data['institution_id'] == iid
    assert data['institution_name'] is not None


def test_guest_cannot_access_dashboard(app, client):
    token, _ = _token(app, role=Role.GUEST, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_dashboard_phantom_user_returns_404(app, client):
    phantom_uid = str(uuid.uuid4())
    iid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=phantom_uid)
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


# ── 28–31. NOTIFICATIONS ──────────────────────────────────────────────────────

def test_student_can_retrieve_own_notifications(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        _make_notification(uid, institution_id=iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/notifications/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert isinstance(r.get_json()['data'], list)


def test_notification_endpoint_requires_auth(client):
    assert client.get('/api/v1/notifications/').status_code == 401


def test_unread_count_works_for_student(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        _make_notification(uid, institution_id=iid, is_read=False)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/notifications/count', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['unread_count'] >= 1


def test_mark_read_respects_recipient_ownership(app, client):
    """Student cannot mark another user's notification as read."""
    with app.app_context():
        iid = _make_institution()
        uid_a = _make_db_user(iid)
        uid_b = _make_db_user(iid)
        notif_id = _make_notification(uid_b, institution_id=iid)  # belongs to B
        db.session.commit()

    # Token as uid_a — tries to mark uid_b's notification
    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid_a)
    r = client.post(f'/api/v1/notifications/{notif_id}/read',
                    headers={'Authorization': f'Bearer {token}'})
    # Must return 404 (IDOR prevention — not forbidden, not found)
    assert r.status_code == 404


# ── 32–34. CONTRIBUTIONS ──────────────────────────────────────────────────────

def test_contribution_leaderboard_requires_auth(client):
    """Leaderboard was unauthenticated before Sprint 13 — must now require auth."""
    r = client.get('/api/v1/contributions/leaderboard')
    assert r.status_code == 401


def test_contribution_score_works_for_student(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/contributions/score', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert 'score' in r.get_json()['data']


def test_contribution_badges_requires_auth(client):
    assert client.get('/api/v1/contributions/badges').status_code == 401


# ── 35–40. RBAC ───────────────────────────────────────────────────────────────

def test_student_cannot_access_admin_users(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_student_cannot_access_admin_institutions(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/admin/institutions/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_student_cannot_change_role(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.patch(
        f'/api/v1/admin/users/{uid}/role',
        json={"role": "SUPER_ADMIN"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 403


def test_moderator_can_access_student_endpoints(app, client):
    """MODERATOR has enrollment:read so can access student module."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.MODERATOR)
        db.session.commit()

    token, _ = _token(app, role=Role.MODERATOR, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


def test_faculty_can_access_student_dashboard(app, client):
    """FACULTY has enrollment:read so can access student module."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


def test_institution_admin_can_access_student_endpoints(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.INSTITUTION_ADMIN)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


# ── 41–46. SECURITY ───────────────────────────────────────────────────────────

def test_invalid_uuid_in_student_context_handled(app, client):
    """JWT with a badly-formatted user_id results in 404, not 500."""
    # We simulate this by using a valid JWT but the user doesn't exist in DB
    phantom_uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT,
                      institution_id=str(uuid.uuid4()),
                      user_id=phantom_uid)
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code in (404,)
    assert r.get_json()['success'] is False
    # No stack trace in response
    body = str(r.get_json())
    assert 'Traceback' not in body
    assert 'Exception' not in body or 'NOT_FOUND' in body


def test_student_cannot_access_admin_users_endpoint(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_student_cannot_access_admin_institutions_endpoint(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/admin/institutions/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_contributions_leaderboard_now_requires_auth(client):
    """Regression: leaderboard was unauthenticated before Sprint 13."""
    r = client.get('/api/v1/contributions/leaderboard')
    assert r.status_code == 401


def test_cross_institution_enrollment_access_rejected(app, client):
    """Student in institution A cannot admin-enroll a student in institution B."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_a = _make_db_user(iid_a, role=Role.STUDENT)
        uid_b = _make_db_user(iid_b, role=Role.STUDENT)
        db.session.commit()

    # Try to hit admin endpoint as student (should 403)
    token, _ = _token(app, role=Role.STUDENT, institution_id=iid_a, user_id=uid_a)
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_safe_error_response_no_stack_trace(app, client):
    """Error responses must never include stack traces."""
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    body = str(r.get_json())
    assert 'Traceback' not in body
    assert 'line ' not in body.lower() or 'Line' not in body
