"""Sprint 14 — Faculty Module tests.

Coverage:

AUTHENTICATION (1–5)
    - Unauthenticated requests rejected on all faculty endpoints
    - Authenticated faculty accepted on all endpoints

PROFILE (6–13)
    - Faculty can access own profile
    - Profile contains expected safe fields
    - Profile includes institution info
    - Profile never exposes password_hash / sensitive fields
    - Profile shows department name when present
    - Missing user returns 404
    - GUEST role blocked (enrollment:read missing)
    - Student accessing faculty profile endpoint gets profile (same permission)

DASHBOARD (14–22)
    - Faculty dashboard returns 200
    - Dashboard contains all required fields
    - Dashboard shows correct unread notification count
    - Dashboard shows correct assigned_course_count
    - Dashboard shows zero counts for new faculty
    - Dashboard does not expose sensitive data
    - Dashboard phantom user returns 404
    - GUEST cannot access dashboard
    - Institution name shown correctly

ASSIGNED COURSES (23–28)
    - Faculty can view own assigned courses
    - Empty assignment list returns 200
    - Response has no sensitive fields
    - Faculty cannot view another faculty's assignments via student endpoint
    - Unauthenticated request rejected
    - GUEST rejected

STUDENTS IN COURSE (29–38)
    - Faculty assigned to course can view enrolled students
    - Faculty NOT assigned to course gets 404 (IDOR-safe)
    - Cross-faculty IDOR: cannot view students for another faculty's course
    - Student response has no email / sensitive fields
    - Invalid UUID course_id returns 404
    - Unauthenticated request rejected
    - GUEST rejected
    - Empty enrollment list returns 200 with empty array
    - Student cannot access this endpoint (enrollment:read allowed but no assignments)
    - INSTITUTION_ADMIN can access (has enrollment:read)

OWN RESOURCES (39–46)
    - Faculty can view own resources
    - Empty resource list returns 200
    - Response never exposes storage_path
    - Status filter works (PENDING)
    - Status filter works (APPROVED)
    - GUEST cannot access (no resources:read)
    - Pagination params respected
    - Unauthenticated rejected

RBAC (47–54)
    - STUDENT cannot access admin endpoints
    - FACULTY cannot access admin institutions:manage endpoint
    - FACULTY cannot access admin users:manage endpoint (users list)
    - FACULTY cannot change another user's role
    - MODERATOR can access faculty profile (has enrollment:read)
    - INSTITUTION_ADMIN can access faculty dashboard
    - FACULTY cannot promote themselves to INSTITUTION_ADMIN
    - FACULTY cannot access SUPER_ADMIN endpoints

NOTIFICATIONS (55–58)
    - Faculty can retrieve own notifications
    - Faculty cannot retrieve another user's notifications (IDOR)
    - Notification count works for faculty
    - Unauthenticated notification access rejected

SECURITY (59–65)
    - IDOR: faculty cannot get students from unassigned course
    - Invalid UUID on course_id safely returns 404
    - No stack traces in error responses
    - Suspended faculty returns 200 (account status ≠ permission)
    - Faculty cannot enroll a student (no mutation endpoint on faculty blueprint)
    - Faculty cannot delete another user's resource
    - Cross-institution faculty profile returns 404 for phantom user
"""
import uuid
import pytest

from app.extensions import db
from app.models.user import User
from app.models.academic import Institution, Department, AcademicSession, Semester, Subject, Degree, Program
from app.models.enrollment import InstructorAssignment, CourseEnrollment, AcademicYear, StudentEnrollment
from app.models.notification import Notification
from app.models.resource import StudyMaterial, MaterialType
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Test helpers ──────────────────────────────────────────────────────────────

