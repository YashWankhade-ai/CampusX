from .base import CampusXException

class AuthenticationError(CampusXException):
    def __init__(self, message="Authentication failed", payload=None):
        super().__init__(message, status_code=401, payload=payload)
