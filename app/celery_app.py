"""Celery application entrypoint for worker and beat tasks."""
from app.tasks.celery_app import celery

__all__ = ["celery"]
