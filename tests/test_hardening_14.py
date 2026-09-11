"""Sprint 14 Hardening — Security regression tests.

HARDENING 1 — Academic API security tests
HARDENING 2 — Instructor Assignment integrity tests
"""
import uuid
import pytest

from app.extensions import db
from app.models.user import User
from app.models.academic import Institution, Department, Degree, Program, AcademicSession, Semester, Subject
from app.models.enrollment import InstructorAssignment, AcademicYear
from app.utils.token import generate_access_token
from app.permissions.roles import Role
from app.services.enrollment_service import EnrollmentService


# ── Helpers ────────────────────────────────────────────────────────────────────

class _FakeUser:
    def __init__(self, role=Role.FACULTY, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"u_{uuid.uuid4().hex[:6]}@h-test.edu"


def _token(app, role=Role.STUDENT, institution_id=None, user_id=None):
    u = _FakeUser(role=role, institution_id=institution_id, user_id=user_id)
    with app.app_context():
        return generate_access_token(u), u


def _make_institution(code=None):
    iid = uuid.uuid4()
    inst = Institution(
        id=iid,
        name=f"Hardening Uni {iid.hex[:4]}",
        short_name="HU",
        code=code or f"HU{iid.hex[:4]}",
        domain_whitelist=[],
        settings_json={},
    )
    db.session.add(inst)
    db.session.flush()
    return str(inst.id)


def _make_db_user(institution_id, role=Role.FACULTY, status="active", user_id=None):
    uid = uuid.UUID(user_id) if user_id else uuid.uuid4()
    iid = uuid.UUID(institution_id) if isinstance(institution_id, str) else institution_id
    email = f"u_{uid.hex[:8]}@h-test.edu"
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


def _make_academic_chain(institution_id):
    """Create: Degree → Department → Program → AcademicSession → Semester → Subject."""
    iid = uuid.UUID(institution_id) if isinstance(institution_id, str) else institution_id

    deg = Degree(id=uuid.uuid4(), name="B.Tech Hard", level="undergraduate")
    db.session.add(deg)
    db.session.flush()

    dept = Department(id=uuid.uuid4(), name=f"Dept {uuid.uuid4().hex[:4]}", institution_id=iid)
    db.session.add(dept)
    db.session.flush()

    prog = Program(id=uuid.uuid4(), name="Hard Program", department_id=dept.id, degree_id=deg.id)
    db.session.add(prog)
    db.session.flush()

    session = AcademicSession(id=uuid.uuid4(), name="2027-28", start_year=2027, end_year=2028)
    db.session.add(session)
    db.session.flush()

    sem = Semester(id=uuid.uuid4(), name="Sem 1", academic_session_id=session.id, number=1, is_active=True)
    db.session.add(sem)
    db.session.flush()

    subj = Subject(
        id=uuid.uuid4(),
        code=f"HRD{uuid.uuid4().hex[:4].upper()}",
        name="Hardening Subject",
        program_id=prog.id,
        semester_id=sem.id,
        credits=3,
    )
    db.session.add(subj)
    db.session.flush()

    return str(subj.id), str(sem.id), str(prog.id), str(dept.id)


# ══════════════════════════════════════════════════════════════════════════════
# HARDENING 1 — Academic API security tests
# ══════════════════════════════════════════════════════════════════════════════

# ── GET /academic/institutions ────────────────────────────────────────────────

def test_academic_institutions_requires_auth(client):
    """Unauthenticated request to /academic/institutions must be rejected."""
    assert client.get('/api/v1/academic/institutions').status_code == 401


def test_academic_institutions_authenticated_user_allowed(app, client):
    """Authenticated user with an institution gets their own institution."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/academic/institutions',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()['data']
    assert isinstance(data, list)
    assert any(i['id'] == iid for i in data)


def test_academic_institutions_non_super_admin_sees_only_own(app, client):
    """FACULTY only sees their own institution, not another institution's."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid = _make_db_user(iid_a, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid_a, user_id=uid)
    r = client.get('/api/v1/academic/institutions',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    ids = [i['id'] for i in r.get_json()['data']]
    assert iid_a in ids
    assert iid_b not in ids


def test_academic_institutions_institution_id_query_param_ignored(app, client):
    """institution_id in query string must NOT override JWT institution scope."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid = _make_db_user(iid_a, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid_a, user_id=uid)
    # Attempt to pass another institution's ID as query param
    r = client.get(f'/api/v1/academic/institutions?institution_id={iid_b}',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    ids = [i['id'] for i in r.get_json()['data']]
    # Must see own (iid_a), must NOT see iid_b
    assert iid_a in ids
    assert iid_b not in ids


def test_academic_institutions_super_admin_sees_all(app, client):
    """SUPER_ADMIN sees all institutions."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        db.session.commit()

    token, _ = _token(app, role=Role.SUPER_ADMIN, institution_id=iid_a)
    r = client.get('/api/v1/academic/institutions',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    ids = [i['id'] for i in r.get_json()['data']]
    assert iid_a in ids
    assert iid_b in ids


def test_academic_institutions_no_sensitive_fields(app, client):
    """Institution response must not expose settings_json secrets or internal fields."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/academic/institutions',
                   headers={'Authorization': f'Bearer {token}'})
    for inst in r.get_json()['data']:
        for sensitive in ('settings_json', 'domain_whitelist', 'max_storage_bytes',
                          'subscription_expires_at', 'accreditation_code'):
            assert sensitive not in inst, f"Sensitive field '{sensitive}' leaked"


# ── GET /academic/departments ─────────────────────────────────────────────────

def test_academic_departments_requires_auth(client):
    assert client.get('/api/v1/academic/departments').status_code == 401


def test_academic_departments_scoped_to_jwt_institution(app, client):
    """Departments scoped to actor's institution via JWT, not query param."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid = _make_db_user(iid_a, role=Role.FACULTY)
        # dept in institution A (created via _make_academic_chain)
        _, _, _, dept_id_a = _make_academic_chain(iid_a)
        _, _, _, dept_id_b = _make_academic_chain(iid_b)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid_a, user_id=uid)
    r = client.get('/api/v1/academic/departments',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    dept_ids = [d['id'] for d in r.get_json()['data']]
    assert dept_id_a in dept_ids
    assert dept_id_b not in dept_ids


def test_academic_departments_institution_id_param_ignored_for_non_super_admin(app, client):
    """Non-SUPER_ADMIN cannot see another institution's departments via ?institution_id=."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid = _make_db_user(iid_a, role=Role.STUDENT)
        _, _, _, dept_id_b = _make_academic_chain(iid_b)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid_a, user_id=uid)
    r = client.get(f'/api/v1/academic/departments?institution_id={iid_b}',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    dept_ids = [d['id'] for d in r.get_json()['data']]
    assert dept_id_b not in dept_ids


def test_academic_departments_invalid_institution_uuid_safe(app, client):
    """Invalid UUID in institution_id query param handled safely (no crash)."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.SUPER_ADMIN, institution_id=iid)
    r = client.get('/api/v1/academic/departments?institution_id=not-a-uuid',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data'] == []


# ── GET /academic/subjects ────────────────────────────────────────────────────

def test_academic_subjects_requires_auth(client):
    assert client.get('/api/v1/academic/subjects').status_code == 401


def test_academic_subjects_scoped_to_own_institution(app, client):
    """Subjects filtered via dept→prog chain; cannot see other institution's subjects."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid = _make_db_user(iid_a, role=Role.STUDENT)
        subj_a, _, _, _ = _make_academic_chain(iid_a)
        subj_b, _, _, _ = _make_academic_chain(iid_b)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid_a, user_id=uid)
    r = client.get('/api/v1/academic/subjects',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    subj_ids = [s['id'] for s in r.get_json()['data']]
    assert subj_a in subj_ids
    assert subj_b not in subj_ids


def test_academic_subjects_invalid_program_id_safe(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/academic/subjects?program_id=not-a-uuid',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data'] == []


# ── POST /academic/subjects ───────────────────────────────────────────────────

def test_academic_create_subject_requires_auth(client):
    r = client.post('/api/v1/academic/subjects',
                    json={"code": "X", "name": "X", "program_id": str(uuid.uuid4()), "semester_id": str(uuid.uuid4())})
    assert r.status_code == 401


def test_academic_create_subject_faculty_forbidden(app, client):
    """FACULTY does not have institutions:manage."""
    token, _ = _token(app, role=Role.FACULTY, institution_id=str(uuid.uuid4()))
    r = client.post('/api/v1/academic/subjects',
                    json={"code": "X", "name": "X", "program_id": str(uuid.uuid4()), "semester_id": str(uuid.uuid4())},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_academic_create_subject_student_forbidden(app, client):
    """STUDENT does not have institutions:manage."""
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.post('/api/v1/academic/subjects',
                    json={"code": "X", "name": "X", "program_id": str(uuid.uuid4()), "semester_id": str(uuid.uuid4())},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_academic_create_subject_institution_admin_cross_institution_rejected(app, client):
    """INSTITUTION_ADMIN cannot create a subject in another institution's program."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_admin = _make_db_user(iid_a, role=Role.INSTITUTION_ADMIN)
        # Program belongs to institution B
        _, sem_b, prog_b, _ = _make_academic_chain(iid_b)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_a, user_id=uid_admin)
    r = client.post('/api/v1/academic/subjects',
                    json={"code": "XTEST", "name": "Bad Subject", "program_id": prog_b, "semester_id": sem_b},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_academic_create_subject_institution_admin_own_institution_allowed(app, client):
    """INSTITUTION_ADMIN can create a subject in their own institution's program."""
    with app.app_context():
        iid = _make_institution()
        uid_admin = _make_db_user(iid, role=Role.INSTITUTION_ADMIN)
        _, sem_id, prog_id, _ = _make_academic_chain(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=uid_admin)
    r = client.post('/api/v1/academic/subjects',
                    json={"code": f"OK{uuid.uuid4().hex[:4].upper()}", "name": "Valid Subject",
                          "program_id": prog_id, "semester_id": sem_id},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 201


def test_academic_create_subject_missing_fields(app, client):
    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=str(uuid.uuid4()))
    r = client.post('/api/v1/academic/subjects',
                    json={"code": "X"},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 400


def test_academic_create_subject_invalid_program_uuid(app, client):
    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=str(uuid.uuid4()))
    r = client.post('/api/v1/academic/subjects',
                    json={"code": "X", "name": "X", "program_id": "bad", "semester_id": str(uuid.uuid4())},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# HARDENING 2 — Instructor Assignment integrity tests
# ══════════════════════════════════════════════════════════════════════════════

def test_assign_instructor_same_institution_succeeds(app):
    """Happy path: instructor and course are in the same institution."""
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        db.session.commit()

        svc = EnrollmentService()
        result, err = svc.assign_instructor(
            instructor_id=uid_fac,
            course_id=subj_id,
            semester_id=sem_id,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        assert err is None, f"Expected success but got error: {err}"
        assert result is not None
        assert result['instructor_id'] == uid_fac
        assert result['course_id'] == subj_id


def test_assign_instructor_mismatched_instructor_institution_rejected(app):
    """Instructor from institution B cannot be assigned to institution A's course."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_fac_b = _make_db_user(iid_b, role=Role.FACULTY)
        # Course belongs to institution A
        subj_id_a, sem_id_a, _, _ = _make_academic_chain(iid_a)
        db.session.commit()

        svc = EnrollmentService()
        result, err = svc.assign_instructor(
            instructor_id=uid_fac_b,
            course_id=subj_id_a,
            semester_id=sem_id_a,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid_a,
        )
        assert err is not None
        # IDOR-safe message
        assert "not found" in err.lower() or "denied" in err.lower()


def test_assign_instructor_mismatched_actor_institution_rejected(app):
    """Actor from institution B cannot assign to institution A's course."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_fac_a = _make_db_user(iid_a, role=Role.FACULTY)
        subj_id_a, sem_id_a, _, _ = _make_academic_chain(iid_a)
        db.session.commit()

        svc = EnrollmentService()
        result, err = svc.assign_instructor(
            instructor_id=uid_fac_a,
            course_id=subj_id_a,
            semester_id=sem_id_a,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid_b,  # wrong actor institution
        )
        assert err is not None


def test_assign_instructor_institution_id_from_db_not_caller(app):
    """institution_id on the assignment must come from DB, not from any caller-supplied value."""
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        db.session.commit()

        svc = EnrollmentService()
        result, err = svc.assign_instructor(
            instructor_id=uid_fac,
            course_id=subj_id,
            semester_id=sem_id,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        assert err is None
        # institution_id on the result must match the instructor's actual institution
        assert result['institution_id'] == iid


def test_assign_instructor_duplicate_rejected(app):
    """Second assignment of same instructor/course/semester raises duplicate error."""
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        db.session.commit()

        svc = EnrollmentService()
        _, err1 = svc.assign_instructor(uid_fac, subj_id, sem_id, Role.INSTITUTION_ADMIN, iid)
        assert err1 is None

        _, err2 = svc.assign_instructor(uid_fac, subj_id, sem_id, Role.INSTITUTION_ADMIN, iid)
        assert err2 is not None
        assert "already" in err2.lower() or "duplicate" in err2.lower()


def test_assign_instructor_student_role_rejected(app):
    """A STUDENT cannot be assigned as an instructor."""
    with app.app_context():
        iid = _make_institution()
        uid_stu = _make_db_user(iid, role=Role.STUDENT)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        db.session.commit()

        svc = EnrollmentService()
        result, err = svc.assign_instructor(
            instructor_id=uid_stu,
            course_id=subj_id,
            semester_id=sem_id,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        assert err is not None
        assert "eligible" in err.lower() or "not" in err.lower()


def test_assign_instructor_ghost_instructor_rejected(app):
    """Non-existent instructor_id returns error, not crash."""
    with app.app_context():
        iid = _make_institution()
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        phantom_uid = str(uuid.uuid4())
        db.session.commit()

        svc = EnrollmentService()
        result, err = svc.assign_instructor(
            instructor_id=phantom_uid,
            course_id=subj_id,
            semester_id=sem_id,
            actor_role=Role.SUPER_ADMIN,
            actor_institution_id=None,
        )
        assert err is not None


def test_assign_instructor_invalid_uuid_rejected(app):
    """Invalid UUID format returns clean error."""
    with app.app_context():
        iid = _make_institution()
        db.session.commit()

        svc = EnrollmentService()
        result, err = svc.assign_instructor(
            instructor_id="not-a-uuid",
            course_id=str(uuid.uuid4()),
            semester_id=str(uuid.uuid4()),
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        assert err is not None
        assert "invalid" in err.lower()


def test_assign_instructor_ghost_course_rejected(app):
    """Non-existent course returns error."""
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        _, sem_id, _, _ = _make_academic_chain(iid)
        phantom_course = str(uuid.uuid4())
        db.session.commit()

        svc = EnrollmentService()
        result, err = svc.assign_instructor(
            instructor_id=uid_fac,
            course_id=phantom_course,
            semester_id=sem_id,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid,
        )
        assert err is not None
        assert "not found" in err.lower()


def test_assign_instructor_super_admin_can_cross_institution(app):
    """SUPER_ADMIN can assign an instructor across institutions (platform-level)."""
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        db.session.commit()

        svc = EnrollmentService()
        # SUPER_ADMIN actor with None institution_id (cross-institution)
        result, err = svc.assign_instructor(
            instructor_id=uid_fac,
            course_id=subj_id,
            semester_id=sem_id,
            actor_role=Role.SUPER_ADMIN,
            actor_institution_id=None,
        )
        # Should succeed: instructor and course are in same institution;
        # SUPER_ADMIN bypass only skips actor isolation check, not instructor/course integrity
        assert err is None
        assert result is not None


def test_assign_instructor_cross_institution_via_tampered_param_rejected(app):
    """
    Attacker scenario: institution A admin tries to assign institution B instructor
    to institution A's course by calling assign_instructor with iid_a as actor.
    The instructor's institution_id is resolved from DB and must not match the course's.
    """
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_fac_b = _make_db_user(iid_b, role=Role.FACULTY)
        subj_id_a, sem_id_a, _, _ = _make_academic_chain(iid_a)
        db.session.commit()

        svc = EnrollmentService()
        # Admin from institution A tries to assign faculty from institution B
        result, err = svc.assign_instructor(
            instructor_id=uid_fac_b,    # faculty from B
            course_id=subj_id_a,        # course from A
            semester_id=sem_id_a,
            actor_role=Role.INSTITUTION_ADMIN,
            actor_institution_id=iid_a,  # actor from A — but instructor from B
        )
        # Must fail: instructor_institution_id (B) != course_institution_id (A)
        assert err is not None
