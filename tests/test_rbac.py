import pytest
import uuid
from flask import json
from app.permissions.roles import Role, ROLE_HIERARCHY
from app.permissions.checkers import has_permission, is_same_institution
from app.models.user import User
from app.config import Config, TestingConfig
from app.utils.token import generate_access_token

class MockUser:
    def __init__(self, id, role):
        self.id = id
        self.role = role
        self.institution_id = str(uuid.uuid4())
        self.email = 'test@example.com'

def get_test_token(app, user_id, role="STUDENT"):
    with app.app_context():
        user = MockUser(user_id, role)
        return generate_access_token(user)

def test_unauthenticated_request_rejected(client):
    response = client.get('/api/v1/users/me')
    assert response.status_code == 401
    data = json.loads(response.data)
    assert not data['success']

def test_authenticated_request_allowed(app, client):
    user_id = str(uuid.uuid4())
    token = get_test_token(app, user_id)
    # Use /api/v1/auth/me which reads from request.user (no DB lookup needed)
    response = client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True


def test_student_blocked_from_approvals(app, client):
    token = get_test_token(app, str(uuid.uuid4()), role=Role.STUDENT)
    response = client.get('/api/v1/approvals/pending', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 403

def test_moderator_allowed_approvals(app, client):
    token = get_test_token(app, str(uuid.uuid4()), role=Role.MODERATOR)
    # The endpoint tries to fetch from db but won't 403
    response = client.get('/api/v1/approvals/pending', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code != 403

def test_student_missing_resources_write_permission():
    assert has_permission(Role.STUDENT, 'resources:write') is False

def test_faculty_has_resources_write_permission():
    assert has_permission(Role.FACULTY, 'resources:write') is True

def test_super_admin_has_all_permissions():
    from app.permissions.permissions import ROLE_PERMISSIONS
    all_perms = set()
    for perms in ROLE_PERMISSIONS.values():
        for p in perms:
            all_perms.add(p)
    
    for perm in all_perms:
        assert has_permission(Role.SUPER_ADMIN, perm) is True

def test_role_hierarchy_ordering():
    assert ROLE_HIERARCHY == [Role.GUEST, Role.STUDENT, Role.FACULTY, Role.MODERATOR, Role.INSTITUTION_ADMIN, Role.SUPER_ADMIN]

def test_missing_role_treated_as_guest():
    user = User(role=None)
    assert has_permission(user, 'resources:write') is False
    assert has_permission(user, 'users:manage') is False

def test_fail_closed_invalid_token(client):
    response = client.get('/api/v1/users/me', headers={'Authorization': 'Bearer invalid.token.string'})
    assert response.status_code == 401

def test_cross_institution_rejected():
    inst1 = uuid.uuid4()
    inst2 = uuid.uuid4()
    assert is_same_institution(inst1, inst2) is False

def test_same_institution_allowed():
    inst1 = uuid.uuid4()
    assert is_same_institution(inst1, inst1) is True

def test_guest_only_search_permission():
    assert has_permission(Role.GUEST, 'search:use') is True
    assert has_permission(Role.GUEST, 'resources:read') is False

def test_institution_admin_has_user_manage():
    assert has_permission(Role.INSTITUTION_ADMIN, 'users:manage') is True

def test_jwt_secret_min_length():
    # check that testing config has >= 32
    assert len(TestingConfig.SECRET_KEY) >= 32
