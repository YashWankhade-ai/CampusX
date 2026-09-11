"""Admin & Institution Management Service — Sprint 12.

Implements all administrative operations with strict:
- Institution isolation (INSTITUTION_ADMIN sees only their institution)
- Privilege escalation prevention (cannot grant a role higher than your own)
- IDOR prevention (target user must be in same institution as admin, except SUPER_ADMIN)
- Audit safety (safe dicts only — no passwords, tokens, hashes)

Role hierarchy (ascending privilege):
    GUEST < STUDENT < FACULTY < MODERATOR < INSTITUTION_ADMIN < SUPER_ADMIN

Rules:
    SUPER_ADMIN     — can manage all institutions and all users
    INSTITUTION_ADMIN — can manage users within their own institution only
                        cannot promote anyone to INSTITUTION_ADMIN or SUPER_ADMIN
    MODERATOR/FACULTY/STUDENT — no admin operations
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from app.extensions import db
from app.models.user import User
from app.models.academic import Institution
from app.permissions.roles import Role, ROLE_HIERARCHY, get_role_level

logger = logging.getLogger(__name__)

# Statuses that are valid for user accounts
VALID_USER_STATUSES = frozenset({"active", "inactive", "suspended", "pending_verification"})

# Roles an INSTITUTION_ADMIN is allowed to assign (cannot assign their own level or above)
INSTITUTION_ADMIN_ASSIGNABLE_ROLES = frozenset({
    Role.STUDENT,
    Role.FACULTY,
    Role.MODERATOR,
})

# All assignable roles (only SUPER_ADMIN can assign these)
SUPER_ADMIN_ASSIGNABLE_ROLES = frozenset({
    Role.STUDENT,
    Role.FACULTY,
    Role.MODERATOR,
    Role.INSTITUTION_ADMIN,
})

# Fields safe to return in admin user listings
_SAFE_USER_FIELDS = (
    "id", "email", "full_name", "display_name", "role",
    "status", "institution_id", "created_at", "last_login_at",
)

MAX_PAGE_SIZE = 100


def _safe_user_dict(user: User) -> dict:
    """Return a safe dict of user fields. NEVER includes password_hash, OTPs, or tokens."""
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name,
        "role": user.role,
        "status": user.status,
        "institution_id": str(user.institution_id) if user.institution_id else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _safe_institution_dict(inst: Institution) -> dict:
    """Return a safe dict of institution fields."""
    return {
        "id": str(inst.id),
        "name": inst.name,
        "short_name": inst.short_name,
        "code": inst.code,
        "is_active": inst.is_active,
        "subscription_tier": inst.subscription_tier,
        "city": inst.city,
        "country": inst.country,
        "created_at": inst.created_at.isoformat() if inst.created_at else None,
    }


# ── Institution Management ────────────────────────────────────────────────────

class AdminService:
    """Thin service layer for admin operations. All methods enforce authorization."""

    # ── Institution endpoints ─────────────────────────────────────────────────

    def list_institutions(self, actor_role: str, actor_institution_id: Optional[str]) -> list[dict]:
        """Return institution list.

        SUPER_ADMIN: all institutions.
        Others: only their own institution (if any).
        """
        if actor_role == Role.SUPER_ADMIN:
            insts = db.session.query(Institution).filter(
                Institution.is_deleted == False
            ).order_by(Institution.name).all()
        elif actor_institution_id:
            try:
                iid = uuid.UUID(actor_institution_id)
            except (ValueError, TypeError):
                return []
            insts = db.session.query(Institution).filter(
                Institution.id == iid,
                Institution.is_deleted == False,
            ).all()
        else:
            return []
        return [_safe_institution_dict(i) for i in insts]

    def get_institution(self, institution_id: str, actor_role: str,
                        actor_institution_id: Optional[str]) -> Optional[dict]:
        """Return a single institution.

        SUPER_ADMIN: any institution.
        INSTITUTION_ADMIN: only their own.
        """
        try:
            iid = uuid.UUID(institution_id)
        except (ValueError, TypeError):
            return None

        inst = db.session.query(Institution).filter(
            Institution.id == iid,
            Institution.is_deleted == False,
        ).first()
        if not inst:
            return None

        # Institution isolation — non-SUPER_ADMIN can only see their own institution
        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id or str(inst.id) != actor_institution_id:
                return None

        return _safe_institution_dict(inst)

    def update_institution(self, institution_id: str, data: dict,
                           actor_role: str, actor_institution_id: Optional[str]) -> Optional[dict]:
        """Update allowed institution fields.

        SUPER_ADMIN: any institution.
        INSTITUTION_ADMIN: only their own; cannot change subscription_tier or is_active.
        """
        try:
            iid = uuid.UUID(institution_id)
        except (ValueError, TypeError):
            return None, "Invalid institution ID"

        inst = db.session.query(Institution).filter(
            Institution.id == iid,
            Institution.is_deleted == False,
        ).first()
        if not inst:
            return None, "Institution not found"

        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id or str(inst.id) != actor_institution_id:
                return None, "Access denied"

        # INSTITUTION_ADMIN-safe fields
        allowed_fields = {"name", "short_name", "city", "state", "country",
                          "address_line1", "address_line2", "postal_code",
                          "phone", "logo_url", "website_url", "settings_json"}
        # SUPER_ADMIN can also manage these
        if actor_role == Role.SUPER_ADMIN:
            allowed_fields |= {"is_active", "subscription_tier", "subscription_expires_at",
                                "max_storage_bytes", "domain_whitelist", "accreditation_code"}

        for key, value in data.items():
            if key in allowed_fields and hasattr(inst, key):
                setattr(inst, key, value)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return None, str(e)

        return _safe_institution_dict(inst), None

    def create_institution(self, data: dict, actor_role: str) -> tuple[Optional[dict], Optional[str]]:
        """Create a new institution. SUPER_ADMIN only."""
        if actor_role != Role.SUPER_ADMIN:
            return None, "Only SUPER_ADMIN can create institutions"

        required = ("name", "short_name", "code")
        for field in required:
            if not data.get(field):
                return None, f"Missing required field: {field}"

        # Check code uniqueness
        existing = db.session.query(Institution).filter(
            Institution.code == data["code"],
            Institution.is_deleted == False,
        ).first()
        if existing:
            return None, "Institution code already exists"

        inst = Institution(
            id=uuid.uuid4(),
            name=data["name"],
            short_name=data["short_name"],
            code=data["code"],
            city=data.get("city"),
            country=data.get("country", "India"),
            is_active=data.get("is_active", True),
        )
        db.session.add(inst)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return None, str(e)
        return _safe_institution_dict(inst), None

    # ── User Management ───────────────────────────────────────────────────────

    def list_users(self, actor_role: str, actor_institution_id: Optional[str],
                   page: int = 1, limit: int = 20,
                   status_filter: Optional[str] = None) -> tuple[list[dict], int]:
        """Return paginated user list, institution-scoped.

        SUPER_ADMIN: all users across all institutions.
        INSTITUTION_ADMIN: only users in their institution.
        Others: forbidden (enforced at route level, not here).
        """
        limit = min(limit, MAX_PAGE_SIZE)
        page = max(page, 1)
        offset = (page - 1) * limit

        query = db.session.query(User).filter(User.is_deleted == False)

        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id:
                return [], 0
            try:
                iid = uuid.UUID(actor_institution_id)
            except (ValueError, TypeError):
                return [], 0
            query = query.filter(User.institution_id == iid)

        if status_filter and status_filter in VALID_USER_STATUSES:
            query = query.filter(User.status == status_filter)

        from sqlalchemy import func
        total = query.with_entities(func.count(User.id)).scalar() or 0
        users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
        return [_safe_user_dict(u) for u in users], total

    def get_user(self, user_id: str, actor_role: str,
                 actor_institution_id: Optional[str]) -> Optional[dict]:
        """Return a single user.

        SUPER_ADMIN: any user.
        INSTITUTION_ADMIN/MODERATOR: only users in same institution.
        IDOR prevention: institution check is server-side.
        """
        try:
            uid = uuid.UUID(user_id)
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
            if str(user.institution_id) != actor_institution_id:
                return None  # IDOR prevention

        return _safe_user_dict(user)

    def set_user_status(self, user_id: str, new_status: str,
                        actor_role: str, actor_institution_id: Optional[str],
                        actor_user_id: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
        """Activate, deactivate, or suspend a user.

        Rules:
        - SUPER_ADMIN: any user in any institution
        - INSTITUTION_ADMIN: users in their institution only; cannot deactivate themselves
        - new_status must be in VALID_USER_STATUSES
        - Never destructively deletes — soft status change only
        """
        if new_status not in VALID_USER_STATUSES:
            return None, f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(VALID_USER_STATUSES))}"

        try:
            uid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return None, "Invalid user ID"

        user = db.session.query(User).filter(
            User.id == uid,
            User.is_deleted == False,
        ).first()
        if not user:
            return None, "User not found"

        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id or str(user.institution_id) != actor_institution_id:
                return None, "User not found"  # IDOR: reveal nothing
            # Self-deactivation prevention
            if actor_user_id and str(uid) == str(actor_user_id):
                return None, "Cannot change your own account status"

        user.status = new_status
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return None, str(e)
        return _safe_user_dict(user), None

    def change_user_role(self, user_id: str, new_role: str,
                         actor_role: str, actor_institution_id: Optional[str],
                         actor_user_id: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
        """Change a user's role.

        Privilege escalation prevention:
        - INSTITUTION_ADMIN can only assign STUDENT, FACULTY, MODERATOR
          (cannot promote to INSTITUTION_ADMIN or SUPER_ADMIN)
        - SUPER_ADMIN can assign any role except SUPER_ADMIN (to prevent accident)
        - Nobody can self-promote
        - Nobody can promote beyond their own level
        - Institution isolation enforced for INSTITUTION_ADMIN
        """
        if new_role not in {r for r in vars(Role).values() if isinstance(r, str) and not r.startswith("_")}:
            return None, f"Invalid role: {new_role}"

        # Self-promotion prevention
        if actor_user_id and str(actor_user_id) == str(user_id):
            return None, "Cannot change your own role"

        # Privilege escalation check
        actor_level = get_role_level(actor_role)
        new_role_level = get_role_level(new_role)

        if actor_role == Role.SUPER_ADMIN:
            # SUPER_ADMIN can assign any role below SUPER_ADMIN
            if new_role == Role.SUPER_ADMIN:
                return None, "Cannot promote to SUPER_ADMIN via API"
            allowed = SUPER_ADMIN_ASSIGNABLE_ROLES
        elif actor_role == Role.INSTITUTION_ADMIN:
            allowed = INSTITUTION_ADMIN_ASSIGNABLE_ROLES
            if new_role not in allowed:
                return None, f"INSTITUTION_ADMIN cannot assign role: {new_role}"
        else:
            return None, "Insufficient privileges to change roles"

        try:
            uid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return None, "Invalid user ID"

        user = db.session.query(User).filter(
            User.id == uid,
            User.is_deleted == False,
        ).first()
        if not user:
            return None, "User not found"

        # Institution isolation for non-super-admin
        if actor_role != Role.SUPER_ADMIN:
            if not actor_institution_id or str(user.institution_id) != actor_institution_id:
                return None, "User not found"  # IDOR

        # Cannot demote/change a user whose role is >= actor's role (except SUPER_ADMIN)
        target_level = get_role_level(user.role)
        if actor_role != Role.SUPER_ADMIN and target_level >= actor_level:
            return None, "Cannot modify a user with equal or higher privileges"

        user.role = new_role
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return None, str(e)
        return _safe_user_dict(user), None
