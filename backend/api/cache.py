"""Simple LRU + TTL cache wrapper for assessment responses."""

from __future__ import annotations

import threading
from typing import Callable, Generic, Optional, TypeVar

from cachetools import TTLCache

K = TypeVar("K")
V = TypeVar("V")


class AssessmentCache(Generic[K, V]):
    """Thread-safe TTL cache with LRU eviction semantics."""

    def __init__(self, maxsize: int = 64, ttl_seconds: int = 900) -> None:
        self._cache: TTLCache[K, V] = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._lock = threading.Lock()

    def get(self, key: K) -> Optional[V]:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._cache[key] = value

    def get_or_set(self, key: K, factory: Callable[[], V]) -> V:
        with self._lock:
            value = self._cache.get(key)
            if value is not None:
                return value
        value = factory()
        with self._lock:
            self._cache[key] = value
        return value

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
