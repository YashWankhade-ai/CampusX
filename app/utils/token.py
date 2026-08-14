import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
import jwt
from flask import current_app

logger = logging.getLogger(__name__)

def get_jwt_secret_key() -> str:
    """Retrieve environment-driven JWT secret key without exposing in source code."""
    if current_app and current_app.config.get("JWT_SECRET_KEY"):
        return current_app.config["JWT_SECRET_KEY"]
    if current_app and current_app.config.get("SECRET_KEY"):
        return current_app.config["SECRET_KEY"]
    return os.environ.get("JWT_SECRET_KEY", os.environ.get("SECRET_KEY", "dev-secret-key-campusx-2026"))

def generate_access_token(user, expires_in_seconds: int = 900) -> str:
    """
    Generates a signed HS256 JWT access token for an authenticated user.
    Claims adhere to CampusX Security Architecture Section 3.2.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=expires_in_seconds)

    payload = {
        "iss": "campusx-api",
        "sub": str(user.id),
        "aud": "campusx-api",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "nbf": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
        "institution_id": str(user.institution_id) if hasattr(user, "institution_id") and user.institution_id else None,
        "role": str(user.role).upper() if hasattr(user, "role") and user.role else "STUDENT",
        "email": getattr(user, "email", "")
    }

    secret_key = get_jwt_secret_key()
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token

def decode_access_token(token: str) -> dict | None:
    """
    Decodes and validates a JWT access token.
    Returns claims payload if valid, or None if expired/invalid.
    """
    if not token:
        return None

    try:
        secret_key = get_jwt_secret_key()
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            audience="campusx-api",
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True}
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("JWT validation failed: Token signature expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("JWT validation failed: Invalid token payload")
        return None
    except Exception as e:
        logger.debug(f"JWT validation failed: {e}")
        return None
