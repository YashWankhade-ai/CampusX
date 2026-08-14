from app.models import ApprovalRequest
from app.extensions import db
from datetime import datetime, timezone

class ApprovalService:
    def get_pending_queue(self, reviewer_id=None):
        query = db.session.query(ApprovalRequest).filter_by(status='pending')
        if reviewer_id:
            query = query.filter_by(reviewer_id=reviewer_id)
        return query.all()

    def review_material(self, request_id, reviewer_id, comments=None):
        req = db.session.query(ApprovalRequest).get(request_id)
        if not req:
            raise ValueError("Request not found")
        req.reviewer_id = reviewer_id
        req.status = 'under_review'
        req.reviewer_comments = comments
        req.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return req

    def approve_material(self, request_id, reviewer_id):
        req = db.session.query(ApprovalRequest).get(request_id)
        if not req:
            raise ValueError("Request not found")
        req.status = 'approved'
        req.reviewer_id = reviewer_id
        req.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return req

    def reject_material(self, request_id, reviewer_id, reason):
        req = db.session.query(ApprovalRequest).get(request_id)
        if not req:
            raise ValueError("Request not found")
        req.status = 'rejected'
        req.reviewer_id = reviewer_id
        req.reviewer_comments = reason
        req.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return req

    def request_changes(self, request_id, reviewer_id, required_changes):
        req = db.session.query(ApprovalRequest).get(request_id)
        if not req:
            raise ValueError("Request not found")
        req.status = 'changes_requested'
        req.reviewer_id = reviewer_id
        req.reviewer_comments = required_changes
        req.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return req
