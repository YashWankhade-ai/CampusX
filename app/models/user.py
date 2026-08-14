import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Integer, SmallInteger, Boolean, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from app.models.base import BaseModel

# Portable JSON type for PostgreSQL JSONB and SQLite fallback in testing
JSONType = JSONB().with_variant(JSON(), "sqlite")

class User(BaseModel):
    """
    Universal user model for CampusX.
    Conforms to CampusX Database Specification Section 12 (Domain 1).
    """
    __tablename__ = "users"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="STUDENT", index=True, nullable=False)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_verification")
    failed_login_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Kolkata")
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    notification_prefs_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)

    # Relationships
    institution: Mapped[Optional["Institution"]] = relationship("Institution", back_populates="users")
    profile: Mapped[Optional["Profile"]] = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    study_materials: Mapped[List["StudyMaterial"]] = relationship("StudyMaterial", back_populates="author", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        first_name = kwargs.pop("first_name", None)
        last_name = kwargs.pop("last_name", None)
        if (first_name or last_name) and "full_name" not in kwargs:
            kwargs["full_name"] = f"{first_name or ''} {last_name or ''}".strip()
        if "email" in kwargs and "email_normalized" not in kwargs:
            kwargs["email_normalized"] = kwargs["email"].lower()
        super().__init__(**kwargs)

    @property
    def first_name(self) -> str:
        parts = (self.full_name or "").split(" ")
        return parts[0] if parts else ""

    @property
    def last_name(self) -> str:
        parts = (self.full_name or "").split(" ")
        return parts[-1] if len(parts) > 1 else ""

    __table_args__ = (
        UniqueConstraint("institution_id", "email_normalized", name="uq_users_email_normalized_per_institution"),
        Index("uq_users_email_normalized", "email_normalized"),
        Index("ix_users_institution_id", "institution_id"),
        Index("ix_users_status", "status"),
    )

class Role(BaseModel):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")

class UserRole(BaseModel):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="user_roles")
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")

class Profile(BaseModel):
    __tablename__ = "profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="profile")

class OTPCode(BaseModel):
    """
    One-time password codes for email verification and 2FA. Short-lived.
    Conforms to CampusX Database Specification Section 12 (Domain 1, Table 1.5).
    """
    __tablename__ = "otp_codes"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, default="email_verification")
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_otp_codes_email_purpose", "email", "purpose"),
        Index("ix_otp_codes_expires_at", "expires_at"),
    )
