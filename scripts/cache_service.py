"""
AI-CON Production Cache Service (Phase 3: Production Scaling).
Provides unified caching for cutoff queries, candidate shortlists, and student session profiles.
Supports Redis when running, with automatic thread-safe in-memory LRU+TTL fallback.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("aicon.cache_service")


class _MemoryCache:
    """Thread-safe in-memory cache with Time-To-Live (TTL) expiration."""

    def __init__(self, maxsize: int = 2000):
        self._maxsize = maxsize
        self._store: Dict[str, Tuple[float, Any]] = {}  # key -> (expires_at, value)
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at, val = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            return val

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        with self._lock:
            # Simple eviction if exceeding maxsize
            if len(self._store) >= self._maxsize and key not in self._store:
                # Remove oldest 10%
                keys_to_remove = sorted(self._store.keys(), key=lambda k: self._store[k][0])[:max(1, self._maxsize // 10)]
                for k in keys_to_remove:
                    self._store.pop(k, None)
            self._store[key] = (time.time() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class CacheService:
    """
    High-performance caching layer.
    Connects to Redis if available; otherwise uses thread-safe memory cache.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        self._redis_client: Optional[Any] = None
        self._memory_cache = _MemoryCache()
        self.backend = "memory"
        self._init_redis()

    def _init_redis(self) -> None:
        try:
            import redis
            client = redis.Redis.from_url(
                self.redis_url,
                socket_connect_timeout=0.4,
                socket_timeout=0.4,
                decode_responses=True,
            )
            # Test ping
            client.ping()
            self._redis_client = client
            self.backend = "redis"
            logger.info("CacheService: connected to Redis at %s", self.redis_url)
        except Exception as exc:
            self._redis_client = None
            self.backend = "memory"
            logger.info("CacheService: Redis not available (%s); operating with high-speed in-memory cache.", exc)

    def get(self, key: str) -> Optional[Any]:
        if self._redis_client:
            try:
                raw = self._redis_client.get(key)
                if raw is not None:
                    return json.loads(raw)
            except Exception:
                pass
        return self._memory_cache.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        if self._redis_client:
            try:
                raw = json.dumps(value, ensure_ascii=False)
                self._redis_client.setex(key, ttl_seconds, raw)
                return
            except Exception:
                pass
        self._memory_cache.set(key, value, ttl_seconds=ttl_seconds)

    def delete(self, key: str) -> None:
        if self._redis_client:
            try:
                self._redis_client.delete(key)
            except Exception:
                pass
        self._memory_cache.delete(key)

    # Convenience domain helpers
    def cache_cutoff(self, code: str, branch: str, category: str, data: Any, ttl: int = 7200) -> None:
        key = f"cutoff:{code}:{branch.lower()}:{category.upper()}"
        self.set(key, data, ttl_seconds=ttl)

    def get_cached_cutoff(self, code: str, branch: str, category: str) -> Optional[Any]:
        key = f"cutoff:{code}:{branch.lower()}:{category.upper()}"
        return self.get(key)

    def cache_session(self, session_id: str, data: Any, ttl: int = 86400) -> None:
        key = f"session:{session_id}"
        self.set(key, data, ttl_seconds=ttl)

    def get_cached_session(self, session_id: str) -> Optional[Any]:
        key = f"session:{session_id}"
        return self.get(key)


_GLOBAL_CACHE: Optional[CacheService] = None
_CACHE_LOCK = threading.Lock()


def get_cache_service() -> CacheService:
    global _GLOBAL_CACHE
    with _CACHE_LOCK:
        if _GLOBAL_CACHE is None:
            _GLOBAL_CACHE = CacheService()
        return _GLOBAL_CACHE
