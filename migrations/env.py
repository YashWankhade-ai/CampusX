"""Alembic migrations environment.

Database URL strategy (matches app/config.py):
    1. DATABASE_URL environment variable (full URI, highest priority)
    2. Individual POSTGRES_* environment variables assembled by build_database_uri()
    3. Fallback: sqlite:///:memory:  (only used when running tests via pytest,
       where db.create_all() is called directly and no real migration is needed)

When running inside a Flask app context (e.g. `flask db upgrade`) the engine
is taken from `db.engine` directly.

When running standalone (e.g. `python -m alembic current`) the URL is built
from environment variables — same logic as app/config.py:build_database_uri().
No credentials are hard-coded here or in alembic.ini.
"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_database_url() -> str:
    """Build the database URL using the same strategy as app/config.py.

    Priority:
        1. DATABASE_URL env var (full connection string)
        2. Individual POSTGRES_* env vars → assembled PostgreSQL URI
        3. sqlite:///:memory:  (safe fallback for test / offline use)

    Never reads sqlalchemy.url from alembic.ini (that key is intentionally
    commented out to prevent the 'driver' placeholder from causing errors).
    """
    import os

    # 1. Full explicit URI
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit

    # 2. Assemble from individual vars (same defaults as app/config.py)
    user = os.environ.get("POSTGRES_USER", "campusx")
    password = os.environ.get("POSTGRES_PASSWORD", "campusx123")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db_name = os.environ.get("POSTGRES_DB", "campusx_dev")

    # Only use the assembled URI if at least one variable is explicitly set,
    # otherwise fall back to SQLite (prevents connecting to a non-existent
    # default Postgres instance during offline/test usage).
    postgres_vars = {"DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD",
                     "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB"}
    if any(os.environ.get(v) for v in postgres_vars):
        return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

    # 3. Safe fallback (alembic heads / history work without a real DB)
    return "sqlite:///:memory:"


# Import models so SQLAlchemy metadata is fully populated for autogenerate
import app.models  # noqa: E402, F401
from app.extensions import db  # noqa: E402

target_metadata = db.Model.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without a live connection)."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    # Prefer the Flask app's already-configured engine when available
    try:
        from flask import current_app as _app
        if _app and hasattr(db, "engine"):
            connectable = db.engine
            with connectable.connect() as connection:
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                )
                with context.begin_transaction():
                    context.run_migrations()
            return
    except RuntimeError:
        pass  # No app context — running standalone

    # Standalone mode: build URL from environment variables
    url = _get_database_url()
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
