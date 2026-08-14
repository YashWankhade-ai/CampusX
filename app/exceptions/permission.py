from .base import CampusXException

class PermissionDeniedError(CampusXException):
    def __init__(self, message="Permission denied", payload=None):
        super().__init__(message, status_code=403, payload=payload)
