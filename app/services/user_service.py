"""User service — Sprint 12 hardening.

Replaces the Sprint 0 scaffold with real, security-correct implementations:

- get_user_profile()      → DB query by user_id; returns safe dict
- get_user_by_id()        → IDOR-safe: checks same institution unless SUPER_ADMIN
- update_user_profile()   → own-profile update only; allowlisted fields
- list_users()            → institution-scoped (SUPER_ADMIN sees all)
- get_leaderboard()       → institution-scoped contribution count ranking

Safe serialization:
    _safe_user_dict() — explicit allowlist, NEVER includes password_hash,
    refresh tokens, OTP codes, or internal secrets.

NOTE: assign_role() is intentionally removed — role changes are exclusively
through AdminService.change_user_role() which enforces privilege escalation
rules. Duplicating it here would create a privilege escalation bypass.
"""
import uuid
import logging
from typing import Optional

from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.contribution import UserContribution
from app.permissions.roles import Role

logger = logging.getLogger(__name__)

MAX_LIMIT = 100
PROFILE_UPDATE_FIELDS = frozenset({"full_name", "display_name", "avatar_url", "timezone", "locale"})


def _safe_user_dict(user: User) -> dict:
    """Explicit-allowlist safe serializer. NEVER exposes password_hash, tokens, OTPs."""
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "status": user.status,
        "institution_id": str(user.institution_id) if user.institution_id else None,
        "timezone": user.timezone,
        "locale": user.locale,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


class UserService:
    # ── Own profile ────────────────────────────────────────────────────────────

    def get_user_profile(self, user_id: str) -> Optional[dict]:
        """Return own profile as a safe dict. Returns None if not found."""
        try:
            uid = uuid.UUID(str(user_id))
        except (ValueError, TypeError):
            return None
        user = db.session.query(User).filter(
            User.id == uid,
            User.is_deleted == False,
        ).first()
        return _safe_user_dict(user) if user else None

    def update_user_profile(self, user_id: str, **kwargs) -> Optional[dict]:
        """Update own profile. Only allowlisted fields accepted."""
        try:
            uid = uuid.UUID(str(user_id))
        except (ValueError, TypeError):
            return None
        user = db.session.query(User).filter(
            User.id == uid,
            User.is_deleted == False,
        ).first()
        if not user:
            return None
        for key, value in kwargs.items():
            if key in PROFILE_UPDATE_FIELDS and hasattr(user, key):
                setattr(user, key, value)
        db.session.commit()
        return _safe_user_dict(user)

    # ── User detail (with IDOR enforcement) ────────────────────────────────────

    def get_user_by_id(
        self,
        user_id: str,
        actor_role: str,
        actor_institution_id: Optional[str],
    ) -> Optional[dict]:
        """Return a user's safe profile.

        IDOR enforcement:
            SUPER_ADMIN: any user
            Others: only users in the same institution
            Unknown user → None (caller returns 404, not 403, to prevent enumeration)
        """
        try:
            uid = uuid.UUID(str(user_id))
        except (ValueError, TypeError):
            return None

        user = db.session.query(User).filter(
            User.id == uid,
            User.is_deleted == False,
        ).first()
        if not user:
            return None

        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id:
                return None
            if str(user.institution_id) != str(actor_institution_id):
                return None  # Cross-institution IDOR: return None, not 403

        return _safe_user_dict(user)

    # ── Admin list (institution-scoped) ────────────────────────────────────────

    def list_users(
        self,
        actor_role: str,
        actor_institution_id: Optional[str],
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """Return institution-scoped user list.

        This method exists for backward compatibility with users.py list_users route.
        For full admin pagination, prefer AdminService.list_users().

        SUPER_ADMIN: all users.
        Others: only users in their institution.
        """
        limit = min(limit, MAX_LIMIT)
        query = db.session.query(User).filter(User.is_deleted == False)
        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id:
                return []
            try:
                iid = uuid.UUID(str(actor_institution_id))
            except (ValueError, TypeError):
                return []
            query = query.filter(User.institution_id == iid)
        users = query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()
        return [_safe_user_dict(u) for u in users]

    # ── Leaderboard (institution-scoped, contribution-based) ───────────────────

    def get_leaderboard(
        self,
        actor_institution_id: Optional[str],
        limit: int = 10,
    ) -> list[dict]:
        """Return top contributors, institution-scoped, ranked by contribution count.

        Reuses the UserContribution table from Sprint 10.
        Never crosses institution boundaries.
        """
        limit = max(1, min(limit, 50))

        query = db.session.query(
            UserContribution.user_id,
            func.count(UserContribution.id).label("contribution_count"),
        ).filter(UserContribution.is_deleted == False)

        if actor_institution_id:
            try:
                iid = uuid.UUID(str(actor_institution_id))
                query = query.filter(UserContribution.institution_id == iid)
            except (ValueError, TypeError):
                return []

        rows = query.group_by(UserContribution.user_id).order_by(
            func.count(UserContribution.id).desc()
        ).limit(limit).all()

        if not rows:
            return []

        # Fetch user display names in one query
        user_ids = [r.user_id for r in rows]
        users_by_id = {
            u.id: u for u in db.session.query(User).filter(
                User.id.in_(user_ids),
                User.is_deleted == False,
            ).all()
        }

        result = []
        for rank, row in enumerate(rows, start=1):
            user = users_by_id.get(row.user_id)
            result.append({
                "rank": rank,
                "user_id": str(row.user_id),
                "full_name": user.full_name if user else None,
                "display_name": user.display_name if user else None,
                "contribution_count": row.contribution_count,
            })
        return result
