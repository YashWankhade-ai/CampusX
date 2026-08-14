from .base import BaseSchema, Schema, fields, validate, ValidationError
from .user import UserSchema, UserCreateSchema, UserUpdateSchema
from .auth import LoginSchema, TokenRefreshSchema, ChangePasswordSchema
from .resource import ResourceSchema, ResourceCreateSchema, ResourceUpdateSchema
from .academic import CourseSchema, CourseCreateSchema, CourseUpdateSchema, GradeSchema, GradeCreateSchema
from .approval import ApprovalSchema, ApprovalCreateSchema, ApprovalActionSchema
from .search import SearchQuerySchema
from .ai import AIChatRequestSchema, AIInsightRequestSchema
from .notification import NotificationSchema, NotificationCreateSchema
from .analytics import AnalyticsRequestSchema, AnalyticsResponseSchema
from .qr_code import QRCodeGenerateSchema, QRCodeScanSchema

__all__ = [
    "BaseSchema",
    "UserSchema", "UserCreateSchema", "UserUpdateSchema",
    "LoginSchema", "TokenRefreshSchema", "ChangePasswordSchema",
    "ResourceSchema", "ResourceCreateSchema", "ResourceUpdateSchema",
    "CourseSchema", "CourseCreateSchema", "CourseUpdateSchema", "GradeSchema", "GradeCreateSchema",
    "ApprovalSchema", "ApprovalCreateSchema", "ApprovalActionSchema",
    "SearchQuerySchema",
    "AIChatRequestSchema", "AIInsightRequestSchema",
    "NotificationSchema", "NotificationCreateSchema",
    "AnalyticsRequestSchema", "AnalyticsResponseSchema",
    "QRCodeGenerateSchema", "QRCodeScanSchema"
]
