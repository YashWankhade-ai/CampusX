"""Tests for Department & Branch-tagged ID creation, user management, and enrollment."""
import uuid
import pytest
from app.extensions import db
from app.models.user import User
from app.models.academic import Institution, Department, Degree, Program, Subject, Semester, AcademicSession
from app.models.enrollment import StudentEnrollment, CourseEnrollment, AcademicYear
from app.permissions.roles import Role
from app.utils.academic_utils import get_branch_code, generate_institutional_id


def _setup_test_academic(app):
    """Helper to ensure institution, department, and program exist in testing db."""
    with app.app_context():
        inst = Institution.query.first()
        if not inst:
            inst = Institution(id=uuid.uuid4(), name="CampusX University", short_name="CXU", code="CXU-01")
            db.session.add(inst)
            db.session.flush()

        dept_ai = Department.query.filter_by(name="Department of Artificial Intelligence").first()
        if not dept_ai:
            dept_ai = Department(id=uuid.uuid4(), name="Department of Artificial Intelligence", institution_id=inst.id)
            db.session.add(dept_ai)

        dept_cse = Department.query.filter_by(name="Computer Science & Engineering").first()
        if not dept_cse:
            dept_cse = Department(id=uuid.uuid4(), name="Computer Science & Engineering", institution_id=inst.id)
            db.session.add(dept_cse)
        db.session.flush()

        deg = Degree.query.first()
        if not deg:
            deg = Degree(id=uuid.uuid4(), name="Bachelor of Technology", level="undergraduate")
            db.session.add(deg)
            db.session.flush()

        prog = Program.query.first()
        if not prog:
            prog = Program(id=uuid.uuid4(), name="B.Tech Computer Science", department_id=dept_cse.id, degree_id=deg.id)
            db.session.add(prog)
            db.session.flush()

        sess = AcademicSession.query.first()
        if not sess:
            sess = AcademicSession(id=uuid.uuid4(), name="2026-2027", start_year=2026, end_year=2027)
            db.session.add(sess)
            db.session.flush()

        sem = Semester.query.first()
        if not sem:
            sem = Semester(id=uuid.uuid4(), name="Semester 1", academic_session_id=sess.id, number=1)
            db.session.add(sem)
            db.session.flush()

        subj = Subject.query.first()
        if not subj:
            subj = Subject(id=uuid.uuid4(), name="Data Structures", code="CS201", program_id=prog.id, semester_id=sem.id)
            db.session.add(subj)

        ay = AcademicYear.query.first()
        if not ay:
            ay = AcademicYear(id=uuid.uuid4(), label="2026-2027", start_year=2026, end_year=2027)
            db.session.add(ay)

        inst_id = str(inst.id)
        dept_ai_id = str(dept_ai.id)
        dept_cse_id = str(dept_cse.id)
        db.session.commit()
        return inst_id, dept_ai_id, dept_cse_id


def test_branch_code_derivation():
    """Verify branch codes are accurately derived from department names."""
    assert get_branch_code("Computer Science & Engineering") == "CSE"
    assert get_branch_code("Department of Computer Science & Engineering") == "CSE"
    assert get_branch_code("Department of Artificial Intelligence") == "AI"
    assert get_branch_code("Department of Information Technology") == "IT"
    assert get_branch_code("Department of Electronics & Communication") == "ECE"
    assert get_branch_code("Department of Electrical Engineering") == "EE"
    assert get_branch_code("Department of Mechanical Engineering") == "ME"
    assert get_branch_code("Department of Civil Engineering") == "CE"
    assert get_branch_code("Department of Data Science") == "DS"
    assert get_branch_code("Department of Aerospace Engineering") == "AERO"
    assert get_branch_code("Department of Chemical Engineering") == "CHEM"


def test_institutional_id_generation():
    """Verify generated IDs contain the department/branch code."""
    stu_id = generate_institutional_id("STUDENT", "CSE", 1, 2026)
    assert stu_id == "STU-CSE-2026-001"
    assert "CSE" in stu_id

    fac_id = generate_institutional_id("FACULTY", "AI", 5, 2026)
    assert fac_id == "FAC-AI-2026-005"
    assert "AI" in fac_id

    adm_id = generate_institutional_id("ADMIN", "IT", 2, 2026)
    assert adm_id == "ADM-IT-2026-002"
    assert "IT" in adm_id


