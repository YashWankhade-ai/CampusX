import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Text, Boolean, BigInteger, DateTime, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from app.models.base import BaseModel

# Portable JSON type for PostgreSQL JSONB and SQLite fallback in testing
JSONType = JSONB().with_variant(JSON(), "sqlite")

class Institution(BaseModel):
    """
    Root tenant entity for CampusX.
    Every tenant-scoped record in CampusX references an Institution.
    Conforms to CampusX Database Specification Section 12 (Domain 1).
    """
    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    domain_whitelist: Mapped[dict] = mapped_column(JSONType, nullable=False, default=list)
    logo_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    address_line1: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="India")
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    accreditation_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    subscription_tier: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    max_storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=10737418240)  # 10 GB
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    settings_json: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="institution", cascade="all, delete-orphan")
    departments: Mapped[List["Department"]] = relationship("Department", back_populates="institution", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_institutions_code", "code", unique=True),
        Index("ix_institutions_is_active", "is_active"),
    )

class Department(BaseModel):
    __tablename__ = "departments"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)

    institution: Mapped["Institution"] = relationship("Institution", back_populates="departments")
    programs: Mapped[List["Program"]] = relationship("Program", back_populates="department", cascade="all, delete-orphan")

class Degree(BaseModel):
    __tablename__ = "degrees"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)

    programs: Mapped[List["Program"]] = relationship("Program", back_populates="degree", cascade="all, delete-orphan")

class Program(BaseModel):
    __tablename__ = "programs"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    degree_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("degrees.id", ondelete="CASCADE"), nullable=False)

    department: Mapped["Department"] = relationship("Department", back_populates="programs")
    degree: Mapped["Degree"] = relationship("Degree", back_populates="programs")
    subjects: Mapped[List["Subject"]] = relationship("Subject", back_populates="program", cascade="all, delete-orphan")

class AcademicSession(BaseModel):
    __tablename__ = "academic_sessions"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    end_year: Mapped[int] = mapped_column(Integer, nullable=False)

    semesters: Mapped[List["Semester"]] = relationship("Semester", back_populates="academic_session", cascade="all, delete-orphan")

class Semester(BaseModel):
    __tablename__ = "semesters"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    academic_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_sessions.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    academic_session: Mapped["AcademicSession"] = relationship("AcademicSession", back_populates="semesters")
    subjects: Mapped[List["Subject"]] = relationship("Subject", back_populates="semester", cascade="all, delete-orphan")

class Subject(BaseModel):
    __tablename__ = "subjects"
    code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    semester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=3)

    program: Mapped["Program"] = relationship("Program", back_populates="subjects")
    semester: Mapped["Semester"] = relationship("Semester", back_populates="subjects")
    units: Mapped[List["Unit"]] = relationship("Unit", back_populates="subject", cascade="all, delete-orphan")

class Unit(BaseModel):
    __tablename__ = "units"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    subject: Mapped["Subject"] = relationship("Subject", back_populates="units")
    topics: Mapped[List["Topic"]] = relationship("Topic", back_populates="unit", cascade="all, delete-orphan")

class Topic(BaseModel):
    __tablename__ = "topics"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    unit: Mapped["Unit"] = relationship("Unit", back_populates="topics")
