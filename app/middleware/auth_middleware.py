from flask import request, g
from app.utils.response_utils import error_response
from app.services.token_service import TokenService

def auth_middleware():
    """Middleware to parse and validate token on requests if present."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        payload = TokenService.verify_token(token)
        if payload:
            g.current_user = payload
