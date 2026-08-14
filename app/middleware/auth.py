from functools import wraps
from flask import request
from app.utils.response_utils import error_response
from app.utils.token import decode_access_token

class UserContext:
    def __init__(self, user_id, role, institution_id=None, email=None):
        self.id = user_id
        self.role = role.upper() if role else "STUDENT"
        self.institution_id = institution_id
        self.email = email

def require_auth(f):
    """
    Flask decorator for protected routes requiring a valid JWT access token.
    Extracts Bearer token from 'Authorization: Bearer <token>' header or 'access_token' cookie.
    Sets request.user context or returns 401 Unauthorized error response.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]

        if not token:
            token = request.cookies.get("access_token")

        if not token:
            return error_response(
                code="UNAUTHORIZED",
                message="Authentication required. Missing token.",
                status_code=401
            )

        payload = decode_access_token(token)
        if not payload:
            return error_response(
                code="UNAUTHORIZED",
                message="Token is invalid or expired.",
                status_code=401
            )

        request.user = UserContext(
            user_id=payload.get("sub"),
            role=payload.get("role", "STUDENT"),
            institution_id=payload.get("institution_id"),
            email=payload.get("email")
        )
        return f(*args, **kwargs)

    return decorated

def require_role(roles):
    if isinstance(roles, str):
        roles = [roles]
    allowed_roles_upper = [r.upper() for r in roles]

    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            user_role = getattr(request.user, "role", "GUEST").upper()
            if user_role == "SUPER_ADMIN" or user_role in allowed_roles_upper:
                return f(*args, **kwargs)
            return error_response(
                code="FORBIDDEN",
                message=f"Access denied. Required role(s): {', '.join(roles)}",
                status_code=403
            )
        return decorated
    return decorator

# Alias for decorator readability
token_required = require_auth
