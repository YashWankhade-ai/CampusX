"""Sprint 12 — Admin & Institution Management tests.

Tests:
1.  Unauthenticated requests rejected (all admin endpoints → 401)
2.  STUDENT cannot access admin endpoints → 403
3.  FACULTY cannot access admin endpoints → 403
4.  MODERATOR can read users (users:read) but not manage → 403 on manage
5.  INSTITUTION_ADMIN can list their institution's users
6.  INSTITUTION_ADMIN cannot list users from another institution (IDOR)
7.  INSTITUTION_ADMIN can get user detail in same institution
8.  INSTITUTION_ADMIN cannot get user from another institution (IDOR → 404)
9.  SUPER_ADMIN can list all users across institutions
10. INSTITUTION_ADMIN can activate/deactivate user in same institution
11. INSTITUTION_ADMIN cannot activate user in another institution (IDOR → 404)
12. Self-deactivation rejected → 400
13. Invalid status string rejected → 400
14. INSTITUTION_ADMIN can change role to FACULTY/STUDENT/MODERATOR
15. INSTITUTION_ADMIN cannot promote to INSTITUTION_ADMIN (escalation → 403)
16. INSTITUTION_ADMIN cannot promote to SUPER_ADMIN (escalation → 403)
17. Self-promotion rejected → 400/403
18. SUPER_ADMIN cannot promote to SUPER_ADMIN via API → 400
19. SUPER_ADMIN can promote to INSTITUTION_ADMIN
20. Cannot modify a user with equal or higher privilege level
21. SUPER_ADMIN can list all institutions
22. INSTITUTION_ADMIN can list only their institution
23. INSTITUTION_ADMIN can view their own institution detail
24. INSTITUTION_ADMIN cannot view another institution's detail → 404
25. SUPER_ADMIN can create institution
26. INSTITUTION_ADMIN cannot create institution → 403/400
27. SUPER_ADMIN can update any institution
28. INSTITUTION_ADMIN can update their own institution
29. INSTITUTION_ADMIN cannot update another institution → 403/404
30. Duplicate institution code rejected → 400
31. Response does not contain password_hash, otp, or token fields
32. Users in institution A not visible to INSTITUTION_ADMIN of institution B
33. Status filter works (list users with status=active)
34. Pagination works (page 1 of 2, institution-scoped)
35. Pagination limit capped at 100
"""
import uuid
import pytest

