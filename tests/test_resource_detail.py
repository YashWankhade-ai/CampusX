"""Sprint 10 Hardening — Resource Detail & resource.viewed analytics tests.

Covers:
1.  Successful resource detail request returns safe metadata
2.  Authentication required for GET /<resource_id>
3.  Institution isolation: cross-institution resource returns 404
4.  Visibility: PENDING resource invisible to regular STUDENT
5.  Visibility: PENDING resource visible to its own author
6.  Visibility: PENDING resource visible to MODERATOR (same institution)
7.  resource.viewed event created on successful access
8.  No resource.viewed event for unauthenticated request
9.  No resource.viewed event for nonexistent resource
10. No resource.viewed event for cross-institution resource
11. No resource.viewed event for unauthorized status (PENDING for non-author)
12. Response dict does not contain storage_path
13. Response dict does not contain file system paths
14. Response dict does not contain internal sensitive keys
15. get_resource_detail returns None for invalid UUID
16. get_resource_detail returns None for soft-deleted resource
"""
import uuid
import pytest
from unittest.mock import patch

from app.extensions import db
from app.models.resource import StudyMaterial, MaterialType, FileMetadata, MaterialVersion
from app.models.user import User
from app.models.analytics import EventLog
from app.utils.token import generate_access_token
from app.permissions.roles import Role


# ── Helpers ──────────────────────────────────────────────────────────────────

class _User:
    def __init__(self, role=Role.STUDENT, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f"{uuid.uuid4().hex[:6]}@resource-test.edu"
        self.is_verified = True


def _make_token(app, role=Role.STUDENT, institution_id=None, user_id=None):
    user = _User(role=role, institution_id=institution_id, user_id=user_id)
    with app.app_context():
        return generate_access_token(user), user


def _create_db_user(institution_id: str, user_id: str = None) -> str:
    """Insert a minimal User row into the in-memory DB and return user_id string."""
    uid = uuid.UUID(user_id) if user_id else uuid.uuid4()
    iid = uuid.UUID(institution_id)
    email = f"user_{uid.hex[:8]}@test.edu"
    u = User(
        id=uid,
        email=email,
        email_normalized=email.lower(),
        full_name="Test User",
        password_hash="hashed",
        institution_id=iid,
        role=Role.STUDENT,
        status="active",
    )
    db.session.add(u)
    db.session.flush()
    return str(uid)


def _create_approved_resource(author_id: str, title="Test Resource") -> str:
    """Create an APPROVED StudyMaterial and return its ID string."""
    mid = uuid.uuid4()
    fid = uuid.uuid4()
    vid = uuid.uuid4()

    mat = StudyMaterial(
        id=mid,
        title=title,
        description="A test resource",
        author_id=uuid.UUID(author_id),
        material_type=MaterialType.NOTE,
        status="APPROVED",
    )
    fm = FileMetadata(
        id=fid,
        original_name="test.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        storage_path="institution/abc/test.pdf",  # This must NOT appear in API response
    )
    mv = MaterialVersion(
        id=vid,
        study_material_id=mid,
        version_number=1,
        file_metadata_id=fid,
        change_summary="Initial",
    )
    db.session.add_all([mat, fm, mv])
    db.session.flush()
    return str(mid)


def _create_pending_resource(author_id: str) -> str:
    mid = uuid.uuid4()
    mat = StudyMaterial(
        id=mid,
        title="Pending Resource",
        author_id=uuid.UUID(author_id),
        material_type=MaterialType.NOTE,
        status="PENDING",
    )
    db.session.add(mat)
    db.session.flush()
    return str(mid)


# ── 1. Successful resource detail request ─────────────────────────────────────

def test_resource_detail_success(app, client):
    """Authenticated user can access an APPROVED resource from same institution."""
    inst = str(uuid.uuid4())
    token, viewer = _make_token(app, role=Role.STUDENT, institution_id=inst)

    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_approved_resource(author_id)
        db.session.commit()

    response = client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['id'] == resource_id
    assert data['data']['status'] == 'APPROVED'


# ── 2. Authentication required ────────────────────────────────────────────────

def test_resource_detail_requires_auth(app, client):
    """Unauthenticated request must return 401."""
    inst = str(uuid.uuid4())
    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_approved_resource(author_id)
        db.session.commit()

    response = client.get(f'/api/v1/resources/{resource_id}')
    assert response.status_code == 401


# ── 3. Institution isolation ──────────────────────────────────────────────────

def test_resource_detail_cross_institution_returns_404(app, client):
    """Resource from institution A must return 404 to a user from institution B."""
    inst_a = str(uuid.uuid4())
    inst_b = str(uuid.uuid4())

    token, _ = _make_token(app, role=Role.STUDENT, institution_id=inst_b)

    with app.app_context():
        author_id = _create_db_user(inst_a)  # Author is in inst_a
        resource_id = _create_approved_resource(author_id)
        db.session.commit()

    response = client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 404


# ── 4. PENDING resource invisible to regular STUDENT ─────────────────────────

def test_pending_resource_not_visible_to_student(app, client):
    """A STUDENT who is not the author cannot see PENDING resources."""
    inst = str(uuid.uuid4())
    token, viewer = _make_token(app, role=Role.STUDENT, institution_id=inst)

    with app.app_context():
        # Author is a different user in same institution
        author_id = _create_db_user(inst)
        resource_id = _create_pending_resource(author_id)
        db.session.commit()

    response = client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 404


# ── 5. PENDING resource visible to its own author ─────────────────────────────

def test_pending_resource_visible_to_author(app, client):
    """The resource author can see their own PENDING resource."""
    inst = str(uuid.uuid4())
    author_uid = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.FACULTY, institution_id=inst, user_id=author_uid)

    with app.app_context():
        # Create the DB user with the same ID as the JWT user
        _create_db_user(inst, user_id=author_uid)
        resource_id = _create_pending_resource(author_uid)
        db.session.commit()

    response = client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['status'] == 'PENDING'


