"""Rate limiter configuration for CampusX.

Uses Flask-Limiter with Redis as the storage backend when available.
Falls back to in-memory storage when Redis is unavailable — this ensures
tests and development environments work without a Redis instance.

AI endpoints get tighter per-user limits:
    /api/v1/ai/ask  — 30 per minute per user
    /api/v1/ai/chat — 30 per minute per user

Non-AI endpoints use the global default: 200/day, 50/hour.

Security:
    - Limits are per authenticated user JWT identity (key_func=_get_user_identity)
    - Falls back to remote address when no user identity is available
    - key_prefix is namespaced to avoid collisions with other Redis data
"""
import logging

logger = logging.getLogger(__name__)

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    from flask import request

    def _get_user_identity():
        """Rate limit key: authenticated user ID or remote IP as fallback."""
        try:
            # If request.user is set by @require_auth middleware, key on user ID
            if hasattr(request, "user") and request.user and hasattr(request.user, "id"):
                return f"user:{request.user.id}"
        except RuntimeError:
            pass
        return get_remote_address()

    def _make_limiter(storage_uri: str = "memory://"):
        """Create a Limiter instance with the given storage URI."""
        return Limiter(
            key_func=_get_user_identity,
            default_limits=["200 per day", "50 per hour"],
            storage_uri=storage_uri,
            key_prefix="campusx_rl",
            strategy="fixed-window",
        )

    # Module-level limiter — starts with in-memory storage.
    # init_rate_limiter() is called from create_app() and may reconfigure
    # to Redis if REDIS_URL is available.
    limiter = _make_limiter("memory://")

    def init_rate_limiter(app):
        """Bind the limiter to the Flask app.

        Tries to use Redis storage (from REDIS_URL env var).
        Silently falls back to in-memory storage if Redis is not available.
        This ensures test suites and dev environments work without Redis.
        """
        import os
        global limiter

        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            try:
                limiter = _make_limiter(redis_url)
                logger.info("Rate limiter: using Redis storage at %s", redis_url.split("@")[-1])
            except Exception as exc:
                logger.warning(
                    "Rate limiter: Redis unavailable (%s) — falling back to in-memory storage",
                    type(exc).__name__,
                )
                limiter = _make_limiter("memory://")
        else:
            logger.info("Rate limiter: REDIS_URL not set — using in-memory storage")
            limiter = _make_limiter("memory://")

        limiter.init_app(app)
        return limiter

    # Convenience decorators for AI endpoint rate limiting
    # 30 requests per minute per authenticated user
    AI_RATE_LIMIT = "30 per minute"

    FLASK_LIMITER_AVAILABLE = True

except ImportError:
    logger.debug("Flask-Limiter not installed — rate limiting disabled")
    FLASK_LIMITER_AVAILABLE = False
    AI_RATE_LIMIT = None

    class _NoOpLimiter:
        """No-op limiter used when Flask-Limiter is not installed."""
        def init_app(self, app):
            pass

        def limit(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator

        def exempt(self, f):
            return f

    limiter = _NoOpLimiter()

    def init_rate_limiter(app):
        return limiter
