import os
import time
import logging

logger = logging.getLogger(__name__)

class InMemoryRedis:
    """
    In-memory Redis fallback store with TTL expiration.
    Used when production Redis server is not running or during unit testing.
    """
    def __init__(self):
        self._store = {}

    def set(self, name: str, value: str, ex: int = 600) -> bool:
        expires_at = time.time() + ex
        self._store[name] = (value, expires_at)
        return True

    def get(self, name: str) -> str | None:
        if name not in self._store:
            return None
        value, expires_at = self._store[name]
        if time.time() > expires_at:
            del self._store[name]
            return None
        return value

    def delete(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self._store:
                del self._store[name]
                count += 1
        return count

_in_memory_redis = InMemoryRedis()

def get_redis_client():
    try:
        from flask import current_app
        if current_app and current_app.config.get("TESTING"):
            return _in_memory_redis
    except Exception:
        pass

    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            r = redis.Redis.from_url(redis_url, socket_connect_timeout=0.5, socket_timeout=0.5, decode_responses=True)
            r.ping()
            return r
        except Exception:
            pass
    return _in_memory_redis
