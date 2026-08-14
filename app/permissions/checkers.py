from flask import g
from .permissions import ROLE_PERMISSIONS

def has_role(role: str) -> bool:
    """Check if the current user has the specified role."""
    if not hasattr(g, "current_user") or not g.current_user:
        return False
    
    # Check if role matches or if user is SUPER_ADMIN
    user_role = g.current_user.get("role")
    if user_role == "SUPER_ADMIN":
        return True
        
    return user_role == role

def has_permission(permission: str) -> bool:
    """Check if the current user has the specified permission."""
    if not hasattr(g, "current_user") or not g.current_user:
        return False
        
    user_role = g.current_user.get("role")
    
    if user_role == "SUPER_ADMIN":
        return True
        
    permissions = ROLE_PERMISSIONS.get(user_role, [])
    return permission in permissions
