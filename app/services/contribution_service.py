"""Contribution Service — Sprint 10.

Records contribution events when users upload or have resources approved.
Aggregation uses DB-level queries (no Python loops over large row sets).

Contribution actions (architecture-supported):
    resource_uploaded  — user uploaded a new resource
    resource_approved  — user's resource was approved by a reviewer

Points/gamification/badges are not implemented (not in specification).
"""
import uuid
import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import func

from app.models.contribution import UserContribution
from app.extensions import db

logger = logging.getLogger(__name__)

VALID_ACTIONS = frozenset({"resource_uploaded", "resource_approved"})


def record_contribution(
    user_id: str,
    action: str,
    resource_id: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> None:
    """Record a contribution event. Never raises — contribution failure must not break primary ops."""
    if action not in VALID_ACTIONS:
        logger.debug("Dropping unknown contribution action: %s", action)
        return
    try:
        contrib = UserContribution(
            user_id=uuid.UUID(user_id),
            action=action,
            resource_id=uuid.UUID(resource_id) if resource_id else None,
            institution_id=uuid.UUID(institution_id) if institution_id else None,
        )
        db.session.add(contrib)
        db.session.flush()  # Caller commits
    except Exception:
        logger.warning("Failed to record contribution: %s", action, exc_info=True)


def get_user_contribution_counts(user_id: str) -> Dict[str, int]:
    """Return contribution counts per action for a user. DB-aggregated."""
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return {}

    rows = db.session.query(
        UserContribution.action,
        func.count(UserContribution.id).label("cnt"),
    ).filter(
        UserContribution.user_id == uid,
        UserContribution.is_deleted == False,
    ).group_by(UserContribution.action).all()

    return {row.action: row.cnt for row in rows}


def get_institution_contribution_summary(institution_id: str) -> Dict[str, int]:
    """Return contribution counts per action for an institution. DB-aggregated."""
    try:
        iid = uuid.UUID(institution_id)
    except (ValueError, TypeError):
        return {}

    rows = db.session.query(
        UserContribution.action,
        func.count(UserContribution.id).label("cnt"),
    ).filter(
        UserContribution.institution_id == iid,
        UserContribution.is_deleted == False,
    ).group_by(UserContribution.action).all()

    return {row.action: row.cnt for row in rows}


class ContributionService:
    """Thin wrapper — delegates to module-level functions for testability."""

    def record(
        self,
        user_id: str,
        action: str,
        resource_id: Optional[str] = None,
        institution_id: Optional[str] = None,
    ) -> None:
        record_contribution(user_id, action, resource_id, institution_id)

    def get_user_contributions(self, user_id: str) -> Dict[str, int]:
        return get_user_contribution_counts(user_id)

    def get_institution_contributions(self, institution_id: str) -> Dict[str, int]:
        return get_institution_contribution_summary(institution_id)

    # ── Legacy stubs referenced by the old contributions blueprint ──

    def get_user_score(self, user_id: str) -> int:
        """Legacy: returns total contribution count as a proxy score."""
        counts = get_user_contribution_counts(str(user_id))
        return sum(counts.values())

    def get_user_badges(self, user_id: str) -> List[Dict[str, Any]]:
        """Legacy stub — badges not implemented in Sprint 10."""
        return []

    def get_leaderboard(self, timeframe: str = "all_time", limit: int = 10) -> List[Dict[str, Any]]:
        """Return top contributors by total contribution count."""
        rows = db.session.query(
            UserContribution.user_id,
            func.count(UserContribution.id).label("total"),
        ).filter(
            UserContribution.is_deleted == False,
        ).group_by(UserContribution.user_id).order_by(
            func.count(UserContribution.id).desc()
        ).limit(limit).all()

        return [{"user_id": str(row.user_id), "contributions": row.total} for row in rows]

    # ── Old method names that broken code called ──

    def calculate_points(self, user_id) -> int:
        return self.get_user_score(str(user_id))

    def add_contribution(self, user_id, action, points=0, resource_id=None):
        """Legacy — maps old call to new record()."""
        record_contribution(str(user_id), action, str(resource_id) if resource_id else None)
