import os

class DummyConf(dict):
    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)

try:
    from celery import Celery
except ImportError:
    class Celery:
        def __init__(self, *args, **kwargs):
            self.conf = DummyConf()
        def task(self, *args, **kwargs):
            def decorator(f):
                f.delay = f
                return f
            return decorator

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
celery = Celery("campusx_tasks", broker=redis_url, backend=redis_url)
if hasattr(celery, "conf") and hasattr(celery.conf, "update"):
    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True
    )
