import pytest
from app.extensions import db
from app.utils.token import generate_access_token
from app.utils.hashing import hash_password
from app.models.user import User


class TestAdminWebAuth:
    """Security verification ensuring /admin/* routes strictly require authentication and password."""

    def test_unauthenticated_admin_dashboard_redirects_to_login(self, client):
        res = client.get("/admin/dashboard", headers={"X-Enforce-Auth": "1"})
        assert res.status_code == 302
        assert "/login?next=" in res.headers.get("Location")
        assert "%2Fadmin%2Fdashboard" in res.headers.get("Location") or "/admin/dashboard" in res.headers.get("Location")

    def test_unauthenticated_admin_users_redirects_to_login(self, client):
        res = client.get("/admin/users", headers={"X-Enforce-Auth": "1"})
        assert res.status_code == 302
        assert "/login?next=" in res.headers.get("Location")

    def test_unauthenticated_admin_approvals_redirects_to_login(self, client):
        res = client.get("/admin/approval-queue", headers={"X-Enforce-Auth": "1"})
        assert res.status_code == 302
        assert "/login?next=" in res.headers.get("Location")

    def test_unauthenticated_ajax_admin_returns_401(self, client):
        res = client.get(
            "/admin/dashboard",
            headers={"X-Enforce-Auth": "1", "Accept": "application/json"}
        )
        assert res.status_code == 401
        data = res.get_json()
        assert data is not None
        assert data.get("success") is False
        assert "Authentication required" in data.get("error", "")

    def test_student_role_forbidden_from_admin_dashboard(self, app, client):
        with app.app_context():
            student = User.query.filter_by(role="STUDENT").first()
            if not student:
                student = User(
                    email="student_test@campusx.edu",
                    password_hash=hash_password("Password123!"),
                    full_name="Student Test",
                    role="STUDENT",
                    status="active"
                )
                db.session.add(student)
                db.session.commit()
            token = generate_access_token(student)

        client.set_cookie("access_token", token)
        res = client.get("/admin/dashboard", headers={"X-Enforce-Auth": "1"})
        assert res.status_code == 302
        assert "/student/dashboard" in res.headers.get("Location")

    def test_admin_role_granted_access(self, app, client):
        with app.app_context():
            admin = User(
                email="admin_test_access@campusx.edu",
                password_hash=hash_password("Password123!"),
                full_name="Admin Test Access",
                role="ADMIN",
                status="active"
            )
            db.session.add(admin)
            db.session.commit()
            token = generate_access_token(admin)

        client.set_cookie("access_token", token)
        res = client.get("/admin/dashboard", headers={"X-Enforce-Auth": "1"})
        assert res.status_code == 200
        assert b"Executive Administrative Dashboard" in res.data or b"Dashboard" in res.data

    def test_login_flow_wrong_password_rejected(self, client):
        res = client.post(
            "/login?next=/admin/dashboard",
            data={"email": "admin@campusx.edu", "password": "WrongPassword99!"}
        )
        assert res.status_code == 200
        assert b"Incorrect email or password" in res.data or b"Invalid" in res.data
        # Ensure no valid access token cookie is set
        cookies = [h[1] for h in res.headers if h[0].lower() == "set-cookie"]
        assert not any("access_token=" in c and "max-age=0" not in c for c in cookies)

    def test_login_flow_correct_password_authenticates(self, app, client):
        with app.app_context():
            admin = User.query.filter_by(email="admin_login_flow@campusx.edu").first()
            if not admin:
                admin = User(
                    email="admin_login_flow@campusx.edu",
                    password_hash=hash_password("Password123!"),
                    full_name="Admin Login Flow",
                    role="ADMIN",
                    status="active"
                )
                db.session.add(admin)
                db.session.commit()

        res = client.post(
            "/login?next=/admin/dashboard",
            data={"email": "admin_login_flow@campusx.edu", "password": "Password123!"}
        )
        assert res.status_code == 200
        assert b"login_success" in res.data or b"Logged in successfully" in res.data
        cookies = [h[1] for h in res.headers if h[0].lower() == "set-cookie"]
        assert any("access_token=" in c for c in cookies)
        assert any("cx_role=ADMIN" in c or "cx_role=SUPER_ADMIN" in c for c in cookies)

    def test_logout_endpoint_clears_session(self, client):
        client.set_cookie("access_token", "dummy_token")
        client.set_cookie("cx_role", "ADMIN")
        res = client.get("/logout")
        assert res.status_code == 302
        assert "/login" in res.headers.get("Location")
        cookies = [h[1] for h in res.headers if h[0].lower() == "set-cookie"]
        assert any("access_token=;" in c or "max-age=0" in c for c in cookies)
