from .base import CampusXException

class ValidationError(CampusXException):
    def __init__(self, message="Validation failed", payload=None):
        super().__init__(message, status_code=400, payload=payload)
