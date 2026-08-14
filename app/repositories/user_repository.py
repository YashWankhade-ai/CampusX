import uuid
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import select, func, or_, desc
from app.extensions import db
from app.models.user import User, OTPCode

class UserRepository:
    """
    Data-access layer for User and OTP entities.
    Follows separation of concerns: does NOT access Flask request objects or commit transactions directly.
    """
    def __init__(self, session=None):
        self._session = session

    @property
    def session(self):
        return self._session if self._session is not None else db.session

    def find_by_id(self, user_id: uuid.UUID | str) -> Optional[User]:
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return None
        stmt = select(User).where(User.id == user_id, User.is_deleted == False)
        return self.session.execute(stmt).scalar_one_or_none()

    def find_by_email(self, email: str) -> Optional[User]:
        if not email:
            return None
        normalized_email = email.lower().strip()
        stmt = select(User).where(
            User.email_normalized == normalized_email,
            User.is_deleted == False
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def create(self, user: User) -> User:
        self.session.add(user)
        return user

    def update_last_login(self, user: User, login_time=None) -> None:
        user.last_login_at = login_time or datetime.now(timezone.utc)
        user.failed_login_attempts = 0

    # OTP Persistence Methods
    def create_otp(self, otp_record: OTPCode) -> OTPCode:
        self.session.add(otp_record)
        return otp_record

    def find_pending_otp(self, email: str, purpose: str = "email_verification") -> Optional[OTPCode]:
        if not email:
            return None
        normalized_email = email.lower().strip()
        stmt = select(OTPCode).where(
            OTPCode.email == normalized_email,
            OTPCode.purpose == purpose,
            OTPCode.used_at == None,
            OTPCode.is_deleted == False
        ).order_by(desc(OTPCode.created_at))
        return self.session.execute(stmt).scalars().first()
