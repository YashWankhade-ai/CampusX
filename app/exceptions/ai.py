from .base import CampusXException

class AIProcessingError(CampusXException):
    def __init__(self, message="AI processing failed", payload=None):
        super().__init__(message, status_code=500, payload=payload)