def test_admin_create_student_with_department(app, client):
    """Test creating a student via /admin/users/create with department selection."""
    inst_id, dept_ai_id, dept_cse_id = _setup_test_academic(app)

    form_data = {
        "full_name": "Kavya Patel",
        "email": f"kavya.patel.ai_{uuid.uuid4().hex[:4]}@campusx.edu",
        "role": "STUDENT",
        "department_id": dept_ai_id,
        "password": "Password123!"
    }

    res = client.post("/admin/users/create", data=form_data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        created_user = User.query.filter_by(email=form_data["email"]).first()
        assert created_user is not None
        assert str(created_user.department_id) == dept_ai_id
        assert created_user.role == "STUDENT"

        meta = created_user.metadata_json or {}
        assert "institutional_id" in meta
        inst_id = meta["institutional_id"]
        branch_code = meta.get("branch_code")
        assert branch_code == "AI"
        assert "AI" in inst_id
        assert inst_id.startswith("STU-")

        # Verify enrollment
        se = StudentEnrollment.query.filter_by(user_id=created_user.id).first()
        assert se is not None
        assert se.status == "active"


def test_admin_create_faculty_with_department(app, client):
    """Test creating a faculty member with department and branch-tagged ID."""
    inst_id, dept_ai_id, dept_cse_id = _setup_test_academic(app)

    form_data = {
        "full_name": "Dr. Vikram Seth",
        "email": f"vikram.seth.cse_{uuid.uuid4().hex[:4]}@campusx.edu",
        "role": "FACULTY",
        "department_id": dept_cse_id,
        "institutional_id": "FAC-CSE-2026-042",
        "password": "Password123!"
    }

    res = client.post("/admin/users/create", data=form_data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email=form_data["email"]).first()
        assert user is not None
        assert user.role == "FACULTY"
        assert str(user.department_id) == dept_cse_id
        assert user.metadata_json.get("institutional_id") == "FAC-CSE-2026-042"
        assert "CSE" in user.metadata_json.get("institutional_id")


def test_admin_users_page_displays_branch_ids(app, client):
    """Verify /admin/users renders institutional IDs and branch tags."""
    _setup_test_academic(app)
    res = client.get("/admin/users")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "User &amp; Institutional ID" in html or "User & Institutional ID" in html
    assert "Create New Student / Faculty ID" in html
    assert "Academic Branch" in html


def test_admin_user_approval_flow(app, client):
    """Test approving a pending user transitions status to active."""
    inst_id, dept_ai_id, _ = _setup_test_academic(app)

    # Create pending student
    form_data = {
        "full_name": "Pending Student",
        "email": f"pending.stu_{uuid.uuid4().hex[:4]}@campusx.edu",
        "role": "STUDENT",
        "department_id": dept_ai_id,
        "password": "Password123!",
        "status": "pending_approval"
    }
    res = client.post("/admin/users/create", data=form_data, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email=form_data["email"]).first()
        assert user is not None
        assert user.status == "pending_approval"
        user_id = str(user.id)

    # Now approve user via POST /admin/users/<user_id>/approve
    res_approve = client.post(f"/admin/users/{user_id}/approve", headers={"Accept": "application/json"})
    assert res_approve.status_code == 200
    json_data = res_approve.get_json()
    assert json_data["success"] is True
    assert json_data["status"] == "active"

    with app.app_context():
        updated_user = db.session.get(User, uuid.UUID(user_id))
        assert updated_user.status == "active"


def test_admin_user_deletion_flow(app, client):
    """Test deleting a user cascades and removes their record."""
    inst_id, dept_ai_id, _ = _setup_test_academic(app)

    form_data = {
        "full_name": "Temporary Faculty",
        "email": f"temp.fac_{uuid.uuid4().hex[:4]}@campusx.edu",
        "role": "FACULTY",
        "department_id": dept_ai_id,
        "password": "Password123!"
    }
    client.post("/admin/users/create", data=form_data, follow_redirects=True)

    with app.app_context():
        user = User.query.filter_by(email=form_data["email"]).first()
        assert user is not None
        user_id = str(user.id)

    # Delete the user via POST /admin/users/<user_id>/delete
    res_del = client.post(f"/admin/users/{user_id}/delete", headers={"Accept": "application/json"})
    assert res_del.status_code == 200
    assert res_del.get_json()["success"] is True

    with app.app_context():
        deleted_user = db.session.get(User, uuid.UUID(user_id))
        assert deleted_user is None


def test_admin_protection_from_deletion(app, client):
    """Ensure primary administrators cannot be deleted."""
    with app.app_context():
        admin = User.query.filter_by(email="admin@campusx.edu").first()
        if not admin:
            admin = User(
                id=uuid.uuid4(),
                email="admin@campusx.edu",
                full_name="CampusX Super Admin",
                password_hash="testhash",
                role="SUPER_ADMIN",
                status="active"
            )
            db.session.add(admin)
            db.session.commit()
        admin_id = str(admin.id)

    res_del = client.post(f"/admin/users/{admin_id}/delete", headers={"Accept": "application/json"})
    assert res_del.status_code == 403
    assert "Primary administrator accounts cannot be deleted" in res_del.get_json()["error"]


