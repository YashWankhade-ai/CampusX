import uuid
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Integer, BigInteger, Enum
from app.models.base import BaseModel
import enum

class MaterialType(enum.Enum):
    NOTE = "NOTE"
    QUESTION_PAPER = "QUESTION_PAPER"
    SYLLABUS = "SYLLABUS"
    ASSIGNMENT = "ASSIGNMENT"

class ResourceCategory(BaseModel):
    __tablename__ = "resource_categories"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

class StudyMaterial(BaseModel):
    __tablename__ = "study_materials"
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    material_type: Mapped[MaterialType] = mapped_column(Enum(MaterialType), default=MaterialType.NOTE, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    faculty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    author: Mapped["User"] = relationship("User", back_populates="study_materials")
    subject: Mapped[Optional["Subject"]] = relationship("Subject", foreign_keys=[subject_id])
    versions: Mapped[list["MaterialVersion"]] = relationship("MaterialVersion", back_populates="study_material", cascade="all, delete-orphan")
    comments: Mapped[list["ResourceComment"]] = relationship("ResourceComment", back_populates="study_material", cascade="all, delete-orphan")
    ratings: Mapped[list["ResourceRating"]] = relationship("ResourceRating", back_populates="study_material", cascade="all, delete-orphan")

class MaterialVersion(BaseModel):
    __tablename__ = "material_versions"
    study_material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    file_metadata_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_metadata.id", ondelete="CASCADE"), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    study_material: Mapped["StudyMaterial"] = relationship("StudyMaterial", back_populates="versions")
    file_metadata: Mapped["FileMetadata"] = relationship("FileMetadata")

class FileMetadata(BaseModel):
    __tablename__ = "file_metadata"
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)

class ResourceTag(BaseModel):
    __tablename__ = "resource_tags"
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)

class ResourceTagAssociation(BaseModel):
    __tablename__ = "resource_tag_associations"
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resource_tags.id", ondelete="CASCADE"), nullable=False)

class ResourceComment(BaseModel):
    __tablename__ = "resource_comments"
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    study_material: Mapped["StudyMaterial"] = relationship("StudyMaterial", back_populates="comments")
    user: Mapped["User"] = relationship("User")

class ResourceRating(BaseModel):
    __tablename__ = "resource_ratings"
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)

    study_material: Mapped["StudyMaterial"] = relationship("StudyMaterial", back_populates="ratings")
    user: Mapped["User"] = relationship("User")
