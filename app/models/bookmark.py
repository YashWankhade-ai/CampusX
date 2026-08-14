import uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey
from app.models.base import BaseModel

class BookmarkFolder(BaseModel):
    __tablename__ = "bookmark_folders"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    user: Mapped["User"] = relationship("User")
    bookmarks: Mapped[list["Bookmark"]] = relationship("Bookmark", back_populates="folder", cascade="all, delete-orphan")

class Bookmark(BaseModel):
    __tablename__ = "bookmarks"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookmark_folders.id", ondelete="SET NULL"), nullable=True)

    user: Mapped["User"] = relationship("User")
    resource: Mapped["StudyMaterial"] = relationship("StudyMaterial")
    folder: Mapped["BookmarkFolder"] = relationship("BookmarkFolder", back_populates="bookmarks")
