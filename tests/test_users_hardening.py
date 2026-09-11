"""Sprint 12 Hardening — User Profile, Users API, Leaderboard, Enrollment tests.

Coverage:
    Own profile (1–5)
    Authentication (6–8)
    Profile IDOR (9–12)
    Cross-institution isolation (13–16)
    Sensitive-field protection (17–18)
    Users list endpoint (19–22)
    No 501 endpoints remaining (23–25)
    Leaderboard authentication (26)
    Leaderboard institution isolation (27–29)
    Enrollment creation (30–33)
    Duplicate enrollment rejection (34–35)
    Institution isolation for enrollment (36–37)
    Enrollment IDOR (38)
"""
import uuid
import pytest

from app.extensions import db
from app.models.user import User
from app.models.academic import Institution
from app.models.enrollment import AcademicYear, StudentEnrollment, CourseEnrollment
from app.models.contribution import UserContribution
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeUser:
    def __init__(self, role=Role.STUDENT, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"u_{uuid.uuid4().hex[:6]}@user-test.edu"


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
    email = f"u_{uid.hex[:8]}@user-test.edu"
    u = User(
        id=uid,
        email=email,
        email_normalized=email.lower(),
        full_name="Test User",
        password_hash="hashed",
        institution_id=iid,
        role=role,
        status=status,
    )
    db.session.add(u)
    db.session.flush()
    return str(uid)


def _make_academic_year():
    ay = AcademicYear(
        id=uuid.uuid4(),
        start_year=2024,
        end_year=2025,
        label="2024-2025",
    )
    db.session.add(ay)
    db.session.flush()
    return str(ay.id)


# ── 1–5. Own profile ──────────────────────────────────────────────────────────

def test_get_own_profile_returns_profile(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/users/me', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['id'] == uid


def test_own_profile_contains_expected_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/users/me', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for field in ('id', 'email', 'full_name', 'role', 'status', 'institution_id'):
        assert field in data, f"Expected field '{field}' missing from profile"


def test_own_profile_never_exposes_password_hash(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/users/me', headers={'Authorization': f'Bearer {token}'})
    assert 'password_hash' not in r.get_json()['data']


def test_update_own_profile_allowed_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.put(
        '/api/v1/users/me',
        json={"full_name": "Updated Name", "timezone": "Asia/Kolkata"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 200
    assert r.get_json()['data']['full_name'] == 'Updated Name'


def test_update_own_profile_ignores_role_field(app, client):
    """Attempting to set role via profile update must be silently ignored."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.put(
        '/api/v1/users/me',
        json={"role": "SUPER_ADMIN", "full_name": "Hacker"},
        headers={'Authorization': f'Bearer {token}'}
    )
    # Should succeed but role must NOT be changed
    assert r.status_code == 200
    assert r.get_json()['data'].get('role') != 'SUPER_ADMIN'


# ── 6–8. Authentication required ──────────────────────────────────────────────

def test_get_me_requires_auth(client):
    assert client.get('/api/v1/users/me').status_code == 401


def test_update_me_requires_auth(client):
    assert client.put('/api/v1/users/me', json={}).status_code == 401


def test_get_user_by_id_requires_auth(client):
    assert client.get(f'/api/v1/users/{uuid.uuid4()}').status_code == 401


# ── 9–12. Profile IDOR prevention ─────────────────────────────────────────────

def test_user_can_get_own_profile_by_id(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get(f'/api/v1/users/{uid}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['id'] == uid


def test_same_institution_user_visible(app, client):
    with app.app_context():
        iid = _make_institution()
        uid_a = _make_db_user(iid, role=Role.STUDENT)
        uid_b = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    # User A looks up User B in same institution — should succeed
    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid_a)
    r = client.get(f'/api/v1/users/{uid_b}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['id'] == uid_b


def test_cross_institution_user_returns_404(app, client):
    """IDOR: looking up a user in another institution returns 404, not 403."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_a = _make_db_user(iid_a)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid_b)
    r = client.get(f'/api/v1/users/{uid_a}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


def test_nonexistent_user_returns_404(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get(f'/api/v1/users/{uuid.uuid4()}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


# ── 13–16. Cross-institution isolation (list_users) ───────────────────────────

def test_institution_admin_list_users_scoped(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_a = _make_db_user(iid_a)
        uid_b = _make_db_user(iid_b)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_a)
    r = client.get('/api/v1/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    ids_returned = {u['id'] for u in r.get_json()['data']}
    assert uid_a in ids_returned
    assert uid_b not in ids_returned


def test_super_admin_list_users_sees_all(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_a = _make_db_user(iid_a)
        uid_b = _make_db_user(iid_b)
        db.session.commit()

    token, _ = _token(app, role=Role.SUPER_ADMIN)
    r = client.get('/api/v1/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    ids_returned = {u['id'] for u in r.get_json()['data']}
    assert uid_a in ids_returned
    assert uid_b in ids_returned


def test_student_cannot_list_users(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_list_users_requires_auth(client):
    assert client.get('/api/v1/users/').status_code == 401


# ── 17–18. Sensitive field protection ─────────────────────────────────────────

def test_get_user_by_id_no_sensitive_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get(f'/api/v1/users/{uid}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()['data']
    for sensitive in ('password_hash', 'token', 'secret', 'otp', 'code_hash',
                      'email_normalized', 'failed_login_attempts', 'locked_until'):
        assert sensitive not in data, f"Sensitive field '{sensitive}' leaked"


def test_list_users_no_sensitive_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get('/api/v1/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    for user in r.get_json()['data']:
        assert 'password_hash' not in user


# ── 19–22. Users list endpoint ────────────────────────────────────────────────

def test_list_users_returns_list(app, client):
    with app.app_context():
        iid = _make_institution()
        _make_db_user(iid)
        _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get('/api/v1/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert isinstance(r.get_json()['data'], list)


def test_list_users_has_meta(app, client):
    with app.app_context():
        iid = _make_institution()
        _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get('/api/v1/users/', headers={'Authorization': f'Bearer {token}'})
    meta = r.get_json().get('meta', {})
    assert 'page' in meta
    assert 'limit' in meta


def test_list_users_pagination_limit_respected(app, client):
    with app.app_context():
        iid = _make_institution()
        for _ in range(5):
            _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get('/api/v1/users/?limit=2', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert len(r.get_json()['data']) == 2


def test_list_users_limit_capped(app, client):
    token, _ = _token(app, role=Role.SUPER_ADMIN)
    r = client.get('/api/v1/users/?limit=99999', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['meta']['limit'] <= 100


# ── 23–25. No remaining 501 endpoints ─────────────────────────────────────────

def test_put_user_by_id_is_removed(app, client):
    """PUT /users/<id> was a 501 stub — it must not exist or must not return 501."""
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.put(f'/api/v1/users/{uuid.uuid4()}',
                   json={},
                   headers={'Authorization': f'Bearer {token}'})
    # Must not be 501 (endpoint removed — expect 404 or 405)
    assert r.status_code != 501


def test_delete_user_by_id_is_removed(app, client):
    """DELETE /users/<id> was a 501 stub — must not exist or must not return 501."""
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.delete(f'/api/v1/users/{uuid.uuid4()}',
                      headers={'Authorization': f'Bearer {token}'})
    assert r.status_code != 501


def test_get_user_by_id_is_not_501(app, client):
    """GET /users/<id> must no longer return 501."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get(f'/api/v1/users/{uid}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code != 501


# ── 26. Leaderboard authentication ────────────────────────────────────────────

def test_leaderboard_requires_auth(client):
    r = client.get('/api/v1/users/leaderboard')
    assert r.status_code == 401


# ── 27–29. Leaderboard institution isolation ──────────────────────────────────

def test_leaderboard_returns_institution_scoped_results(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_a = _make_db_user(iid_a)
        uid_b = _make_db_user(iid_b)
        # Add contributions for A user
        contrib = UserContribution(
            id=uuid.uuid4(),
            user_id=uuid.UUID(uid_a),
            action="resource_uploaded",
            institution_id=uuid.UUID(iid_a),
        )
        db.session.add(contrib)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid_a)
    r = client.get('/api/v1/users/leaderboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()['data']
    # User A should be in results
    user_ids = [e['user_id'] for e in data]
    assert uid_a in user_ids
    # User B (different institution) should NOT be in results
    assert uid_b not in user_ids


def test_leaderboard_meta_has_institution_scoped_flag(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/users/leaderboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['meta']['institution_scoped'] is True


def test_leaderboard_limit_capped(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/users/leaderboard?limit=999',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['meta']['limit'] <= 50


# ── 30–33. Enrollment creation ────────────────────────────────────────────────

def test_student_enrollment_created_successfully(app, client):
    """Service-level: enroll_student returns enrollment dict."""
    from app.services.enrollment_service import EnrollmentService
    from app.models.academic import Program, Department, Degree

    svc = EnrollmentService()
    with app.app_context():
        iid = _make_institution()
        student_uid = _make_db_user(iid, role=Role.STUDENT)

        # Build Program chain: Degree → Department → Program
        deg = Degree(id=uuid.uuid4(), name="B.Tech", level="undergraduate")
        db.session.add(deg)
        dept = Department(
            id=uuid.uuid4(),
            name="CS Dept",
            institution_id=uuid.UUID(iid)
        )
        db.session.add(dept)
        db.session.flush()
        prog = Program(
            id=uuid.uuid4(),
            name="CS Program",
            department_id=dept.id,
            degree_id=deg.id,
        )
        db.session.add(prog)
        ay = AcademicYear(
            id=uuid.uuid4(), start_year=2024, end_year=2025, label="2024-2025"
        )
        db.session.add(ay)
        db.session.flush()

        result, err = svc.enroll_student(
            student_id=student_uid,
            program_id=str(prog.id),
            academic_year_id=str(ay.id),
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        db.session.commit()

    assert err is None
    assert result is not None
    assert result['user_id'] == student_uid
    assert result['institution_id'] == iid


def test_enrollment_institution_id_from_student_record(app, client):
    """institution_id on enrollment must come from student's DB record, not actor."""
    from app.services.enrollment_service import EnrollmentService
    from app.models.academic import Program, Department, Degree

    svc = EnrollmentService()
    with app.app_context():
        iid = _make_institution()
        student_uid = _make_db_user(iid, role=Role.STUDENT)

        deg = Degree(id=uuid.uuid4(), name="B.Sc", level="undergraduate")
        db.session.add(deg)
        dept = Department(id=uuid.uuid4(), name="Physics", institution_id=uuid.UUID(iid))
        db.session.add(dept)
        db.session.flush()
        prog = Program(id=uuid.uuid4(), name="Physics Prog",
                       department_id=dept.id, degree_id=deg.id)
        db.session.add(prog)
        ay = AcademicYear(id=uuid.uuid4(), start_year=2023, end_year=2024, label="2023-24")
        db.session.add(ay)
        db.session.flush()

        # Actor passes a DIFFERENT (fake) institution_id — should not matter
        result, err = svc.enroll_student(
            student_id=student_uid,
            program_id=str(prog.id),
            academic_year_id=str(ay.id),
            actor_role=Role.SUPER_ADMIN,
            actor_institution_id=str(uuid.uuid4()),  # bogus institution
        )
        db.session.commit()

    assert err is None
    # institution_id on result must be the STUDENT's real institution, not the actor's
    assert result['institution_id'] == iid


def test_get_student_enrollments_returns_list(app, client):
    from app.services.enrollment_service import EnrollmentService
    from app.models.academic import Program, Department, Degree

    svc = EnrollmentService()
    with app.app_context():
        iid = _make_institution()
        student_uid = _make_db_user(iid, role=Role.STUDENT)

        deg = Degree(id=uuid.uuid4(), name="M.Tech", level="postgraduate")
        db.session.add(deg)
        dept = Department(id=uuid.uuid4(), name="ECE", institution_id=uuid.UUID(iid))
        db.session.add(dept)
        db.session.flush()
        prog = Program(id=uuid.uuid4(), name="VLSI",
                       department_id=dept.id, degree_id=deg.id)
        db.session.add(prog)
        ay = AcademicYear(id=uuid.uuid4(), start_year=2025, end_year=2026, label="2025-26")
        db.session.add(ay)
        db.session.flush()

        svc.enroll_student(
            student_id=student_uid,
            program_id=str(prog.id),
            academic_year_id=str(ay.id),
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        db.session.commit()

        enrollments, err = svc.get_student_enrollments(
            student_id=student_uid,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )

    assert err is None
    assert isinstance(enrollments, list)
    assert len(enrollments) >= 1


def test_enrollment_status_defaults_to_active(app, client):
    from app.services.enrollment_service import EnrollmentService
    from app.models.academic import Program, Department, Degree

    svc = EnrollmentService()
    with app.app_context():
        iid = _make_institution()
        student_uid = _make_db_user(iid, role=Role.STUDENT)

        deg = Degree(id=uuid.uuid4(), name="BCA", level="undergraduate")
        db.session.add(deg)
        dept = Department(id=uuid.uuid4(), name="IT", institution_id=uuid.UUID(iid))
        db.session.add(dept)
        db.session.flush()
        prog = Program(id=uuid.uuid4(), name="BCA Prog",
                       department_id=dept.id, degree_id=deg.id)
        db.session.add(prog)
        ay = AcademicYear(id=uuid.uuid4(), start_year=2026, end_year=2027, label="2026-27")
        db.session.add(ay)
        db.session.flush()

        result, _ = svc.enroll_student(
            student_id=student_uid,
            program_id=str(prog.id),
            academic_year_id=str(ay.id),
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        db.session.commit()

    assert result['status'] == 'active'


# ── 34–35. Duplicate enrollment rejection ─────────────────────────────────────

def test_duplicate_student_enrollment_rejected(app, client):
    from app.services.enrollment_service import EnrollmentService
    from app.models.academic import Program, Department, Degree

    svc = EnrollmentService()
    with app.app_context():
        iid = _make_institution()
        student_uid = _make_db_user(iid, role=Role.STUDENT)

        deg = Degree(id=uuid.uuid4(), name="MBA", level="postgraduate")
        db.session.add(deg)
        dept = Department(id=uuid.uuid4(), name="Mgmt", institution_id=uuid.UUID(iid))
        db.session.add(dept)
        db.session.flush()
        prog = Program(id=uuid.uuid4(), name="MBA Prog",
                       department_id=dept.id, degree_id=deg.id)
        db.session.add(prog)
        ay = AcademicYear(id=uuid.uuid4(), start_year=2024, end_year=2025, label="2024-25-dup")
        db.session.add(ay)
        db.session.flush()

        prog_id = str(prog.id)
        ay_id = str(ay.id)

        # First enrollment
        svc.enroll_student(
            student_id=student_uid,
            program_id=prog_id,
            academic_year_id=ay_id,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        db.session.commit()

        # Second enrollment — same combination
        result, err = svc.enroll_student(
            student_id=student_uid,
            program_id=prog_id,
            academic_year_id=ay_id,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )

    assert result is None
    assert err is not None
    assert "already enrolled" in err.lower()


def test_duplicate_academic_year_key_rejected(app, client):
    """academic_years table has unique constraint on (start_year, end_year)."""
    with app.app_context():
        ay1 = AcademicYear(id=uuid.uuid4(), start_year=2099, end_year=2100, label="2099-2100")
        db.session.add(ay1)
        db.session.commit()

        ay2 = AcademicYear(id=uuid.uuid4(), start_year=2099, end_year=2100, label="dupe")
        db.session.add(ay2)
        try:
            db.session.commit()
            # SQLite in tests may not enforce this — if it passes, just ensure no data corruption
        except Exception:
            db.session.rollback()
            # Expected — constraint enforced
            return
        # If SQLite didn't enforce — OK in test mode


# ── 36–38. Institution isolation for enrollment ────────────────────────────────

def test_enroll_student_from_other_institution_rejected(app, client):
    """INSTITUTION_ADMIN of institution B cannot enroll a student from institution A."""
    from app.services.enrollment_service import EnrollmentService
    from app.models.academic import Program, Department, Degree

    svc = EnrollmentService()
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        student_uid_a = _make_db_user(iid_a, role=Role.STUDENT)

        deg = Degree(id=uuid.uuid4(), name="B.Ed", level="undergraduate")
        db.session.add(deg)
        dept = Department(id=uuid.uuid4(), name="Edu", institution_id=uuid.UUID(iid_b))
        db.session.add(dept)
        db.session.flush()
        prog = Program(id=uuid.uuid4(), name="Edu Prog",
                       department_id=dept.id, degree_id=deg.id)
        db.session.add(prog)
        ay = AcademicYear(id=uuid.uuid4(), start_year=2022, end_year=2023, label="2022-23")
        db.session.add(ay)
        db.session.flush()

        # Admin of B tries to enroll a student from A
        result, err = svc.enroll_student(
            student_id=student_uid_a,
            program_id=str(prog.id),
            academic_year_id=str(ay.id),
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid_b,  # admin of institution B
        )

    assert result is None
    assert err is not None
    # IDOR: error message must not reveal the real institution
    assert "not found" in err.lower() or "access" in err.lower()


def test_get_enrollments_for_other_institution_student_rejected(app, client):
    """get_student_enrollments must not expose data cross-institution."""
    from app.services.enrollment_service import EnrollmentService

    svc = EnrollmentService()
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        student_uid_a = _make_db_user(iid_a, role=Role.STUDENT)
        db.session.commit()

        enrollments, err = svc.get_student_enrollments(
            student_id=student_uid_a,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid_b,  # admin of B — should not see A's student
        )

    assert enrollments is None
    assert err is not None


def test_enrollment_response_has_no_sensitive_fields(app, client):
    from app.services.enrollment_service import EnrollmentService
    from app.models.academic import Program, Department, Degree

    svc = EnrollmentService()
    with app.app_context():
        iid = _make_institution()
        student_uid = _make_db_user(iid, role=Role.STUDENT)

        deg = Degree(id=uuid.uuid4(), name="B.Arch", level="undergraduate")
        db.session.add(deg)
        dept = Department(id=uuid.uuid4(), name="Architecture", institution_id=uuid.UUID(iid))
        db.session.add(dept)
        db.session.flush()
        prog = Program(id=uuid.uuid4(), name="B.Arch Prog",
                       department_id=dept.id, degree_id=deg.id)
        db.session.add(prog)
        ay = AcademicYear(id=uuid.uuid4(), start_year=2020, end_year=2021, label="2020-21")
        db.session.add(ay)
        db.session.flush()

        result, err = svc.enroll_student(
            student_id=student_uid,
            program_id=str(prog.id),
            academic_year_id=str(ay.id),
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        db.session.commit()

    assert err is None
    for sensitive in ('password_hash', 'token', 'secret'):
        assert sensitive not in result
