try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="redis://localhost:6379"
    )

    def init_rate_limiter(app):
        limiter.init_app(app)
        return limiter
except ImportError:
    class DummyLimiter:
        def init_app(self, app): pass
        def limit(self, *args, **kwargs):
            def decorator(f): return f
            return decorator

    limiter = DummyLimiter()

    def init_rate_limiter(app):
        return limiter
