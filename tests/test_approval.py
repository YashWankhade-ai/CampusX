"""Sprint 8 — Approval workflow tests.

Tests the complete approval lifecycle including:
- Authorization (unauthenticated, unauthorized, authorized)
- Self-approval prevention
- Cross-institution isolation
- Valid/invalid status transitions
- Audit trail (ApprovalAction records)
- Rejection reason storage
- Duplicate approval handling
"""
import pytest
import uuid
from datetime import datetime, timezone
from flask import json
from app.utils.token import generate_access_token
from app.permissions.roles import Role
from app.models.resource import StudyMaterial, MaterialType
from app.models.approval import ApprovalAction
from app.extensions import db


# ── Helpers ──

class MockApprovalUser:
    """Mock user for token generation in approval tests."""
    def __init__(self, role=Role.MODERATOR, institution_id=None, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.role = role
        self.institution_id = institution_id or str(uuid.uuid4())
        self.email = f'{role.lower()}@test.edu'


def make_token(app, role=Role.MODERATOR, institution_id=None, user_id=None):
    """Generate a JWT for a mock user."""
    with app.app_context():
        user = MockApprovalUser(role=role, institution_id=institution_id, user_id=user_id)
        return generate_access_token(user), user


def create_pending_resource(app, author_id, institution_id=None):
    """Insert a PENDING StudyMaterial into the test DB.
    
    Also creates a User row for the author so that institution
    isolation checks (JOIN on users) work correctly.
    """
    from app.models.user import User

    with app.app_context():
        # Create author user if not exists
        author_uuid = uuid.UUID(author_id) if isinstance(author_id, str) else author_id
        existing = db.session.query(User).filter_by(id=author_uuid).first()
        if not existing:
            author = User(
                id=author_uuid,
                email=f'author-{str(author_uuid)[:8]}@test.edu',
                email_normalized=f'author-{str(author_uuid)[:8]}@test.edu',
                full_name='Test Author',
                password_hash='$argon2id$v=19$m=65536,t=3,p=4$AAAA$AAAA',
                role=Role.FACULTY,
                status='ACTIVE',
            )
            if institution_id:
                author.institution_id = uuid.UUID(institution_id) if isinstance(institution_id, str) else institution_id
            db.session.add(author)
            db.session.flush()

        resource = StudyMaterial(
            id=uuid.uuid4(),
            title='Test Resource for Approval',
            description='A test document pending review',
            author_id=author_uuid,
            material_type=MaterialType.NOTE,
            status='PENDING',
        )
        db.session.add(resource)
        db.session.commit()
        return str(resource.id), str(author_uuid)


# ── 1. Unauthenticated user cannot access approval endpoints ──

def test_unauthenticated_cannot_list_pending(client):
    response = client.get('/api/v1/approvals/pending')
    assert response.status_code == 401


def test_unauthenticated_cannot_approve(client):
    response = client.post(f'/api/v1/approvals/{uuid.uuid4()}/approve')
    assert response.status_code == 401


def test_unauthenticated_cannot_reject(client):
    response = client.post(f'/api/v1/approvals/{uuid.uuid4()}/reject')
    assert response.status_code == 401


# ── 2. Unauthorized role cannot approve ──

def test_student_cannot_approve(app, client):
    token, user = make_token(app, role=Role.STUDENT)
    response = client.post(
        f'/api/v1/approvals/{uuid.uuid4()}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 403


def test_faculty_cannot_approve(app, client):
    """FACULTY has resources:write but NOT resources:approve."""
    token, user = make_token(app, role=Role.FACULTY)
    response = client.post(
        f'/api/v1/approvals/{uuid.uuid4()}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 403


# ── 3. Authorized reviewer can approve ──

def test_moderator_can_approve(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    # Reviewer is a MODERATOR at the same institution (different user)
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_id)
    
    response = client.post(
        f'/api/v1/approvals/{resource_id}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['status'] == 'APPROVED'
    assert data['data']['decision'] == 'approved'


# ── 4. Authorized reviewer can reject ──

def test_moderator_can_reject_with_reason(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_id)
    
    response = client.post(
        f'/api/v1/approvals/{resource_id}/reject',
        headers={'Authorization': f'Bearer {token}'},
        json={'reason': 'Poor quality content'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['status'] == 'REJECTED'
    assert data['data']['reason'] == 'Poor quality content'


# ── 5. Self-approval is rejected ──

def test_self_approval_rejected(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    # Token user IS the author
    token, _ = make_token(app, role=Role.MODERATOR, institution_id=institution_id, user_id=author_id)
    
    response = client.post(
        f'/api/v1/approvals/{resource_id}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 400
    data = response.get_json()
    assert 'own upload' in data['error']['message'].lower()


# ── 6. Cross-institution approval rejected ──

def test_cross_institution_approval_rejected(app, client):
    institution_a = str(uuid.uuid4())
    institution_b = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    # Resource belongs to institution A
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_a)
    
    # Reviewer is from institution B
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_b)
    
    response = client.post(
        f'/api/v1/approvals/{resource_id}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    # Should return 404 (not 403) to avoid revealing resource existence
    assert response.status_code == 404


# ── 7. Invalid resource ID ──

def test_invalid_resource_id(app, client):
    token, _ = make_token(app, role=Role.MODERATOR)
    
    response = client.post(
        '/api/v1/approvals/not-a-uuid/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code in (400, 404)


def test_nonexistent_resource_id(app, client):
    token, _ = make_token(app, role=Role.MODERATOR)
    
    response = client.post(
        f'/api/v1/approvals/{uuid.uuid4()}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 404


# ── 8. Invalid status transition ──

def test_cannot_approve_already_approved(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    # First approval
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_id)
    response1 = client.post(
        f'/api/v1/approvals/{resource_id}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response1.status_code == 200
    
    # Second approval attempt (duplicate)
    response2 = client.post(
        f'/api/v1/approvals/{resource_id}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response2.status_code == 400
    data = response2.get_json()
    assert 'already approved' in data['error']['message'].lower() or 'cannot' in data['error']['message'].lower()


# ── 9. Rejection stores reason and reviewer ──

def test_rejection_stores_audit_record(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_id)
    
    client.post(
        f'/api/v1/approvals/{resource_id}/reject',
        headers={'Authorization': f'Bearer {token}'},
        json={'reason': 'Insufficient citations'}
    )
    
    # Check the audit trail
    with app.app_context():
        actions = db.session.query(ApprovalAction).filter(
            ApprovalAction.resource_id == uuid.UUID(resource_id)
        ).all()
        assert len(actions) == 1
        assert actions[0].action == 'rejected'
        assert actions[0].comments == 'Insufficient citations'
        assert str(actions[0].approver_id) == reviewer.id


# ── 10. Approval creates audit record with timestamp ──

def test_approval_creates_audit_record(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_id)
    
    client.post(
        f'/api/v1/approvals/{resource_id}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    
    with app.app_context():
        actions = db.session.query(ApprovalAction).filter(
            ApprovalAction.resource_id == uuid.UUID(resource_id)
        ).all()
        assert len(actions) == 1
        assert actions[0].action == 'approved'
        assert actions[0].created_at is not None


# ── 11. Upload now creates PENDING status ──

def test_upload_creates_pending_resource(app, client):
    """Verify Sprint 7 upload now sets status=PENDING (not APPROVED)."""
    import io
    from app.utils.token import generate_access_token
    
    class UploadUser:
        def __init__(self):
            self.id = str(uuid.uuid4())
            self.role = Role.FACULTY
            self.institution_id = str(uuid.uuid4())
            self.email = 'uploader@test.edu'
    
    with app.app_context():
        user = UploadUser()
        token = generate_access_token(user)
    
    data = {
        'file': (io.BytesIO(b'%PDF-1.4 test'), 'lecture.pdf', 'application/pdf'),
        'title': 'Test PENDING Upload',
    }
    response = client.post(
        '/api/v1/resources/upload',
        data=data,
        content_type='multipart/form-data',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 201
    result = response.get_json()['data']
    assert result['status'] == 'PENDING'


# ── 12. Pending list filtered by institution ──

def test_pending_list_institution_scoped(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    # Reviewer from same institution sees it
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_id)
    response = client.get(
        '/api/v1/approvals/pending',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['meta']['total'] >= 1


# ── 13. Pending list from different institution sees nothing ──

def test_pending_list_cross_institution_empty(app, client):
    institution_a = str(uuid.uuid4())
    institution_b = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    create_pending_resource(app, author_id=author_id, institution_id=institution_a)
    
    # Reviewer from institution B should not see institution A resources
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_b)
    response = client.get(
        '/api/v1/approvals/pending',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    # Should be 0 for this institution
    assert data['meta']['total'] == 0


# ── 14. Institution admin can also approve ──

def test_institution_admin_can_approve(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    token, reviewer = make_token(app, role=Role.INSTITUTION_ADMIN, institution_id=institution_id)
    
    response = client.post(
        f'/api/v1/approvals/{resource_id}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200


# ── 15. Approval history endpoint ──

def test_approval_history(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    token, reviewer = make_token(app, role=Role.MODERATOR, institution_id=institution_id)
    
    # Approve it
    client.post(
        f'/api/v1/approvals/{resource_id}/approve',
        headers={'Authorization': f'Bearer {token}'}
    )
    
    # Fetch history
    response = client.get(
        f'/api/v1/approvals/{resource_id}/history',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['data']) == 1
    assert data['data'][0]['action'] == 'approved'


# ── 16. Self-rejection also prevented ──

def test_self_rejection_prevented(app, client):
    institution_id = str(uuid.uuid4())
    author_id = str(uuid.uuid4())
    
    resource_id, _ = create_pending_resource(app, author_id=author_id, institution_id=institution_id)
    
    token, _ = make_token(app, role=Role.MODERATOR, institution_id=institution_id, user_id=author_id)
    
    response = client.post(
        f'/api/v1/approvals/{resource_id}/reject',
        headers={'Authorization': f'Bearer {token}'},
        json={'reason': 'Self-sabotage'}
    )
    assert response.status_code == 400
    assert 'own upload' in response.get_json()['error']['message'].lower()
