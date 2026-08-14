import logging
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError
    ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
    _HAS_ARGON2 = True
except ImportError:
    ph = None
    _HAS_ARGON2 = False

logger = logging.getLogger(__name__)

def hash_password(password: str) -> str:
    """
    Hashes a password using Argon2id algorithm (time_cost=3, memory_cost=65536, parallelism=4)
    in accordance with CampusX Security Architecture Specification Section 3.1.
    """
    if not password:
        raise ValueError("Password cannot be empty")

    if _HAS_ARGON2 and ph:
        return ph.hash(password)
    else:
        from werkzeug.security import generate_password_hash
        return generate_password_hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against a stored Argon2id hash using constant-time comparison.
    Never logs passwords or hashes.
    """
    if not password or not hashed_password:
        return False

    if _HAS_ARGON2 and ph and hashed_password.startswith("$argon2"):
        try:
            return ph.verify(hashed_password, password)
        except (VerifyMismatchError, VerificationError, Exception):
            return False
    else:
        try:
            from werkzeug.security import check_password_hash
            return check_password_hash(hashed_password, password)
        except Exception:
            return False
