import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Integer
from app.models.base import BaseModel

class ContributionType(BaseModel):
    __tablename__ = "contribution_types"
    name: Mapped[str] = mapped_column(String(100))
    points: Mapped[int] = mapped_column(Integer, default=10)

class UserContribution(BaseModel):
    __tablename__ = "user_contributions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    contribution_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contribution_types.id"), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("study_materials.id"), nullable=True)

Contribution = UserContribution

class Badge(BaseModel):
    __tablename__ = "badges"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

class Leaderboard(BaseModel):
    __tablename__ = "leaderboards"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    total_points: Mapped[int] = mapped_column(Integer, default=0, index=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
