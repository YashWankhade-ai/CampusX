import os

def write_file(filepath, content):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        f.write(content.strip() + '\n')

BASE_DIR = r"C:\Users\ASUS\.gemini\antigravity\scratch\campusx"

# 1. Exceptions
exceptions_base = """
class CampusXException(Exception):
    def __init__(self, message, status_code=500, payload=None):
        Exception.__init__(self)
        self.message = message
        self.status_code = status_code
        self.payload = payload
        
    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv
"""
exceptions_auth = """
from .base import CampusXException

class AuthenticationError(CampusXException):
    def __init__(self, message="Authentication failed", payload=None):
        super().__init__(message, status_code=401, payload=payload)
"""
exceptions_resource = """
from .base import CampusXException

class ResourceNotFoundError(CampusXException):
    def __init__(self, message="Resource not found", payload=None):
        super().__init__(message, status_code=404, payload=payload)
"""
exceptions_permission = """
from .base import CampusXException

class PermissionDeniedError(CampusXException):
    def __init__(self, message="Permission denied", payload=None):
        super().__init__(message, status_code=403, payload=payload)
"""
exceptions_ai = """
from .base import CampusXException

class AIProcessingError(CampusXException):
    def __init__(self, message="AI processing failed", payload=None):
        super().__init__(message, status_code=500, payload=payload)
"""
exceptions_validation = """
from .base import CampusXException

class ValidationError(CampusXException):
    def __init__(self, message="Validation failed", payload=None):
        super().__init__(message, status_code=400, payload=payload)
"""

write_file(f"{BASE_DIR}/app/exceptions/base.py", exceptions_base)
write_file(f"{BASE_DIR}/app/exceptions/auth.py", exceptions_auth)
write_file(f"{BASE_DIR}/app/exceptions/resource.py", exceptions_resource)
write_file(f"{BASE_DIR}/app/exceptions/permission.py", exceptions_permission)
write_file(f"{BASE_DIR}/app/exceptions/ai.py", exceptions_ai)
write_file(f"{BASE_DIR}/app/exceptions/validation.py", exceptions_validation)
write_file(f"{BASE_DIR}/app/exceptions/__init__.py", "")

# 9. Utils (response utils for envelope)
utils_response = """
from flask import jsonify

def success_response(data=None, meta=None, message="Success", status_code=200, request_id=None):
    response = {
        "success": True,
        "message": message,
        "data": data if data is not None else {},
        "meta": meta if meta is not None else {},
        "error": None,
        "request_id": request_id
    }
    return jsonify(response), status_code

def error_response(message="Error", error_details=None, status_code=400, request_id=None):
    response = {
        "success": False,
        "message": message,
        "data": None,
        "meta": None,
        "error": error_details if error_details is not None else {},
        "request_id": request_id
    }
    return jsonify(response), status_code
"""
write_file(f"{BASE_DIR}/app/utils/response_utils.py", utils_response)
write_file(f"{BASE_DIR}/app/utils/hashing.py", "def hash_password(pwd): return pwd\ndef verify_password(pwd, hash): return pwd == hash")
write_file(f"{BASE_DIR}/app/utils/pagination.py", "def paginate(query, page, per_page): return query.paginate(page=page, per_page=per_page)")
write_file(f"{BASE_DIR}/app/utils/datetime_utils.py", "import datetime\ndef now(): return datetime.datetime.utcnow()")
write_file(f"{BASE_DIR}/app/utils/string_utils.py", "def camel_to_snake(name): return name")
write_file(f"{BASE_DIR}/app/utils/file_utils.py", "def save_file(f, path): pass")
write_file(f"{BASE_DIR}/app/utils/crypto_utils.py", "def encrypt(data): return data\ndef decrypt(data): return data")
write_file(f"{BASE_DIR}/app/utils/__init__.py", "")

# 3. Repositories
repositories_base = """
from sqlalchemy import select
from app.extensions import db

class BaseRepository:
    def __init__(self, model):
        self.model = model

    def get_by_id(self, id):
        stmt = select(self.model).where(self.model.id == id)
        return db.session.execute(stmt).scalar_one_or_none()

    def get_all(self):
        stmt = select(self.model)
        return db.session.execute(stmt).scalars().all()

    def create(self, **kwargs):
        instance = self.model(**kwargs)
        db.session.add(instance)
        db.session.commit()
        return instance

    def update(self, instance, **kwargs):
        for key, value in kwargs.items():
            setattr(instance, key, value)
        db.session.commit()
        return instance

    def delete(self, instance):
        db.session.delete(instance)
        db.session.commit()
"""
write_file(f"{BASE_DIR}/app/repositories/base_repository.py", repositories_base)

repos = ['user', 'resource', 'academic', 'approval', 'chat', 'analytics', 'notification', 'search', 'audit']
for repo in repos:
    content = f"from .base_repository import BaseRepository\n\nclass {repo.capitalize()}Repository(BaseRepository):\n    pass\n"
    write_file(f"{BASE_DIR}/app/repositories/{repo}_repository.py", content)
write_file(f"{BASE_DIR}/app/repositories/__init__.py", "")

print("Phase 3 script completed part 1.")
