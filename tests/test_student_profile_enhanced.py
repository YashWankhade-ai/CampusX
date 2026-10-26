"""Tests for Enhanced Student Profile page & API."""
import uuid
import pytest
from app.extensions import db
from app.models.user import User
from app.models.academic import Institution, Department
from app.models.enrollment import CourseEnrollment
from app.models.resource import StudyMaterial, MaterialType
from app.permissions.roles import Role
from app.utils.token import generate_access_token


def _make_institution():
    inst = Institution(
        id=uuid.uuid4(),
        name="Test University of Technology",
        short_name="TUT",
        code=f"TUT-{uuid.uuid4().hex[:4].upper()}",
        city="Pune",
        country="India",
        subscription_tier="enterprise",
        domain_whitelist=["tut.edu"]
    )
    db.session.add(inst)
    db.session.flush()
    return str(inst.id)


def _make_department(iid):
    dept = Department(
        id=uuid.uuid4(),
        name="Artificial Intelligence",
        institution_id=uuid.UUID(iid)
    )
    db.session.add(dept)
    db.session.flush()
    return str(dept.id)


def _make_student(iid, dept_id=None):
    user = User(
        id=uuid.uuid4(),
        institution_id=uuid.UUID(iid),
        email=f"student_{uuid.uuid4().hex[:6]}@tut.edu",
        full_name="Aarav Sharma",
        display_name="Aarav S.",
        password_hash="argon2_hashed_placeholder",
        role=Role.STUDENT,
        status="ACTIVE",
        department_id=uuid.UUID(dept_id) if dept_id else None,
        metadata_json={
            "phone": "+91 98765 43210",
            "location": "Pune, India",
            "bio": "Deep Learning & Robotics enthusiast",
            "student_id": "STU-2026-0042",
            "date_of_birth": "2002-05-14",
            "gender": "Male"
        }
    )
    db.session.add(user)
    db.session.flush()
    return str(user.id)


def _token(app, iid, uid):
    with app.app_context():
        user = db.session.query(User).filter(User.id == uuid.UUID(uid)).first()
        return generate_access_token(user)


def test_student_profile_enhanced_api(app, client):
    with app.app_context():
        iid = _make_institution()
        dept_id = _make_department(iid)
        uid = _make_student(iid, dept_id)

        # Add study material
        mat = StudyMaterial(
            id=uuid.uuid4(),
            title="Unit 3 Neural Networks",
            author_id=uuid.UUID(uid),
            material_type=MaterialType.NOTE,
            status="APPROVED"
        )
        db.session.add(mat)
        db.session.commit()

        token = _token(app, iid, uid)

    res = client.get('/api/v1/student/profile', headers={'Authorization': f'Bearer {token}'})
    assert res.status_code == 200
    data = res.get_json()['data']

    # Header & Personal
    assert data['full_name'] == "Aarav Sharma"
    assert data['display_name'] == "Aarav S."
    assert data['phone'] == "+91 98765 43210"
    assert data['location'] == "Pune, India"
    assert data['bio'] == "Deep Learning & Robotics enthusiast"
    assert data['student_id'] == "STU-2026-0042"
    assert data['date_of_birth'] == "2002-05-14"
    assert data['gender'] == "Male"

    # Academic & Institution
    assert data['department_name'] == "Artificial Intelligence"
    assert data['institution']['name'] == "Test University of Technology"
    assert data['institution']['city'] == "Pune"

    # Activity counts
    assert 'activity' in data
    assert data['activity']['resources_contributed'] >= 1
    assert data['activity']['approved_contributions'] >= 1
    assert isinstance(data['activity']['courses_enrolled'], int)
    assert isinstance(data['activity']['unread_notifications'], int)

    # Security: no passwords or hash leaks
    for leak in ('password', 'password_hash', 'token', 'secret'):
        assert leak not in data


def test_student_profile_update_api(app, client):
    with app.app_context():
        iid = _make_institution()
        uid = _make_student(iid)
        db.session.commit()
        token = _token(app, iid, uid)

    update_payload = {
        "full_name": "Aarav K. Sharma",
        "display_name": "Aarav",
        "phone": "+91 99999 88888",
        "location": "Bengaluru, India",
        "bio": "AI Researcher and Student",
        "timezone": "UTC",
        # Attempt to forge institutional fields
        "role": "SUPER_ADMIN",
        "institution_id": str(uuid.uuid4())
    }

    res = client.put(
        '/api/v1/student/profile',
        headers={'Authorization': f'Bearer {token}'},
        json=update_payload
    )
    assert res.status_code == 200
    data = res.get_json()['data']

    # Updated fields
    assert data['full_name'] == "Aarav K. Sharma"
    assert data['display_name'] == "Aarav"
    assert data['phone'] == "+91 99999 88888"
    assert data['location'] == "Bengaluru, India"
    assert data['bio'] == "AI Researcher and Student"
    assert data['timezone'] == "UTC"

    # Institutional fields are locked and unchanged
    assert data['role'] == Role.STUDENT
    assert data['institution_id'] == iid


def test_student_profile_html_page_rendering(client):
    res = client.get('/student/profile')
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # All required structural elements
    assert "Profile — CampusX" in html or "Student Profile" in html
    assert "profile-avatar" in html
    assert "Personal Information" in html
    assert "Academic Information" in html
    assert "Institution Details" in html or "Institution" in html
    assert "CampusX Activity" in html
    assert "Profile Completion" in html
    assert "Account & Security" in html
    assert "Sign out" in html
    assert "Edit Personal Details" in html or "Edit Details" in html
    assert "/api/v1/student/profile" in html
    assert "read-only" in html.lower() or "Contact your institution" in html

    # Verify no fake submit button (per cycle 2 requirements)
    assert 'type="submit"' not in html or "Save" not in html
