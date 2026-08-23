"""Contribution models — Sprint 10.

UserContribution: audit record of a meaningful contribution action.
Contribution types: resource_uploaded, resource_approved.

Architecture note:
  The specification does not define a points/gamification system.
  ContributionType and Leaderboard are retained as model scaffolds
  (they exist in migration context) but are not wired up.
  Badge is a scaffold — no awarding logic in Sprint 10.
"""
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Integer, Index
from app.models.base import BaseModel


class ContributionType(BaseModel):
    """Reference table for contribution action types."""
    __tablename__ = "contribution_types"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # points field retained for potential future use — not used in Sprint 10
    points: Mapped[int] = mapped_column(Integer, default=0)


class UserContribution(BaseModel):
    """Records a contribution action by a user.

    action values (exhaustive):
        resource_uploaded — user uploaded a resource
        resource_approved — user's resource was approved

    institution_id is denormalised for efficient tenant-scoped queries.
    """
    __tablename__ = "user_contributions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("study_materials.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_user_contributions_user_id", "user_id"),
        Index("ix_user_contributions_action", "action"),
        Index("ix_user_contributions_institution_id", "institution_id"),
    )


# Alias for any existing imports
Contribution = UserContribution


class Badge(BaseModel):
    """Scaffold — badge definition table. Awarding not implemented in Sprint 10."""
    __tablename__ = "badges"
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Leaderboard(BaseModel):
    """Scaffold — pre-aggregated leaderboard. Not populated in Sprint 10."""
    __tablename__ = "leaderboards"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    total_points: Mapped[int] = mapped_column(Integer, default=0, index=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
