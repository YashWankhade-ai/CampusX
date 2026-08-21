"""Approval workflow models.

ApprovalWorkflow / ApprovalStep / ApprovalRequest — generic workflow engine (legacy).
ApprovalAction — audit trail for resource approval decisions (Sprint 8).
"""
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Text, Integer
from app.models.base import BaseModel


class ApprovalWorkflow(BaseModel):
    __tablename__ = "approval_workflows"
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApprovalStep(BaseModel):
    __tablename__ = "approval_steps"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_workflows.id"))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    step_order: Mapped[int] = mapped_column(Integer, default=1)


class ApprovalRequest(BaseModel):
    __tablename__ = "approval_requests"
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_workflows.id"))
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    target_resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ApprovalAction(BaseModel):
    """Audit record for resource approval/rejection decisions.

    Each row records one decision (approve, reject, changes_requested)
    by a reviewer against a specific StudyMaterial resource.
    """
    __tablename__ = "approval_actions"
    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
