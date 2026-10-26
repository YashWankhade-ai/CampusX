import os
import tempfile

def build_database_uri() -> str:
    """Build database URI from DATABASE_URL, local SQLite dev database, or PostgreSQL env vars."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    explicit_uri = os.environ.get("DATABASE_URL")
    if explicit_uri:
        if explicit_uri.startswith("sqlite:///"):
            path_part = explicit_uri[len("sqlite:///"):]
            path_part = path_part.replace("\\", "/")
            if not (len(path_part) >= 2 and path_part[1] == ":"):
                abs_path = os.path.join(base_dir, path_part).replace("\\", "/")
                return f"sqlite:///{abs_path}"
            return f"sqlite:///{path_part}"
        return explicit_uri

    # On Vercel serverless environment, use system temporary directory for SQLite
    if os.environ.get("VERCEL"):
        tmp_db = os.path.join(tempfile.gettempdir(), "campusx.db").replace("\\", "/")
        return f"sqlite:///{tmp_db}"

    sqlite_db = os.path.join(base_dir, "instance", "campusx_dev.db").replace("\\", "/")
    if os.path.exists(sqlite_db):
        return f"sqlite:///{sqlite_db}"

    user = os.environ.get("POSTGRES_USER", "campusx")
    password = os.environ.get("POSTGRES_PASSWORD", "campusx123")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db_name = os.environ.get("POSTGRES_DB", "campusx_dev")

    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

class Config:
    # Changed to have NO default in base config. Production will crash if missing (fail-secure).
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-campusx-2026-very-long-32-bytes")
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {} if build_database_uri().startswith("sqlite") else {
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "1800"))
    }
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    DEBUG = False
    TESTING = False

    # Upload / Storage configuration
    UPLOAD_DIR = os.environ.get('UPLOAD_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads'))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 100 * 1024 * 1024))  # 100 MB
    STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND', 'local')  # 'local' or 's3'
    S3_BUCKET = os.environ.get('S3_BUCKET', '')
    S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL', '')
    S3_REGION = os.environ.get('S3_REGION', 'us-east-1')

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    # 32+ byte string for dev
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-campusx-2026-very-long-32-bytes")
    SQLALCHEMY_DATABASE_URI = build_database_uri()

class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    # 32+ byte string for testing
    SECRET_KEY = "test-secret-key-campusx-2026-very-long-32-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    STORAGE_BACKEND = 'local'
    UPLOAD_DIR = os.path.join(tempfile.gettempdir(), 'campusx_test_uploads')
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    CELERY_BROKER_URL = "memory://"

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() in ("true", "1")
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PREFERRED_URL_SCHEME = "https"

config_by_name = {
    "dev": DevelopmentConfig,
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "prod": ProductionConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig
}
