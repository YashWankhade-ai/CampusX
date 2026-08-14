import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, DateTime
from app.models.base import BaseModel
from datetime import datetime

class QRCode(BaseModel):
    __tablename__ = "qr_codes"
    entity_type: Mapped[str] = mapped_column(String(100)) # user, resource, event
    entity_id: Mapped[str] = mapped_column(String(100))
    code_data: Mapped[str] = mapped_column(String(500), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class QRCodeScan(BaseModel):
    __tablename__ = "qr_code_scans"
    qr_code_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qr_codes.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    location_data: Mapped[str | None] = mapped_column(String(255), nullable=True)