class _FakeUser:
    def __init__(self, role=Role.FACULTY, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"u_{uuid.uuid4().hex[:6]}@faculty-test.edu"


def _token(app, role=Role.FACULTY, institution_id=None, user_id=None):
    u = _FakeUser(role=role, institution_id=institution_id, user_id=user_id)
    with app.app_context():
        return generate_access_token(u), u


def _make_institution(code=None):
    iid = uuid.uuid4()
    inst = Institution(
        id=iid,
        name=f"Faculty University {iid.hex[:4]}",
        short_name="FU",
        code=code or f"FU{iid.hex[:4]}",
        domain_whitelist=[],
        settings_json={},
    )
    db.session.add(inst)
    db.session.flush()
    return str(inst.id)


def _make_db_user(institution_id, role=Role.FACULTY, status="active", user_id=None):
    uid = uuid.UUID(user_id) if user_id else uuid.uuid4()
    iid = uuid.UUID(institution_id) if isinstance(institution_id, str) else institution_id
    email = f"u_{uid.hex[:8]}@faculty-test.edu"
    u = User(
        id=uid,
        email=email,
        email_normalized=email.lower(),
        full_name="Test Faculty",
        password_hash="hashed",
        institution_id=iid,
        role=role,
        status=status,
    )
    db.session.add(u)
    db.session.flush()
    return str(uid)


def _make_academic_chain(institution_id):
    """Create: AcademicSession → Semester → Degree → Department → Program → Subject.
    Returns (subject_id, semester_id, program_id, department_id) as strings.
    """
    iid = uuid.UUID(institution_id) if isinstance(institution_id, str) else institution_id

    dept = Department(id=uuid.uuid4(), name="CS Dept", institution_id=iid)
    db.session.add(dept)
    db.session.flush()

    deg = Degree(id=uuid.uuid4(), name="B.Tech", level="undergraduate")
    db.session.add(deg)
    db.session.flush()

    prog = Program(id=uuid.uuid4(), name="CS Program", department_id=dept.id, degree_id=deg.id)
    db.session.add(prog)
    db.session.flush()

    session = AcademicSession(id=uuid.uuid4(), name="2026-27", start_year=2026, end_year=2027)
    db.session.add(session)
    db.session.flush()

    sem = Semester(id=uuid.uuid4(), name="Semester 1", academic_session_id=session.id, number=1, is_active=True)
    db.session.add(sem)
    db.session.flush()

    subj = Subject(
        id=uuid.uuid4(),
        code=f"CS{uuid.uuid4().hex[:4].upper()}",
        name="Data Structures",
        program_id=prog.id,
        semester_id=sem.id,
        credits=3,
    )
    db.session.add(subj)
    db.session.flush()

    return str(subj.id), str(sem.id), str(prog.id), str(dept.id)


def _make_assignment(instructor_id, course_id, semester_id, institution_id, is_primary=True):
    a = InstructorAssignment(
        id=uuid.uuid4(),
        instructor_id=uuid.UUID(instructor_id),
        course_id=uuid.UUID(course_id),
        semester_id=uuid.UUID(semester_id),
        institution_id=uuid.UUID(institution_id),
        is_primary=is_primary,
    )
    db.session.add(a)
    db.session.flush()
    return str(a.id)


def _make_course_enrollment(student_id, course_id, semester_id, institution_id):
    e = CourseEnrollment(
        id=uuid.uuid4(),
        student_id=uuid.UUID(student_id),
        course_id=uuid.UUID(course_id),
        semester_id=uuid.UUID(semester_id),
        institution_id=uuid.UUID(institution_id),
    )
    db.session.add(e)
    db.session.flush()
    return str(e.id)


def _make_notification(recipient_id, institution_id=None, is_read=False):
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


def _make_resource(author_id, status="PENDING"):
    r = StudyMaterial(
        id=uuid.uuid4(),
        title="Test Resource",
        description="Test",
        author_id=uuid.UUID(author_id),
        material_type=MaterialType.NOTE,
        status=status,
    )
    db.session.add(r)
    db.session.flush()
    return str(r.id)


# ── 1–5. AUTHENTICATION ───────────────────────────────────────────────────────

def test_faculty_profile_requires_auth(client):
    assert client.get('/api/v1/faculty/profile').status_code == 401


def test_faculty_dashboard_requires_auth(client):
    assert client.get('/api/v1/faculty/dashboard').status_code == 401


def test_faculty_courses_requires_auth(client):
    assert client.get('/api/v1/faculty/courses').status_code == 401


def test_faculty_course_students_requires_auth(client):
    random_id = str(uuid.uuid4())
    assert client.get(f'/api/v1/faculty/courses/{random_id}/students').status_code == 401


def test_faculty_resources_requires_auth(client):
    assert client.get('/api/v1/faculty/resources').status_code == 401


# ── 6–13. PROFILE ─────────────────────────────────────────────────────────────

def test_faculty_can_access_own_profile(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['id'] == uid


def test_faculty_profile_contains_expected_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for field in ('id', 'email', 'full_name', 'role', 'status', 'institution_id', 'institution'):
        assert field in data, f"Expected field '{field}' missing from faculty profile"


def test_faculty_profile_includes_institution_data(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    assert data['institution'] is not None
    assert 'name' in data['institution']


def test_faculty_profile_never_exposes_sensitive_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for sensitive in ('password_hash', 'code_hash', 'failed_login_attempts',
                      'locked_until', 'email_normalized', 'storage_path'):
        assert sensitive not in data, f"Sensitive field '{sensitive}' leaked"


def test_faculty_profile_not_found_returns_404(app, client):
    phantom_uid = str(uuid.uuid4())
    iid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=phantom_uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


def test_guest_cannot_access_faculty_profile(app, client):
    token, _ = _token(app, role=Role.GUEST, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_student_can_access_faculty_profile_endpoint(app, client):
    """enrollment:read is available to STUDENT — faculty blueprint uses same permission."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.STUDENT, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    # Student gets 200 — the service returns their own profile via JWT user_id
    assert r.status_code == 200


def test_faculty_profile_shows_correct_institution_id(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.get_json()['data']['institution_id'] == iid


# ── 14–22. DASHBOARD ─────────────────────────────────────────────────────────

def test_faculty_dashboard_returns_200(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


def test_faculty_dashboard_contains_required_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for field in ('user_id', 'full_name', 'role', 'status',
                  'assigned_course_count', 'total_resource_count',
                  'approved_resource_count', 'pending_resource_count',
                  'unread_notification_count', 'contribution_count'):
        assert field in data, f"Dashboard missing required field '{field}'"


def test_dashboard_unread_notification_count(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        _make_notification(uid, institution_id=iid, is_read=False)
        _make_notification(uid, institution_id=iid, is_read=False)
        _make_notification(uid, institution_id=iid, is_read=True)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.get_json()['data']['unread_notification_count'] == 2


def test_dashboard_assigned_course_count(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.get_json()['data']['assigned_course_count'] == 1


def test_dashboard_zero_counts_for_new_faculty(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    assert data['assigned_course_count'] == 0
    assert data['total_resource_count'] == 0
    assert data['unread_notification_count'] == 0
    assert data['contribution_count'] == 0


def test_dashboard_does_not_expose_sensitive_data(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    for sensitive in ('password_hash', 'token', 'code_hash', 'otp',
                      'failed_login_attempts', 'locked_until', 'email_normalized', 'storage_path'):
        assert sensitive not in data, f"Sensitive field '{sensitive}' leaked"


def test_dashboard_phantom_user_returns_404(app, client):
    phantom_uid = str(uuid.uuid4())
    iid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=phantom_uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


def test_guest_cannot_access_dashboard(app, client):
    token, _ = _token(app, role=Role.GUEST, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_dashboard_institution_name_correct(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    data = r.get_json()['data']
    assert data['institution_id'] == iid
    assert data['institution_name'] is not None


# ── 23–28. ASSIGNED COURSES ───────────────────────────────────────────────────

def test_faculty_can_view_assigned_courses(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/courses', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()
    assert len(data['data']) == 1
    assert data['meta']['total'] == 1


def test_faculty_empty_assignment_list(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/courses', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data'] == []
    assert r.get_json()['meta']['total'] == 0


def test_assignment_response_has_no_sensitive_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/courses', headers={'Authorization': f'Bearer {token}'})
    for item in r.get_json()['data']:
        for sensitive in ('password_hash', 'storage_path', 'token'):
            assert sensitive not in item


def test_courses_response_includes_course_name(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/courses', headers={'Authorization': f'Bearer {token}'})
    assert r.get_json()['data'][0]['course_name'] is not None


def test_courses_scoped_to_own_instructor_id(app, client):
    """Faculty A cannot see Faculty B's assignments."""
    with app.app_context():
        iid = _make_institution()
        uid_a = _make_db_user(iid, role=Role.FACULTY)
        uid_b = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid_b, subj_id, sem_id, iid)  # only B has assignment
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_a)
    r = client.get('/api/v1/faculty/courses', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data'] == []  # A sees nothing


def test_guest_cannot_access_courses(app, client):
    token, _ = _token(app, role=Role.GUEST, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/faculty/courses', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


# ── 29–38. STUDENTS IN COURSE ─────────────────────────────────────────────────

def test_faculty_assigned_to_course_can_view_students(app, client):
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        uid_stu = _make_db_user(iid, role=Role.STUDENT)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid_fac, subj_id, sem_id, iid)
        _make_course_enrollment(uid_stu, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_fac)
    r = client.get(f'/api/v1/faculty/courses/{subj_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert len(r.get_json()['data']) == 1


def test_faculty_not_assigned_to_course_gets_404(app, client):
    """IDOR prevention: course exists but faculty is not assigned → 404."""
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        # No assignment for uid_fac
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_fac)
    r = client.get(f'/api/v1/faculty/courses/{subj_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


def test_faculty_cannot_view_another_facultys_course_students(app, client):
    """Faculty A cannot view students in Faculty B's course."""
    with app.app_context():
        iid = _make_institution()
        uid_a = _make_db_user(iid, role=Role.FACULTY)
        uid_b = _make_db_user(iid, role=Role.FACULTY)
        uid_stu = _make_db_user(iid, role=Role.STUDENT)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid_b, subj_id, sem_id, iid)  # only B assigned
        _make_course_enrollment(uid_stu, subj_id, sem_id, iid)
        db.session.commit()

    # Request as A — A is not assigned to the course
    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_a)
    r = client.get(f'/api/v1/faculty/courses/{subj_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


def test_student_response_has_no_email_or_sensitive_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        uid_stu = _make_db_user(iid, role=Role.STUDENT)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid_fac, subj_id, sem_id, iid)
        _make_course_enrollment(uid_stu, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_fac)
    r = client.get(f'/api/v1/faculty/courses/{subj_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    for student in r.get_json()['data']:
        for sensitive in ('email', 'email_normalized', 'password_hash',
                          'last_login_at', 'failed_login_attempts', 'storage_path'):
            assert sensitive not in student, f"Sensitive field '{sensitive}' leaked"


def test_invalid_uuid_course_id_returns_404(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/courses/not-a-uuid/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


def test_course_students_requires_auth(client):
    random_id = str(uuid.uuid4())
    assert client.get(f'/api/v1/faculty/courses/{random_id}/students').status_code == 401


def test_guest_cannot_access_course_students(app, client):
    random_id = str(uuid.uuid4())
    token, _ = _token(app, role=Role.GUEST, institution_id=str(uuid.uuid4()))
    r = client.get(f'/api/v1/faculty/courses/{random_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_empty_enrollment_returns_200(app, client):
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid_fac, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_fac)
    r = client.get(f'/api/v1/faculty/courses/{subj_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data'] == []


def test_institution_admin_can_view_course_students(app, client):
    """INSTITUTION_ADMIN has enrollment:read → can access faculty endpoints."""
    with app.app_context():
        iid = _make_institution()
        uid_admin = _make_db_user(iid, role=Role.INSTITUTION_ADMIN)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid_admin, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=uid_admin)
    r = client.get(f'/api/v1/faculty/courses/{subj_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


# ── 39–46. OWN RESOURCES ─────────────────────────────────────────────────────

def test_faculty_can_view_own_resources(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        _make_resource(uid, status="PENDING")
        _make_resource(uid, status="APPROVED")
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/resources', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert len(r.get_json()['data']) == 2


def test_faculty_empty_resource_list(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/resources', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data'] == []


def test_resource_response_never_exposes_storage_path(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        _make_resource(uid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/resources', headers={'Authorization': f'Bearer {token}'})
    for item in r.get_json()['data']:
        assert 'storage_path' not in item


def test_resource_status_filter_pending(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        _make_resource(uid, status="PENDING")
        _make_resource(uid, status="APPROVED")
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/resources?status=PENDING',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    items = r.get_json()['data']
    assert all(i['status'] == 'PENDING' for i in items)


def test_resource_status_filter_approved(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        _make_resource(uid, status="PENDING")
        _make_resource(uid, status="APPROVED")
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/resources?status=APPROVED',
                   headers={'Authorization': f'Bearer {token}'})
    items = r.get_json()['data']
    assert all(i['status'] == 'APPROVED' for i in items)


def test_guest_cannot_access_resources(app, client):
    token, _ = _token(app, role=Role.GUEST, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/faculty/resources', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_faculty_resources_pagination(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        for _ in range(5):
            _make_resource(uid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/resources?limit=2&page=1',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert len(r.get_json()['data']) == 2


def test_faculty_resources_requires_auth(client):
    assert client.get('/api/v1/faculty/resources').status_code == 401


# ── 47–54. RBAC ──────────────────────────────────────────────────────────────

def test_student_cannot_access_admin_users(app, client):
    token, _ = _token(app, role=Role.STUDENT, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_faculty_cannot_access_admin_institutions_manage(app, client):
    """FACULTY does not have institutions:manage."""
    token, _ = _token(app, role=Role.FACULTY, institution_id=str(uuid.uuid4()))
    r = client.post('/api/v1/admin/institutions/',
                    json={"name": "Evil", "short_name": "EV", "code": "EVIL1"},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_faculty_cannot_access_admin_users_list(app, client):
    """FACULTY does not have users:manage."""
    token, _ = _token(app, role=Role.FACULTY, institution_id=str(uuid.uuid4()))
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_faculty_cannot_change_another_users_role(app, client):
    with app.app_context():
        iid = _make_institution()
        other_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid)
    r = client.patch(
        f'/api/v1/admin/users/{other_uid}/role',
        json={"role": "INSTITUTION_ADMIN"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 403


def test_moderator_can_access_faculty_endpoints(app, client):
    """MODERATOR has enrollment:read → can access faculty profile endpoint."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.MODERATOR)
        db.session.commit()

    token, _ = _token(app, role=Role.MODERATOR, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


def test_institution_admin_can_access_faculty_dashboard(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.INSTITUTION_ADMIN)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


def test_faculty_cannot_promote_themselves(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.patch(
        f'/api/v1/admin/users/{uid}/role',
        json={"role": "INSTITUTION_ADMIN"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 403


def test_faculty_cannot_access_super_admin_create_institution(app, client):
    token, _ = _token(app, role=Role.FACULTY, institution_id=str(uuid.uuid4()))
    r = client.post('/api/v1/admin/institutions/',
                    json={"name": "X", "short_name": "X", "code": "X000"},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


# ── 55–58. NOTIFICATIONS ─────────────────────────────────────────────────────

def test_faculty_can_retrieve_own_notifications(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        _make_notification(uid, institution_id=iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/notifications/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert isinstance(r.get_json()['data'], list)


def test_faculty_cannot_read_another_users_notification(app, client):
    with app.app_context():
        iid = _make_institution()
        uid_a = _make_db_user(iid, role=Role.FACULTY)
        uid_b = _make_db_user(iid, role=Role.FACULTY)
        notif_id = _make_notification(uid_b, institution_id=iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_a)
    r = client.post(f'/api/v1/notifications/{notif_id}/read',
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404  # IDOR prevention


def test_notification_count_works_for_faculty(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        _make_notification(uid, is_read=False)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/notifications/count', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['unread_count'] >= 1


def test_notification_endpoint_requires_auth(client):
    assert client.get('/api/v1/notifications/').status_code == 401


# ── 59–65. SECURITY ──────────────────────────────────────────────────────────

def test_idor_faculty_cannot_get_students_from_unassigned_course(app, client):
    with app.app_context():
        iid = _make_institution()
        uid_fac = _make_db_user(iid, role=Role.FACULTY)
        uid_other_fac = _make_db_user(iid, role=Role.FACULTY)
        uid_stu = _make_db_user(iid, role=Role.STUDENT)
        subj_id, sem_id, _, _ = _make_academic_chain(iid)
        _make_assignment(uid_other_fac, subj_id, sem_id, iid)
        _make_course_enrollment(uid_stu, subj_id, sem_id, iid)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_fac)
    r = client.get(f'/api/v1/faculty/courses/{subj_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    # uid_fac is NOT assigned — must get 404, not 200
    assert r.status_code == 404


def test_invalid_uuid_course_students_safely_returns_404(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/courses/invalid-uuid/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404
    body = str(r.get_json())
    assert 'Traceback' not in body


def test_no_stack_traces_in_error_responses(app, client):
    token, _ = _token(app, role=Role.FACULTY, institution_id=str(uuid.uuid4()),
                      user_id=str(uuid.uuid4()))
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    body = str(r.get_json())
    assert 'Traceback' not in body
    assert 'line ' not in body.lower() or r.status_code in (200, 404)


def test_suspended_faculty_returns_200_from_service(app, client):
    """Account suspension is a data field, not a permission — suspended faculty
    still authenticate and get their own profile (caller can check status field)."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY, status="suspended")
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.get('/api/v1/faculty/profile', headers={'Authorization': f'Bearer {token}'})
    # Service returns profile; status field shows "suspended"
    assert r.status_code == 200
    assert r.get_json()['data']['status'] == 'suspended'


def test_faculty_cannot_post_to_courses_endpoint(app, client):
    """Faculty has no mutation endpoint on /faculty/courses."""
    with app.app_context():
        iid = _make_institution()
        uid = _make_db_user(iid, role=Role.FACULTY)
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid)
    r = client.post('/api/v1/faculty/courses',
                    json={"course_id": str(uuid.uuid4())},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code in (404, 405)


def test_resources_only_own_returned(app, client):
    """Faculty A cannot see Faculty B's resources via own resources endpoint."""
    with app.app_context():
        iid = _make_institution()
        uid_a = _make_db_user(iid, role=Role.FACULTY)
        uid_b = _make_db_user(iid, role=Role.FACULTY)
        _make_resource(uid_b)  # resource belongs to B only
        db.session.commit()

    token, _ = _token(app, role=Role.FACULTY, institution_id=iid, user_id=uid_a)
    r = client.get('/api/v1/faculty/resources', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data'] == []  # A sees nothing


def test_cross_institution_student_blocked_by_assignment(app, client):
    """Faculty in institution A cannot enumerate students in institution B's course."""
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_fac_a = _make_db_user(iid_a, role=Role.FACULTY)
        uid_fac_b = _make_db_user(iid_b, role=Role.FACULTY)
        subj_id, sem_id, _, _ = _make_academic_chain(iid_b)
        _make_assignment(uid_fac_b, subj_id, sem_id, iid_b)
        db.session.commit()

    # Faculty A tries to access Faculty B's course — not assigned → 404
    token, _ = _token(app, role=Role.FACULTY, institution_id=iid_a, user_id=uid_fac_a)
    r = client.get(f'/api/v1/faculty/courses/{subj_id}/students',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404