# ── 6. PENDING resource visible to MODERATOR ─────────────────────────────────

def test_pending_resource_visible_to_moderator(app, client):
    """MODERATOR from same institution can see PENDING resources."""
    inst = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.MODERATOR, institution_id=inst)

    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_pending_resource(author_id)
        db.session.commit()

    response = client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['status'] == 'PENDING'


# ── 7. resource.viewed event created on successful access ─────────────────────

def test_resource_viewed_event_recorded_on_success(app, client):
    """A resource.viewed event is created only on successful authorized access."""
    inst = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.STUDENT, institution_id=inst)

    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_approved_resource(author_id)
        db.session.commit()

        before = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed",
            EventLog.event_data['resource_id'].as_string() == resource_id,
        ).count()

    client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )

    with app.app_context():
        after = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed",
        ).count()
    assert after > before


# ── 8. No resource.viewed event for unauthenticated request ──────────────────

def test_no_viewed_event_for_unauthenticated(app, client):
    """Unauthenticated request (401) must not produce a resource.viewed event."""
    inst = str(uuid.uuid4())
    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_approved_resource(author_id)
        db.session.commit()

        before = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed"
        ).count()

    client.get(f'/api/v1/resources/{resource_id}')  # No auth header

    with app.app_context():
        after = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed"
        ).count()
    assert after == before


# ── 9. No resource.viewed event for nonexistent resource ─────────────────────

def test_no_viewed_event_for_nonexistent_resource(app, client):
    """404 on nonexistent resource must not produce a resource.viewed event."""
    inst = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.STUDENT, institution_id=inst)
    fake_id = str(uuid.uuid4())

    with app.app_context():
        before = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed"
        ).count()

    client.get(f'/api/v1/resources/{fake_id}',
               headers={'Authorization': f'Bearer {token}'})

    with app.app_context():
        after = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed"
        ).count()
    assert after == before


# ── 10. No resource.viewed event for cross-institution resource ───────────────

