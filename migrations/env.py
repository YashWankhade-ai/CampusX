from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from flask import current_app
from app.extensions import db
import app.models  # Ensure all models are registered

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = db.Model.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if not url or url.startswith("%"):
        if current_app:
            url = current_app.config.get("SQLALCHEMY_DATABASE_URI")
        else:
            url = "sqlite:///:memory:"

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    if current_app and hasattr(db, "engine"):
        connectable = db.engine
    else:
        cfg = config.get_section(config.config_ini_section, {})
        url = cfg.get("sqlalchemy.url")
        if not url or url.startswith("%"):
            cfg["sqlalchemy.url"] = "sqlite:///:memory:"
        connectable = engine_from_config(
            cfg,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