from app.extensions import db
from app.models.user import User
from app.models.academic import Institution
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeUser:
    def __init__(self, role=Role.STUDENT, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"u_{uuid.uuid4().hex[:6]}@admin-test.edu"


def _token(app, role=Role.STUDENT, institution_id=None, user_id=None):
    u = _FakeUser(role=role, institution_id=institution_id, user_id=user_id)
    with app.app_context():
        return generate_access_token(u), u


def _make_institution(name=None, code=None):
    iid = uuid.uuid4()
    inst = Institution(
        id=iid,
        name=name or f"Test University {iid.hex[:4]}",
        short_name="TU",
        code=code or f"TU{iid.hex[:4]}",
        domain_whitelist=[],
        settings_json={},
    )
    db.session.add(inst)
    db.session.flush()
    return str(inst.id)  # Return string ID immediately to avoid DetachedInstanceError


def _make_db_user(institution_id, role=Role.STUDENT, status="active", user_id=None):
    uid = uuid.UUID(user_id) if user_id else uuid.uuid4()
    iid = uuid.UUID(institution_id) if isinstance(institution_id, str) else institution_id
    email = f"u_{uid.hex[:8]}@admin.edu"
    u = User(
        id=uid,
        email=email,
        email_normalized=email.lower(),
        full_name="Admin Test User",
        password_hash="hashed",
        institution_id=iid,
        role=role,
        status=status,
    )
    db.session.add(u)
    db.session.flush()
    return str(uid)


# ── 1. Unauthenticated requests rejected ─────────────────────────────────────

def test_admin_users_list_requires_auth(client):
    assert client.get('/api/v1/admin/users/').status_code == 401


def test_admin_user_detail_requires_auth(client):
    assert client.get(f'/api/v1/admin/users/{uuid.uuid4()}').status_code == 401


def test_admin_institutions_list_requires_auth(client):
    assert client.get('/api/v1/admin/institutions/').status_code == 401


def test_admin_create_institution_requires_auth(client):
    assert client.post('/api/v1/admin/institutions/').status_code == 401


# ── 2–4. Low-privilege roles rejected ────────────────────────────────────────

def test_student_cannot_list_users(app, client):
    inst = str(uuid.uuid4())
    token, _ = _token(app, role=Role.STUDENT, institution_id=inst)
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_faculty_cannot_list_users(app, client):
    inst = str(uuid.uuid4())
    token, _ = _token(app, role=Role.FACULTY, institution_id=inst)
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_moderator_cannot_manage_users(app, client):
    """MODERATOR has users:read but not users:manage → 403 on manage endpoints."""
    inst = str(uuid.uuid4())
    uid_target = str(uuid.uuid4())
    token, _ = _token(app, role=Role.MODERATOR, institution_id=inst)
    r = client.patch(
        f'/api/v1/admin/users/{uid_target}/status',
        json={"status": "inactive"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 403


# ── 5. INSTITUTION_ADMIN can list their institution's users ───────────────────

def test_institution_admin_lists_own_institution_users(app, client):
    with app.app_context():
        iid = _make_institution()
        admin_uid = _make_db_user(iid, role=Role.INSTITUTION_ADMIN)
        _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=admin_uid)
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['meta']['total'] >= 1
    for u in data['data']:
        assert u['institution_id'] == iid


# ── 6. INSTITUTION_ADMIN cannot list users from another institution (IDOR) ────

def test_institution_admin_cannot_see_other_institution_users(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        _make_db_user(iid_a, role=Role.STUDENT)  # user in A
        db.session.commit()

    # Admin of institution B — should see 0 users
    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_b)
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['meta']['total'] == 0


# ── 7. INSTITUTION_ADMIN can get user detail in same institution ──────────────

def test_institution_admin_gets_user_in_same_institution(app, client):
    with app.app_context():
        iid = _make_institution()
        target_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get(f'/api/v1/admin/users/{target_uid}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['id'] == target_uid


# ── 8. INSTITUTION_ADMIN cannot get user from another institution ─────────────

def test_institution_admin_cannot_get_user_from_other_institution(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        target_uid = _make_db_user(iid_a, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_b)
    r = client.get(f'/api/v1/admin/users/{target_uid}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


# ── 9. SUPER_ADMIN can list all users ────────────────────────────────────────

def test_super_admin_lists_all_users(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        uid_a = _make_db_user(iid_a)
        uid_b = _make_db_user(iid_b)
        db.session.commit()

    token, _ = _token(app, role=Role.SUPER_ADMIN)
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    all_ids = {u['id'] for u in r.get_json()['data']}
    assert uid_a in all_ids
    assert uid_b in all_ids


# ── 10. INSTITUTION_ADMIN can activate/deactivate user in same institution ────

def test_institution_admin_can_deactivate_user_in_same_institution(app, client):
    with app.app_context():
        iid = _make_institution()
        admin_uid = str(uuid.uuid4())
        target_uid = _make_db_user(iid, role=Role.STUDENT, status="active")
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=admin_uid)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/status',
        json={"status": "inactive"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 200
    assert r.get_json()['data']['status'] == 'inactive'


# ── 11. INSTITUTION_ADMIN cannot modify user in another institution ────────────

def test_institution_admin_cannot_deactivate_user_in_other_institution(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        target_uid = _make_db_user(iid_a, role=Role.STUDENT, status="active")
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_b)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/status',
        json={"status": "inactive"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 404


# ── 12. Self-deactivation rejected ────────────────────────────────────────────

def test_admin_cannot_deactivate_self(app, client):
    with app.app_context():
        iid = _make_institution()
        admin_uid = _make_db_user(iid, role=Role.INSTITUTION_ADMIN)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=admin_uid)
    r = client.patch(
        f'/api/v1/admin/users/{admin_uid}/status',
        json={"status": "inactive"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 400


# ── 13. Invalid status string rejected ────────────────────────────────────────

def test_invalid_status_rejected(app, client):
    with app.app_context():
        iid = _make_institution()
        target_uid = _make_db_user(iid)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/status',
        json={"status": "banned"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 400


# ── 14. INSTITUTION_ADMIN can change role to FACULTY/STUDENT/MODERATOR ────────

def test_institution_admin_can_assign_faculty_role(app, client):
    with app.app_context():
        iid = _make_institution()
        admin_uid = str(uuid.uuid4())
        target_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=admin_uid)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/role',
        json={"role": "FACULTY"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 200
    assert r.get_json()['data']['role'] == 'FACULTY'


# ── 15. INSTITUTION_ADMIN cannot promote to INSTITUTION_ADMIN ─────────────────

def test_institution_admin_cannot_promote_to_institution_admin(app, client):
    with app.app_context():
        iid = _make_institution()
        admin_uid = str(uuid.uuid4())
        target_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=admin_uid)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/role',
        json={"role": "INSTITUTION_ADMIN"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code in (400, 403)


# ── 16. INSTITUTION_ADMIN cannot promote to SUPER_ADMIN ──────────────────────

def test_institution_admin_cannot_promote_to_super_admin(app, client):
    with app.app_context():
        iid = _make_institution()
        admin_uid = str(uuid.uuid4())
        target_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=admin_uid)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/role',
        json={"role": "SUPER_ADMIN"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code in (400, 403)


# ── 17. Self-promotion rejected ───────────────────────────────────────────────

def test_self_promotion_rejected(app, client):
    with app.app_context():
        iid = _make_institution()
        admin_uid = _make_db_user(iid, role=Role.INSTITUTION_ADMIN)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=admin_uid)
    r = client.patch(
        f'/api/v1/admin/users/{admin_uid}/role',
        json={"role": "SUPER_ADMIN"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code in (400, 403)


# ── 18. SUPER_ADMIN cannot promote to SUPER_ADMIN via API ─────────────────────

def test_super_admin_cannot_promote_to_super_admin_via_api(app, client):
    with app.app_context():
        iid = _make_institution()
        target_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    super_uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.SUPER_ADMIN, institution_id=iid, user_id=super_uid)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/role',
        json={"role": "SUPER_ADMIN"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code in (400, 403)


# ── 19. SUPER_ADMIN can promote to INSTITUTION_ADMIN ─────────────────────────

def test_super_admin_can_promote_to_institution_admin(app, client):
    with app.app_context():
        iid = _make_institution()
        target_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    super_uid = str(uuid.uuid4())
    token, _ = _token(app, role=Role.SUPER_ADMIN, institution_id=iid, user_id=super_uid)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/role',
        json={"role": "INSTITUTION_ADMIN"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 200
    assert r.get_json()['data']['role'] == 'INSTITUTION_ADMIN'


# ── 20. Cannot modify user with equal or higher privilege ─────────────────────

def test_cannot_modify_user_with_higher_privilege(app, client):
    """INSTITUTION_ADMIN cannot demote another INSTITUTION_ADMIN."""
    with app.app_context():
        iid = _make_institution()
        admin_uid = str(uuid.uuid4())
        target_uid = _make_db_user(iid, role=Role.INSTITUTION_ADMIN)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid, user_id=admin_uid)
    r = client.patch(
        f'/api/v1/admin/users/{target_uid}/role',
        json={"role": "STUDENT"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code in (400, 403)


# ── 21. SUPER_ADMIN can list all institutions ─────────────────────────────────

def test_super_admin_lists_all_institutions(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        db.session.commit()

    token, _ = _token(app, role=Role.SUPER_ADMIN)
    r = client.get('/api/v1/admin/institutions/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    all_ids = {i['id'] for i in r.get_json()['data']}
    assert iid_a in all_ids
    assert iid_b in all_ids


# ── 22. INSTITUTION_ADMIN can only list their own institution ─────────────────

def test_institution_admin_only_sees_own_institution(app, client):
    with app.app_context():
        iid_a = _make_institution()
        _make_institution()  # inst_b — should not appear
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_a)
    r = client.get('/api/v1/admin/institutions/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['meta']['total'] == 1
    assert data['data'][0]['id'] == iid_a


# ── 23. INSTITUTION_ADMIN can view their own institution ──────────────────────

def test_institution_admin_can_view_own_institution(app, client):
    with app.app_context():
        iid = _make_institution()
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get(f'/api/v1/admin/institutions/{iid}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['data']['id'] == iid


# ── 24. INSTITUTION_ADMIN cannot view another institution ─────────────────────

def test_institution_admin_cannot_view_other_institution(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_b)
    r = client.get(f'/api/v1/admin/institutions/{iid_a}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 404


# ── 25. SUPER_ADMIN can create institution ────────────────────────────────────

def test_super_admin_can_create_institution(app, client):
    token, _ = _token(app, role=Role.SUPER_ADMIN)
    unique_code = f"NEW{uuid.uuid4().hex[:4].upper()}"
    r = client.post(
        '/api/v1/admin/institutions/',
        json={"name": "New University", "short_name": "NU", "code": unique_code},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 201
    assert r.get_json()['data']['code'] == unique_code


# ── 26. INSTITUTION_ADMIN cannot create institution ───────────────────────────

def test_institution_admin_cannot_create_institution(app, client):
    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=str(uuid.uuid4()))
    r = client.post(
        '/api/v1/admin/institutions/',
        json={"name": "Fake University", "short_name": "FU", "code": "FAKE001"},
        headers={'Authorization': f'Bearer {token}'}
    )
    # Service enforces SUPER_ADMIN-only at create time
    assert r.status_code in (400, 403)


# ── 27. SUPER_ADMIN can update any institution ────────────────────────────────

def test_super_admin_can_update_any_institution(app, client):
    with app.app_context():
        iid = _make_institution()
        db.session.commit()

    token, _ = _token(app, role=Role.SUPER_ADMIN)
    r = client.patch(
        f'/api/v1/admin/institutions/{iid}',
        json={"city": "Mumbai"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 200
    assert r.get_json()['data']['city'] == 'Mumbai'


# ── 28. INSTITUTION_ADMIN can update their own institution ────────────────────

def test_institution_admin_can_update_own_institution(app, client):
    with app.app_context():
        iid = _make_institution()
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.patch(
        f'/api/v1/admin/institutions/{iid}',
        json={"city": "Delhi"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 200
    assert r.get_json()['data']['city'] == 'Delhi'


# ── 29. INSTITUTION_ADMIN cannot update another institution ───────────────────

def test_institution_admin_cannot_update_other_institution(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_b)
    r = client.patch(
        f'/api/v1/admin/institutions/{iid_a}',
        json={"city": "Injected"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code in (403, 404)


# ── 30. Duplicate institution code rejected ────────────────────────────────────

def test_duplicate_institution_code_rejected(app, client):
    with app.app_context():
        _make_institution(code="DUPCODE")
        db.session.commit()

    token, _ = _token(app, role=Role.SUPER_ADMIN)
    r = client.post(
        '/api/v1/admin/institutions/',
        json={"name": "Another Uni", "short_name": "AU", "code": "DUPCODE"},
        headers={'Authorization': f'Bearer {token}'}
    )
    assert r.status_code == 400


# ── 31. Response does not contain sensitive fields ─────────────────────────────

def test_user_response_excludes_sensitive_fields(app, client):
    with app.app_context():
        iid = _make_institution()
        target_uid = _make_db_user(iid, role=Role.STUDENT)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get(f'/api/v1/admin/users/{target_uid}', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    user_data = r.get_json()['data']
    for sensitive in ('password_hash', 'otp', 'token', 'secret', 'code_hash'):
        assert sensitive not in user_data, f"Sensitive field '{sensitive}' found in response"


# ── 32. Cross-institution isolation ───────────────────────────────────────────

def test_users_in_institution_a_not_visible_to_admin_of_b(app, client):
    with app.app_context():
        iid_a = _make_institution()
        iid_b = _make_institution()
        for _ in range(3):
            _make_db_user(iid_a)
        _make_db_user(iid_b)
        db.session.commit()

    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid_b)
    r = client.get('/api/v1/admin/users/', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    # Admin of B should see exactly 1 user (the B user we just created)
    assert r.get_json()['meta']['total'] == 1


# ── 33. Status filter ─────────────────────────────────────────────────────────

def test_status_filter_active_users(app, client):
    with app.app_context():
        iid = _make_institution()
        _make_db_user(iid, status="active")
        _make_db_user(iid, status="inactive")
        db.session.commit()

    # Use INSTITUTION_ADMIN scoped to this institution so filter is clean
    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get('/api/v1/admin/users/?status=active', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()['data']
    assert len(data) >= 1
    for u in data:
        assert u['status'] == 'active'


# ── 34. Pagination works (institution-scoped) ─────────────────────────────────

def test_pagination_page_1_of_2(app, client):
    with app.app_context():
        iid = _make_institution()
        for _ in range(5):
            _make_db_user(iid)
        db.session.commit()

    # Use INSTITUTION_ADMIN so results are scoped exactly to this institution
    token, _ = _token(app, role=Role.INSTITUTION_ADMIN, institution_id=iid)
    r = client.get('/api/v1/admin/users/?page=1&limit=3', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()
    assert len(data['data']) == 3
    assert data['meta']['total'] == 5
    assert data['meta']['limit'] == 3


# ── 35. Pagination limit capped ───────────────────────────────────────────────

def test_pagination_limit_capped(app, client):
    token, _ = _token(app, role=Role.SUPER_ADMIN)
    r = client.get('/api/v1/admin/users/?limit=9999', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['meta']['limit'] <= 100
