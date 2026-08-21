import os
import hashlib
import secrets
from werkzeug.utils import secure_filename
import uuid

# Architecture-approved formats
ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
    'txt', 'md', 'csv',
    'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp',
    'mp4', 'webm', 'mp3', 'wav'
}

# Extension -> MIME type mapping for validation
MIME_TYPE_MAP = {
    'pdf': 'application/pdf',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'ppt': 'application/vnd.ms-powerpoint',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'txt': 'text/plain',
    'md': 'text/markdown',
    'csv': 'text/csv',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'svg': 'image/svg+xml',
    'webp': 'image/webp',
    'mp4': 'video/mp4',
    'webm': 'video/webm',
    'mp3': 'audio/mpeg',
    'wav': 'audio/wav',
}

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

DANGEROUS_EXTENSIONS = {
    'exe', 'bat', 'cmd', 'sh', 'ps1', 'vbs', 'js',
    'msi', 'dll', 'com', 'scr', 'pif', 'php', 'py', 'rb',
    'jar', 'war', 'class', 'cgi', 'pl', 'asp', 'aspx',
    'htaccess', 'htpasswd', 'env'
}

def get_extension(filename: str) -> str:
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()

def validate_filename(filename: str) -> tuple[bool, str]:
    if not filename:
        return False, "Filename cannot be empty"
    
    if '..' in filename or '/' in filename or '\\' in filename:
        return False, "Invalid filename: Path traversal detected"
        
    if '\0' in filename:
        return False, "Invalid filename: Null bytes detected"
        
    ext = get_extension(filename)
    if not ext:
        return False, "Invalid filename: Missing extension"
        
    if ext in DANGEROUS_EXTENSIONS:
        return False, f"Invalid filename: Extension .{ext} is dangerous"
        
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid filename: Extension .{ext} is not allowed"
        
    return True, ""

def validate_file_size(file_size: int) -> tuple[bool, str]:
    if file_size <= 0:
        return False, "File size must be greater than 0"
    if file_size > MAX_FILE_SIZE:
        return False, f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024 * 1024)}MB"
    return True, ""

def validate_mime_type(filename: str, content_type: str) -> tuple[bool, str]:
    ext = get_extension(filename)
    expected_mime = MIME_TYPE_MAP.get(ext)
    
    if content_type == 'application/octet-stream':
        return True, ""
        
    if expected_mime and content_type != expected_mime:
        return False, f"MIME type mismatch: Expected {expected_mime} but got {content_type}"
        
    return True, ""

def validate_file(filename: str, file_size: int, content_type: str) -> tuple[bool, list[str]]:
    all_valid = True
    errors = []
    
    valid, msg = validate_filename(filename)
    if not valid:
        all_valid = False
        errors.append(msg)
        
    valid, msg = validate_file_size(file_size)
    if not valid:
        all_valid = False
        errors.append(msg)
        
    valid, msg = validate_mime_type(filename, content_type)
    if not valid:
        all_valid = False
        errors.append(msg)
        
    return all_valid, errors

def generate_safe_storage_key(institution_id: str, original_filename: str) -> str:
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    year = now.strftime("%Y")
    month = now.strftime("%m")
    
    ext = get_extension(original_filename)
    basename = original_filename.rsplit('.', 1)[0]
    safe_basename = secure_filename(basename)
    
    if not safe_basename:
        safe_basename = "file"
        
    uuid_prefix = secrets.token_hex(16)
    
    return f"{institution_id}/{year}/{month}/{uuid_prefix}_{safe_basename}.{ext}"

def calculate_checksum(file_data) -> str:
    sha256 = hashlib.sha256()
    # Support both werkzeug FileStorage and normal file objects
    file_data.seek(0)
    while True:
        chunk = file_data.read(8192)
        if not chunk:
            break
        sha256.update(chunk)
    file_data.seek(0)
    return sha256.hexdigest()
