from app.models.user import User
from .roles import Role, get_role_level
from .permissions import ROLE_PERMISSIONS
import uuid

def _get_role(user_or_role) -> str:
    """Helper to extract role string."""
    if not user_or_role:
        return None
    if isinstance(user_or_role, str):
        return user_or_role
    if hasattr(user_or_role, 'role'):
        return user_or_role.role
    return None

def has_permission(user_or_role, permission: str) -> bool:
    """Check if role has permission."""
    role = _get_role(user_or_role)
    if not role or role not in ROLE_PERMISSIONS:
        return False
    return permission in ROLE_PERMISSIONS[role]

def has_role(user_or_role, required_role: str) -> bool:
    """Check for exact role match."""
    role = _get_role(user_or_role)
    return role == required_role

def has_min_role(user_or_role, min_role: str) -> bool:
    """Check if role level >= min_role level."""
    role = _get_role(user_or_role)
    if not role:
        return False
    role_lvl = get_role_level(role)
    min_lvl = get_role_level(min_role)
    if role_lvl == -1 or min_lvl == -1:
        return False
    return role_lvl >= min_lvl

def is_same_institution(user_institution_id, resource_institution_id) -> bool:
    """Check if institution IDs match."""
    if user_institution_id is None or resource_institution_id is None:
        return False
    return str(user_institution_id) == str(resource_institution_id)

def can_access_resource(user, resource) -> bool:
    """Check if user can access resource."""
    if not user or not resource:
        return False
    role = _get_role(user)
    if role == Role.SUPER_ADMIN:
        return True

    if not has_permission(role, 'resources:read'):
        return False

    return is_same_institution(user.institution_id, getattr(resource, 'institution_id', None))
