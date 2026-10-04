"""In-memory LRU and disk-based caching subsystems for Auto-Cut-Next."""

from __future__ import annotations

import collections
import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar, Union

from .models import Rect
from .constants import DEFAULT_LRU_CACHE_CAPACITY

K = TypeVar("K")
V = TypeVar("V")


class CacheKeyGenerator:
    """Computes deterministic SHA-256 cache keys incorporating image, crop and subsystem version."""

    @staticmethod
    def generate(
        image_sha256: str,
        crop_rect: Optional[Rect] = None,
        subsystem_version: str = "1.0.0",
        route: str = "generic",
    ) -> str:
        rect_str = f"{crop_rect.x}:{crop_rect.y}:{crop_rect.w}:{crop_rect.h}" if crop_rect else "full"
        token = f"{image_sha256}:{rect_str}:{subsystem_version}:{route}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LRUCache(Generic[K, V]):
    """Thread-safe in-memory Least-Recently-Used (LRU) cache with bounded capacity."""

    def __init__(self, capacity: int = DEFAULT_LRU_CACHE_CAPACITY):
        if capacity <= 0:
            raise ValueError(f"Cache capacity must be positive, got {capacity}")
        self.capacity = capacity
        self._store: collections.OrderedDict[K, V] = collections.OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> Optional[V]:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._hits += 1
                return self._store[key]
            self._misses += 1
            return None

    def put(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            if len(self._store) > self.capacity:
                self._store.popitem(last=False)

    def evict(self, key: K) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self._store

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_ratio = (self._hits / total) if total > 0 else 0.0
            return {
                "size": len(self._store),
                "capacity": self.capacity,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": hit_ratio,
            }


class DiskCache:
    """Atomic file-based disk cache for persistent results."""

    def __init__(self, cache_dir: Union[str, Path]):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path_for_key(self, key: str) -> Path:
        safe_key = hashlib.sha256(key.encode("utf-8")).hexdigest()
        # Subdirectory sharding by first 2 chars
        shard = safe_key[:2]
        shard_dir = self.cache_dir / shard
        shard_dir.mkdir(parents=True, exist_ok=True)
        return shard_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[dict[str, Any]]:
        target = self._path_for_key(key)
        with self._lock:
            if not target.is_file():
                return None
            try:
                with open(target, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None

    def put(self, key: str, data: dict[str, Any]) -> None:
        target = self._path_for_key(key)
        temp_file = target.with_suffix(".tmp")
        with self._lock:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
            temp_file.replace(target)

    def delete(self, key: str) -> bool:
        target = self._path_for_key(key)
        with self._lock:
            if target.is_file():
                target.unlink(missing_ok=True)
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            for item in self.cache_dir.rglob("*.json"):
                try:
                    item.unlink()
                except Exception:
                    pass
