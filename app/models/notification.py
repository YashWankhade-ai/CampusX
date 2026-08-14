import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Boolean, Text
from app.models.base import BaseModel

class NotificationTemplate(BaseModel):
    __tablename__ = "notification_templates"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    body_template: Mapped[str] = mapped_column(Text)

class Notification(BaseModel):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

class UserDevice(BaseModel):
    __tablename__ = "user_devices"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    device_token: Mapped[str] = mapped_column(String(255), unique=True)
    platform: Mapped[str] = mapped_column(String(50)) # ios, android, web
