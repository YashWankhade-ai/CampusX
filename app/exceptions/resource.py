from .base import CampusXException

class ResourceNotFoundError(CampusXException):
    def __init__(self, message="Resource not found", payload=None):
        super().__init__(message, status_code=404, payload=payload)