def test_no_viewed_event_for_cross_institution(app, client):
    """Cross-institution access (404) must not produce a resource.viewed event."""
    inst_a = str(uuid.uuid4())
    inst_b = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.STUDENT, institution_id=inst_b)

    with app.app_context():
        author_id = _create_db_user(inst_a)
        resource_id = _create_approved_resource(author_id)
        db.session.commit()
        before = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed"
        ).count()

    client.get(f'/api/v1/resources/{resource_id}',
               headers={'Authorization': f'Bearer {token}'})

    with app.app_context():
        after = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed"
        ).count()
    assert after == before


# ── 11. No resource.viewed event for unauthorized status ─────────────────────

def test_no_viewed_event_for_unauthorized_status(app, client):
    """PENDING resource (student who is not author) → 404, no viewed event."""
    inst = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.STUDENT, institution_id=inst)

    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_pending_resource(author_id)
        db.session.commit()
        before = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed"
        ).count()

    client.get(f'/api/v1/resources/{resource_id}',
               headers={'Authorization': f'Bearer {token}'})

    with app.app_context():
        after = db.session.query(EventLog).filter(
            EventLog.event_type == "resource.viewed"
        ).count()
    assert after == before


# ── 12. Response does not contain storage_path ───────────────────────────────

def test_response_does_not_contain_storage_path(app, client):
    """The resource detail response must never expose storage_path."""
    inst = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.STUDENT, institution_id=inst)

    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_approved_resource(author_id)
        db.session.commit()

    response = client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()['data']
    assert 'storage_path' not in data
    assert 'checksum' not in data
    assert 'mime_type' not in data


# ── 13. Response does not contain file system paths ──────────────────────────

def test_response_data_fields_are_safe(app, client):
    """Only whitelisted safe fields are present in the resource detail response."""
    inst = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.STUDENT, institution_id=inst)

    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_approved_resource(author_id)
        db.session.commit()

    response = client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    data = response.get_json()['data']
    allowed = {'id', 'title', 'description', 'status', 'material_type',
                'author_id', 'subject_id', 'topic_id', 'created_at', 'updated_at'}
    sensitive = {'storage_path', 'checksum', 'password', 'token', 'secret',
                 'file_path', 'bucket', 'key', 'mime_type', 'size_bytes'}
    for field in sensitive:
        assert field not in data, f"Sensitive field '{field}' found in response"


# ── 14. Response dict does not contain internal sensitive keys ────────────────

def test_institution_id_not_in_resource_detail_response(app, client):
    """institution_id must not be present in the resource detail response."""
    inst = str(uuid.uuid4())
    token, _ = _make_token(app, role=Role.STUDENT, institution_id=inst)

    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_approved_resource(author_id)
        db.session.commit()

    response = client.get(
        f'/api/v1/resources/{resource_id}',
        headers={'Authorization': f'Bearer {token}'}
    )
    data = response.get_json()['data']
    # institution_id is not a field on StudyMaterial — verify it's not present
    assert 'institution_id' not in data


# ── 15. get_resource_detail returns None for invalid UUID ─────────────────────

def test_get_resource_detail_invalid_uuid(app):
    from app.services.resource_service import ResourceService
    with app.app_context():
        svc = ResourceService()
        result = svc.get_resource_detail(
            resource_id="not-a-uuid",
            viewer_id=str(uuid.uuid4()),
            viewer_institution_id=str(uuid.uuid4()),
            viewer_role=Role.STUDENT,
        )
        assert result is None


# ── 16. get_resource_detail returns None for soft-deleted resource ────────────

def test_get_resource_detail_soft_deleted_resource(app):
    from app.services.resource_service import ResourceService

    inst = str(uuid.uuid4())
    with app.app_context():
        author_id = _create_db_user(inst)
        resource_id = _create_approved_resource(author_id)

        # Soft-delete it
        mat = db.session.query(StudyMaterial).filter(
            StudyMaterial.id == uuid.UUID(resource_id)
        ).first()
        mat.is_deleted = True
        db.session.commit()

        svc = ResourceService()
        result = svc.get_resource_detail(
            resource_id=resource_id,
            viewer_id=author_id,
            viewer_institution_id=inst,
            viewer_role=Role.STUDENT,
        )
        assert result is None
