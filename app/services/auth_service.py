import secrets
import hashlib
import logging
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models.user import User, OTPCode
from app.models.academic import Institution
from app.repositories.user_repository import UserRepository
from app.utils.hashing import hash_password, verify_password
from app.utils.token import generate_access_token, decode_access_token
from app.utils.redis_client import get_redis_client
from app.tasks.email import send_otp_email

logger = logging.getLogger(__name__)

def generate_secure_otp() -> str:
    """Generates a cryptographically secure 6-digit OTP code zero-padded to 6 digits."""
    return f"{secrets.randbelow(10**6):06d}"

def hash_otp_code(code: str) -> str:
    """Computes SHA-256 hex digest of a 6-digit OTP string."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()

class AuthService:
    """
    Authentication Service Layer for CampusX.
    Encapsulates business logic for credential validation, registration, OTP generation, and email verification.
    """
    def __init__(self, user_repository: Optional[UserRepository] = None):
        self.user_repo = user_repository if user_repository is not None else UserRepository()
        self.redis = get_redis_client()

    def register_user(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], int]:
        """
        Registers a new user in 'pending_verification' status and issues a 6-digit OTP code.
        Never exposes the plaintext OTP in API response or logs.
        """
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            return False, {"code": "VALIDATION_ERROR", "message": "Email and password are required"}, 400

        existing = self.user_repo.find_by_email(email)
        if existing:
            return False, {"code": "USER_EXISTS", "message": "Account already exists"}, 409

        # Default institution lookup/fallback
        inst = db.session.query(Institution).first()
        if not inst:
            inst = Institution(name="Default Institution", short_name="DEFAULT", code="DEFAULT-01", domain_whitelist=[])
            db.session.add(inst)
            db.session.commit()

        # 1. Create user with status=pending_verification
        user = User(
            institution_id=inst.id,
            email=email,
            email_normalized=email,
            full_name=f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "CampusX User",
            password_hash=hash_password(password),
            role=data.get("role", "STUDENT").upper(),
            status="pending_verification"
        )
        self.user_repo.create(user)
        db.session.flush()

        # 2. Generate 6-digit OTP code & SHA-256 hash
        otp_code = generate_secure_otp()
        code_hash = hash_otp_code(otp_code)
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(minutes=10)

        # 3. Store OTP record in database
        otp_record = OTPCode(
            user_id=user.id,
            email=email,
            purpose="email_verification",
            code_hash=code_hash,
            attempt_count=0,
            max_attempts=5,
            expires_at=expires_at
        )
        self.user_repo.create_otp(otp_record)
        db.session.commit()

        # 4. Store Redis entry (otp:{email}:email_verification -> code_hash, EX=600)
        redis_key = f"otp:{email}:email_verification"
        self.redis.set(redis_key, code_hash, ex=600)

        # 5. Queue Celery email task (async, non-blocking)
        send_otp_email.delay(email, otp_code)

        logger.info(f"OTP issued for email: {email}")

        verification_token = generate_access_token(user, expires_in_seconds=86400)

        return True, {
            "id": str(user.id),
            "email": user.email,
            "status": user.status,
            "verification_token": verification_token,
            "message": "Registration successful. Verification OTP sent to email."
        }, 201

    def verify_email_otp(self, email: str, otp_code: str) -> Tuple[bool, Dict[str, Any], int]:
        """
        Verifies a 6-digit email verification OTP.
        Increments attempt_count BEFORE verification check.
        Activates user and deletes Redis key on success.
        """
        if not email or not otp_code:
            return False, {"code": "VALIDATION_ERROR", "message": "Email and OTP code are required"}, 400

        email_normalized = email.strip().lower()
        otp_record = self.user_repo.find_pending_otp(email_normalized, purpose="email_verification")

        if not otp_record:
            return False, {"code": "INVALID_OTP", "message": "No pending verification code found"}, 400

        now_utc = datetime.now(timezone.utc)
        expires_at = otp_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now_utc > expires_at:
            return False, {"code": "EXPIRED_OTP", "message": "Verification code has expired. Please request a new one."}, 400

        # Increment attempt_count BEFORE verification check
        otp_record.attempt_count += 1
        db.session.commit()

        if otp_record.attempt_count > otp_record.max_attempts:
            return False, {"code": "MAX_ATTEMPTS_EXCEEDED", "message": "Too many failed attempts. Please request a new verification code."}, 423

        submitted_hash = hash_otp_code(otp_code.strip())
        if submitted_hash != otp_record.code_hash:
            return False, {"code": "INVALID_OTP", "message": "Incorrect verification code"}, 400

        # Mark OTP as used
        otp_record.used_at = now_utc

        # Activate user account
        user = self.user_repo.find_by_email(email_normalized)
        if user:
            user.status = "active"

        db.session.commit()

        # Remove Redis OTP key
        redis_key = f"otp:{email_normalized}:email_verification"
        self.redis.delete(redis_key)

        # Issue signed JWT access + refresh tokens
        access_token = generate_access_token(user, expires_in_seconds=900)
        refresh_token = generate_access_token(user, expires_in_seconds=1209600)

        user_dict = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": str(getattr(user, "role", "STUDENT")).upper(),
            "status": user.status,
            "institution_id": str(user.institution_id) if getattr(user, "institution_id", None) else None
        }

        return True, {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 900,
            "user": user_dict,
            "message": "Email verified successfully"
        }, 200

    def authenticate(self, email: str, password: str) -> Tuple[bool, Dict[str, Any], int]:
        """
        Validates user credentials against stored Argon2id hash.
        Generates signed 15-minute JWT access token on success.
        Denies access cleanly on failure without exposing internal state.
        """
        if not email or not password:
            return False, {"code": "VALIDATION_ERROR", "message": "Email and password are required"}, 400

        user = self.user_repo.find_by_email(email)

        # Fail securely if user not found or deleted
        if not user or getattr(user, "is_deleted", False):
            verify_password("dummy_password", "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy")
            return False, {"code": "UNAUTHORIZED", "message": "Invalid email or password"}, 401

        # Check account lockout before checking password
        now_utc = datetime.now(timezone.utc)
        if getattr(user, "locked_until", None):
            locked_until = user.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if now_utc < locked_until:
                return False, {"code": "ACCOUNT_LOCKED", "message": "Account is temporarily locked. Please try again later."}, 423

        # Constant-time password verification
        if not verify_password(password, user.password_hash):
            user.failed_login_attempts = getattr(user, "failed_login_attempts", 0) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now_utc + timedelta(minutes=15)
            db.session.commit()

            if user.failed_login_attempts >= 5:
                return False, {"code": "ACCOUNT_LOCKED", "message": "Account locked due to 5 failed login attempts."}, 423
            return False, {"code": "UNAUTHORIZED", "message": "Invalid email or password"}, 401

        # Update last login timestamp and reset failed attempts
        self.user_repo.update_last_login(user)
        db.session.commit()

        # Issue signed JWT access token (15 minutes expiry = 900 seconds) and refresh token (14 days = 1209600 seconds)
        access_token = generate_access_token(user, expires_in_seconds=900)
        refresh_token = generate_access_token(user, expires_in_seconds=1209600)

        user_dict = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": str(getattr(user, "role", "STUDENT")).upper(),
            "status": user.status,
            "institution_id": str(user.institution_id) if getattr(user, "institution_id", None) else None
        }

        return True, {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 900,
            "user": user_dict
        }, 200

    def refresh_token(self, token: str) -> Tuple[bool, Dict[str, Any], int]:
        payload = decode_access_token(token)
        if not payload:
            return False, {"code": "UNAUTHORIZED", "message": "Invalid or expired refresh token"}, 401

        user = self.user_repo.find_by_id(payload.get("sub"))
        if not user:
            return False, {"code": "UNAUTHORIZED", "message": "User not found"}, 401

        new_access_token = generate_access_token(user, expires_in_seconds=900)
        new_refresh_token = generate_access_token(user, expires_in_seconds=1209600)

        return True, {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
            "expires_in": 900
        }, 200

    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validates JWT access token and returns payload if valid."""
        return decode_access_token(token)
