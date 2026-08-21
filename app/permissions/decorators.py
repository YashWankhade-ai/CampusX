from functools import wraps
from flask import request, jsonify, g
from .checkers import has_permission, has_min_role, is_same_institution
from .roles import Role

def require_permission(permission: str):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not getattr(request, 'user', None):
                return jsonify({"success": False, "error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}), 401

            if not has_permission(request.user, permission):
                return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Permission denied"}}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_min_role(min_role: str):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not getattr(request, 'user', None):
                return jsonify({"success": False, "error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}), 401

            if not has_min_role(request.user, min_role):
                return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Insufficient role level"}}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_same_institution(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not getattr(request, 'user', None):
            return jsonify({"success": False, "error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}), 401

        if getattr(request.user, 'role', None) == Role.SUPER_ADMIN:
            return f(*args, **kwargs)

        inst_id = kwargs.get('institution_id')
        if not inst_id and request.is_json:
            inst_id = request.json.get('institution_id')
        if not inst_id:
            inst_id = request.args.get('institution_id')

        if inst_id and not is_same_institution(request.user.institution_id, inst_id):
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Cross-institution access denied"}}), 403

        return f(*args, **kwargs)
    return decorated_function
