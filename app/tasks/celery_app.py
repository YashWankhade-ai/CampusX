import os
import logging

logger = logging.getLogger(__name__)


class DummyConf(dict):
    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)


try:
    from celery import Celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

    class _StubTaskSelf:
        """Minimal stub of a bound Celery task (self) for test invocations.

        Provides .retry() and .MaxRetriesExceededError so tasks with
        bind=True can be called directly without a Celery worker.
        """
        class MaxRetriesExceededError(Exception):
            pass

        def retry(self, exc=None, countdown=None, **kwargs):
            """In stub mode, just raise MaxRetriesExceededError immediately."""
            raise _StubTaskSelf.MaxRetriesExceededError("Stub: no retries in test mode")

    class Celery:
        def __init__(self, *args, **kwargs):
            self.conf = DummyConf()

        def task(self, *args, **kwargs):
            """Stub @celery.task decorator.

            If bind=True, wraps the function so the stub self is injected
            when called directly (without a Celery broker), and sets
            f.delay = wrapper for compatibility with dispatch calls.
            """
            bind = kwargs.get("bind", False)

            def decorator(f):
                if bind:
                    def wrapper(*call_args, **call_kwargs):
                        # Inject stub self as first positional argument
                        stub_self = _StubTaskSelf()
                        return f(stub_self, *call_args, **call_kwargs)
                    wrapper.__name__ = f.__name__
                    wrapper.__doc__ = f.__doc__
                    wrapper.delay = wrapper   # .delay() in stub = direct call
                    return wrapper
                else:
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
        enable_utc=True,
    )
