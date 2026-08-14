import os

def build_database_uri() -> str:
    """Build PostgreSQL URI from individual environment variables if DATABASE_URL is not set."""
    explicit_uri = os.environ.get("DATABASE_URL")
    if explicit_uri:
        return explicit_uri

    user = os.environ.get("POSTGRES_USER", "campusx")
    password = os.environ.get("POSTGRES_PASSWORD", "campusx123")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db_name = os.environ.get("POSTGRES_DB", "campusx_dev")

    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-campusx-2026")
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "1800"))
    }
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    DEBUG = False
    TESTING = False

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    SQLALCHEMY_DATABASE_URI = build_database_uri()

class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}

class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

config_by_name = {
    "dev": DevelopmentConfig,
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "prod": ProductionConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig
}
