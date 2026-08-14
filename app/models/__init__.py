from .base import BaseModel
from .academic import Institution
from .user import User, Role, UserRole, Profile, OTPCode

try:
    from .academic import Department, Degree, Program, AcademicSession, Semester, Subject, Unit, Topic
except (ImportError, AttributeError):
    pass

try:
    from .audit import AuditLog, LoginHistory
except (ImportError, AttributeError):
    pass

try:
    from .resource import StudyMaterial, MaterialVersion, FileMetadata, ResourceCategory, ResourceTag, ResourceTagAssociation, ResourceComment, ResourceRating
    Resource = StudyMaterial
    ResourceVersion = MaterialVersion
except (ImportError, AttributeError):
    pass

try:
    from .approval import ApprovalWorkflow, ApprovalStep, ApprovalRequest, ApprovalAction
except (ImportError, AttributeError):
    pass

try:
    from .ai_chat import ChatSession, ChatMessage, AICitation
except (ImportError, AttributeError):
    pass

try:
    from .analytics import EventLog, DailyMetric, ResourceView
except (ImportError, AttributeError):
    pass

try:
    from .notification import NotificationTemplate, Notification, UserDevice
except (ImportError, AttributeError):
    pass

try:
    from .contribution import ContributionType, UserContribution, Leaderboard
except (ImportError, AttributeError):
    pass

try:
    from .qr_code import QRCode, QRCodeScan
except (ImportError, AttributeError):
    pass

try:
    from .search import SearchQueryLog, SearchFilterLog
except (ImportError, AttributeError):
    pass

try:
    from .bookmark import BookmarkFolder, Bookmark
except (ImportError, AttributeError):
    pass

try:
    from .embedding import EmbeddingModelConfig, ResourceChunk, ChunkEmbedding
except (ImportError, AttributeError):
    pass

try:
    from .enrollment import AcademicYear, StudentEnrollment, CourseEnrollment, InstructorAssignment
except (ImportError, AttributeError):
    pass

# Aliases
University = Institution
College = Institution
