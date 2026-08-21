import pytest
import uuid
import io
import os
import tempfile
from flask import json
from app.utils.token import generate_access_token
from app.utils.file_validator import (
    validate_filename, validate_file_size, validate_mime_type,
    generate_safe_storage_key, calculate_checksum, validate_file,
    ALLOWED_EXTENSIONS, DANGEROUS_EXTENSIONS, MAX_FILE_SIZE
)
from app.services.storage_service import LocalStorageBackend
from unittest.mock import patch, MagicMock

class MockUploadUser:
    def __init__(self, role='FACULTY'):
        self.id = str(uuid.uuid4())
        self.role = role
        self.institution_id = str(uuid.uuid4())
        self.email = 'faculty@test.edu'

def get_upload_token(app, role='FACULTY', institution_id=None):
    with app.app_context():
        user = MockUploadUser(role=role)
        if institution_id:
            user.institution_id = institution_id
        return generate_access_token(user), user

def test_successful_upload(client, app):
    token, user = get_upload_token(app, role='FACULTY')
    data = {
        'file': (io.BytesIO(b'%PDF-1.4 test content'), 'lecture.pdf', 'application/pdf'),
        'title': 'Test Lecture',
        'description': 'A test upload',
        'resource_type': 'NOTE'
    }
    response = client.post(
        '/api/v1/resources/upload',
        data=data,
        content_type='multipart/form-data',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 201
    res_data = response.json['data']
    assert res_data['title'] == 'Test Lecture'
    assert res_data['resource_type'] == 'NOTE'

def test_unauthenticated_upload_rejected(client):
    data = {
        'file': (io.BytesIO(b'%PDF-1.4 test content'), 'lecture.pdf', 'application/pdf'),
        'title': 'Test Lecture'
    }
    response = client.post(
        '/api/v1/resources/upload',
        data=data,
        content_type='multipart/form-data'
    )
    assert response.status_code == 401

def test_student_upload_rejected(client, app):
    token, user = get_upload_token(app, role='STUDENT')
    data = {
        'file': (io.BytesIO(b'%PDF-1.4 test content'), 'lecture.pdf', 'application/pdf'),
        'title': 'Test Lecture'
    }
    response = client.post(
        '/api/v1/resources/upload',
        data=data,
        content_type='multipart/form-data',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 403

def test_missing_file_rejected(client, app):
    token, user = get_upload_token(app, role='FACULTY')
    data = {
        'title': 'Test Lecture'
    }
    response = client.post(
        '/api/v1/resources/upload',
        data=data,
        content_type='multipart/form-data',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 400
    assert "File is required" in response.json['error']['message']

def test_unsupported_extension_rejected(client, app):
    token, user = get_upload_token(app, role='FACULTY')
    data = {
        'file': (io.BytesIO(b'MZ...'), 'virus.exe', 'application/x-msdownload'),
        'title': 'Test Lecture'
    }
    response = client.post(
        '/api/v1/resources/upload',
        data=data,
        content_type='multipart/form-data',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 400
    assert "is dangerous" in response.json['error']['message'] or "not allowed" in response.json['error']['message']

def test_dangerous_filename_rejected(client, app):
    token, user = get_upload_token(app, role='FACULTY')
    data = {
        'file': (io.BytesIO(b'content'), '../etc/passwd.pdf', 'application/pdf'),
        'title': 'Test Lecture'
    }
    response = client.post(
        '/api/v1/resources/upload',
        data=data,
        content_type='multipart/form-data',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 400
    assert "Path traversal" in response.json['error']['message']

def test_oversized_file_rejected(client, app):
    token, user = get_upload_token(app, role='FACULTY')
    # Since we can't easily mock file size checking without large memory,
    # let's mock the validator.
    with patch('app.utils.file_validator.validate_file_size') as mock_size:
        mock_size.return_value = (False, "File size exceeds maximum allowed size")
        data = {
            'file': (io.BytesIO(b'%PDF-1.4'), 'lecture.pdf', 'application/pdf'),
            'title': 'Test Lecture'
        }
        response = client.post(
            '/api/v1/resources/upload',
            data=data,
            content_type='multipart/form-data',
            headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 400
        assert "File size exceeds" in response.json['error']['message']

def test_empty_file_rejected(client, app):
    token, user = get_upload_token(app, role='FACULTY')
    data = {
        'file': (io.BytesIO(b''), 'lecture.pdf', 'application/pdf'),
        'title': 'Test Lecture'
    }
    response = client.post(
        '/api/v1/resources/upload',
        data=data,
        content_type='multipart/form-data',
        headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 400
    assert "greater than 0" in response.json['error']['message']

def test_safe_storage_key_generated():
    inst_id = str(uuid.uuid4())
    key = generate_safe_storage_key(inst_id, "my_file (1).pdf")
    assert key.startswith(f"{inst_id}/")
    assert key.endswith("_my_file_1.pdf")
    assert len(key.split('/')) == 4 # inst/year/month/file

def test_checksum_calculation():
    f = io.BytesIO(b"hello world")
    # echo -n "hello world" | sha256sum -> b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
    chk = calculate_checksum(f)
    assert chk == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert f.tell() == 0

def test_validate_filename_path_traversal():
    valid, msg = validate_filename("../../etc/passwd.pdf")
    assert not valid
    assert "Path traversal" in msg

def test_validate_filename_null_byte():
    valid, msg = validate_filename("file.pdf\x00.exe")
    assert not valid
    assert "Null bytes" in msg

def test_validate_mime_type_mismatch():
    valid, msg = validate_mime_type("image.png", "application/pdf")
    assert not valid
    assert "MIME type mismatch" in msg

def test_validate_mime_type_octet_stream_allowed():
    valid, msg = validate_mime_type("file.pdf", "application/octet-stream")
    assert valid

def test_local_storage_save_and_get(app):
    with app.app_context():
        backend = LocalStorageBackend()
        key = "test_inst/2026/08/test.txt"
        f = io.BytesIO(b"content")
        backend.save(f, key)
        
        assert backend.exists(key)
        
        f2 = backend.get(key)
        assert f2.read() == b"content"
        f2.close()

def test_local_storage_delete(app):
    with app.app_context():
        backend = LocalStorageBackend()
        key = "test_inst/2026/08/test_del.txt"
        f = io.BytesIO(b"content")
        backend.save(f, key)
        
        assert backend.exists(key)
        backend.delete(key)
        assert not backend.exists(key)
