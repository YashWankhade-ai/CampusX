"""Approval workflow service.

Operates directly on StudyMaterial status with ApprovalAction audit trail.
Enforces institution isolation, self-approval prevention, and valid status transitions.
"""
import uuid
from datetime import datetime, timezone
from app.models.resource import StudyMaterial
from app.models.approval import ApprovalAction, ApprovalRequest
from app.extensions import db


# Valid status transitions
VALID_TRANSITIONS = {
    'PENDING': {'APPROVED', 'REJECTED', 'CHANGES_REQUESTED'},
    'CHANGES_REQUESTED': {'PENDING', 'APPROVED', 'REJECTED'},
    'REJECTED': {'PENDING'},  # Allow re-submission
}

# Statuses that block further approval/rejection
TERMINAL_STATUSES = {'APPROVED'}


class ApprovalService:
    """Manages the resource approval workflow.

    Core rules:
    - Only resources with status in VALID_TRANSITIONS keys can be acted upon
    - Reviewer must have resources:approve permission (enforced at route level)
    - Reviewer must belong to the same institution as the resource author
    - Reviewer cannot approve their own upload
    - All decisions are recorded as ApprovalAction audit entries
    - StudyMaterial.status is updated atomically with the audit record
    """

    def get_pending_queue(self, institution_id=None):
        """Return resources pending review, optionally filtered by institution."""
        query = db.session.query(StudyMaterial).filter(
            StudyMaterial.status.in_(['PENDING', 'CHANGES_REQUESTED']),
            StudyMaterial.is_deleted == False
        )
        # Institution scoping — never return resources from other institutions
        # StudyMaterial doesn't have institution_id directly, so we join via author
        if institution_id:
            from app.models.user import User
            inst_uuid = uuid.UUID(institution_id) if isinstance(institution_id, str) else institution_id
            query = query.join(User, StudyMaterial.author_id == User.id).filter(
                User.institution_id == inst_uuid
            )
        return query.order_by(StudyMaterial.created_at.asc()).all()

    def get_resource_for_review(self, resource_id, reviewer_institution_id):
        """Fetch a resource for review, enforcing institution isolation.

        Returns (resource, error_message) tuple.
        """
        try:
            resource_uuid = uuid.UUID(resource_id)
        except (ValueError, TypeError):
            return None, "Invalid resource ID format"

        resource = db.session.query(StudyMaterial).filter(
            StudyMaterial.id == resource_uuid,
            StudyMaterial.is_deleted == False
        ).first()

        if not resource:
            return None, "Resource not found"

        # Institution isolation: check author's institution matches reviewer's
        from app.models.user import User
        author = db.session.query(User).filter(User.id == resource.author_id).first()
        if not author:
            return None, "Resource author not found"

        if str(author.institution_id) != str(reviewer_institution_id):
            # Fail closed — don't reveal the resource exists to cross-institution users
            return None, "Resource not found"

        return resource, None

    def approve_material(self, resource_id, reviewer_id, reviewer_institution_id):
        """Approve a pending resource.

        Args:
            resource_id: UUID string of the StudyMaterial
            reviewer_id: UUID string of the reviewing user (from JWT)
            reviewer_institution_id: Institution UUID string (from JWT)

        Returns:
            dict with approval result

        Raises:
            ValueError: On validation/authorization failure
        """
        resource, error = self.get_resource_for_review(resource_id, reviewer_institution_id)
        if error:
            raise ValueError(error)

        # Prevent self-approval
        if str(resource.author_id) == str(reviewer_id):
            raise ValueError("Cannot approve your own upload")

        # Validate status transition
        if resource.status not in VALID_TRANSITIONS:
            raise ValueError(f"Resource with status '{resource.status}' cannot be approved")
        if 'APPROVED' not in VALID_TRANSITIONS.get(resource.status, set()):
            raise ValueError(f"Cannot transition from '{resource.status}' to 'APPROVED'")

        # Check for duplicate — already approved
        if resource.status in TERMINAL_STATUSES:
            raise ValueError("Resource is already approved")

        # Atomic: update resource + create audit record
        try:
            resource.status = 'APPROVED'
            resource.updated_at = datetime.now(timezone.utc)

            action = ApprovalAction(
                id=uuid.uuid4(),
                resource_id=resource.id,  # Links audit to the StudyMaterial
                approver_id=uuid.UUID(reviewer_id),
                action='approved',
                comments=None
            )
            db.session.add(action)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise ValueError("Failed to process approval")

        return {
            "resource_id": str(resource.id),
            "title": resource.title,
            "status": resource.status,
            "reviewer_id": reviewer_id,
            "decision": "approved",
            "decided_at": datetime.now(timezone.utc).isoformat()
        }

    def reject_material(self, resource_id, reviewer_id, reviewer_institution_id, reason=''):
        """Reject a pending resource.

        Args:
            resource_id: UUID string of the StudyMaterial
            reviewer_id: UUID string of the reviewing user (from JWT)
            reviewer_institution_id: Institution UUID string (from JWT)
            reason: Rejection reason text

        Returns:
            dict with rejection result

        Raises:
            ValueError: On validation/authorization failure
        """
        resource, error = self.get_resource_for_review(resource_id, reviewer_institution_id)
        if error:
            raise ValueError(error)

        # Prevent self-rejection
        if str(resource.author_id) == str(reviewer_id):
            raise ValueError("Cannot reject your own upload")

        # Validate status transition
        if resource.status not in VALID_TRANSITIONS:
            raise ValueError(f"Resource with status '{resource.status}' cannot be rejected")
        if 'REJECTED' not in VALID_TRANSITIONS.get(resource.status, set()):
            raise ValueError(f"Cannot transition from '{resource.status}' to 'REJECTED'")

        # Atomic: update resource + create audit record
        try:
            resource.status = 'REJECTED'
            resource.updated_at = datetime.now(timezone.utc)

            action = ApprovalAction(
                id=uuid.uuid4(),
                resource_id=resource.id,
                approver_id=uuid.UUID(reviewer_id),
                action='rejected',
                comments=reason or None
            )
            db.session.add(action)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise ValueError("Failed to process rejection")

        return {
            "resource_id": str(resource.id),
            "title": resource.title,
            "status": resource.status,
            "reviewer_id": reviewer_id,
            "decision": "rejected",
            "reason": reason,
            "decided_at": datetime.now(timezone.utc).isoformat()
        }

    def request_changes(self, resource_id, reviewer_id, reviewer_institution_id, feedback=''):
        """Request changes on a pending resource.

        Args:
            resource_id: UUID string of the StudyMaterial
            reviewer_id: UUID string of the reviewing user (from JWT)
            reviewer_institution_id: Institution UUID string (from JWT)
            feedback: Required changes description

        Returns:
            dict with result

        Raises:
            ValueError: On validation/authorization failure
        """
        resource, error = self.get_resource_for_review(resource_id, reviewer_institution_id)
        if error:
            raise ValueError(error)

        # Prevent self-review
        if str(resource.author_id) == str(reviewer_id):
            raise ValueError("Cannot request changes on your own upload")

        # Validate status transition
        if resource.status not in VALID_TRANSITIONS:
            raise ValueError(f"Resource with status '{resource.status}' cannot be changed")
        if 'CHANGES_REQUESTED' not in VALID_TRANSITIONS.get(resource.status, set()):
            raise ValueError(f"Cannot transition from '{resource.status}' to 'CHANGES_REQUESTED'")

        try:
            resource.status = 'CHANGES_REQUESTED'
            resource.updated_at = datetime.now(timezone.utc)

            action = ApprovalAction(
                id=uuid.uuid4(),
                resource_id=resource.id,
                approver_id=uuid.UUID(reviewer_id),
                action='changes_requested',
                comments=feedback or None
            )
            db.session.add(action)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise ValueError("Failed to process change request")

        return {
            "resource_id": str(resource.id),
            "title": resource.title,
            "status": resource.status,
            "reviewer_id": reviewer_id,
            "decision": "changes_requested",
            "feedback": feedback,
            "decided_at": datetime.now(timezone.utc).isoformat()
        }

    def get_approval_history(self, resource_id):
        """Get the audit trail for a resource's approval decisions."""
        try:
            resource_uuid = uuid.UUID(resource_id)
        except (ValueError, TypeError):
            return []

        actions = db.session.query(ApprovalAction).filter(
            ApprovalAction.resource_id == resource_uuid
        ).order_by(ApprovalAction.created_at.asc()).all()

        return [a.to_dict() for a in actions]
