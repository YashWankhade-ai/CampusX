import jwt
import datetime
import uuid
from typing import Dict, Optional, Tuple
from flask import current_app

class TokenService:
    @staticmethod
    def _get_secret() -> str:
        return current_app.config.get("SECRET_KEY", "dev-secret-key-campusx-2026")

    @staticmethod
    def _get_redis():
        try:
            from app.extensions import redis_client
            return redis_client
        except ImportError:
            return None

    @classmethod
    def generate_token_pair(cls, user_id: str, role: str, family_id: Optional[str] = None) -> Tuple[str, str, str, str]:
        """
        Generate a 15-minute access token and 14-day refresh token.
        Returns: (access_token, refresh_token, family_id, jti)
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        secret = cls._get_secret()

        # Access Token (15 min)
        access_jti = str(uuid.uuid4())
        access_payload = {
            "sub": str(user_id),
            "role": role,
            "jti": access_jti,
            "iat": now,
            "exp": now + datetime.timedelta(minutes=15),
            "type": "access"
        }
        access_token = jwt.encode(access_payload, secret, algorithm="HS256")

        # Refresh Token (14 days) with Token Family Rotation
        refresh_jti = str(uuid.uuid4())
        if not family_id:
            family_id = str(uuid.uuid4())

        refresh_payload = {
            "sub": str(user_id),
            "role": role,
            "family_id": family_id,
            "jti": refresh_jti,
            "iat": now,
            "exp": now + datetime.timedelta(days=14),
            "type": "refresh"
        }
        refresh_token = jwt.encode(refresh_payload, secret, algorithm="HS256")

        # Track active refresh token in Redis
        r = cls._get_redis()
        if r:
            ttl = 14 * 86400
            r.setex(f"refresh_active:{refresh_jti}", ttl, family_id)
            r.setex(f"family_user:{family_id}", ttl, str(user_id))

        return access_token, refresh_token, family_id, refresh_jti

    @classmethod
    def verify_token(cls, token: str, expected_type: str = "access") -> Optional[Dict]:
        """Verify JWT signature, expiration, and Redis revocation status."""
        try:
            secret = cls._get_secret()
            payload = jwt.decode(token, secret, algorithms=["HS256"])

            if payload.get("type") != expected_type:
                return None

            jti = payload.get("jti")
            family_id = payload.get("family_id")
            r = cls._get_redis()

            if r:
                # Check blocklist
                if r.get(f"blocklist:{token}") or r.get(f"blocklist_jti:{jti}"):
                    return None

                # Check family revocation
                if family_id and r.get(f"revoked_family:{family_id}"):
                    return None

            return payload
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None

    @classmethod
    def rotate_refresh_token(cls, refresh_token: str) -> Optional[Tuple[str, str]]:
        """
        Rotates refresh token. Revokes old refresh_jti and generates a new pair.
        If a revoked token is reused, revokes the entire family!
        """
        payload = cls.verify_token(refresh_token, expected_type="refresh")
        if not payload:
            return None

        user_id = payload.get("sub")
        role = payload.get("role", "STUDENT")
        family_id = payload.get("family_id")
        jti = payload.get("jti")

        r = cls._get_redis()
        if r:
            # Check if this refresh token was already used/revoked (Reuse Detection)
            if not r.get(f"refresh_active:{jti}"):
                # Revoke whole family on reuse detection!
                r.setex(f"revoked_family:{family_id}", 14 * 86400, "breach_detected")
                return None

            # Invalidate old refresh token
            r.delete(f"refresh_active:{jti}")
            r.setex(f"blocklist_jti:{jti}", 14 * 86400, "rotated")

        access_token, new_refresh_token, _, _ = cls.generate_token_pair(user_id, role, family_id=family_id)
        return access_token, new_refresh_token

    @classmethod
    def block_token(cls, token: str) -> bool:
        """Blocklist a token (used on Logout)."""
        r = cls._get_redis()
        try:
            payload = jwt.decode(token, cls._get_secret(), algorithms=["HS256"])
            jti = payload.get("jti")
            exp = payload.get("exp")
            now = datetime.datetime.now(datetime.timezone.utc).timestamp()
            ttl = int(exp - now) if exp else 3600
            if ttl > 0 and r:
                r.setex(f"blocklist:{token}", ttl, "true")
                if jti:
                    r.setex(f"blocklist_jti:{jti}", ttl, "true")
            return True
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return False

    @classmethod
    def decode_token(cls, token: str) -> Optional[Dict]:
        return cls.verify_token(token, "access")
