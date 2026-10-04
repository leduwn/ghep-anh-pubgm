"""Unit tests for memory and disk caching."""

import threading
from pathlib import Path
from core.cache import LRUCache, DiskCache, CacheKeyGenerator
from core.models import Rect


def test_cache_key_generator():
    rect1 = Rect(10, 20, 100, 50)
    rect2 = Rect(10, 20, 100, 50)
    rect3 = Rect(10, 20, 101, 50)

    key1 = CacheKeyGenerator.generate("sha_test", rect1, "1.0", "ocr")
    key2 = CacheKeyGenerator.generate("sha_test", rect2, "1.0", "ocr")
    key3 = CacheKeyGenerator.generate("sha_test", rect3, "1.0", "ocr")

    assert key1 == key2
    assert key1 != key3


def test_lru_cache_capacity_and_eviction():
    cache = LRUCache[str, int](capacity=3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)

    assert len(cache) == 3
    assert cache.get("a") == 1  # accesses 'a', makes 'b' oldest

    cache.put("d", 4)  # should evict 'b'
    assert len(cache) == 3
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("d") == 4


def test_lru_cache_stats():
    cache = LRUCache[str, str](capacity=5)
    cache.put("k1", "v1")
    _ = cache.get("k1")  # hit
    _ = cache.get("k2")  # miss

    stats = cache.stats
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_ratio"] == 0.5


def test_lru_cache_thread_safety():
    cache = LRUCache[int, int](capacity=100)

    def worker(offset: int):
        for i in range(100):
            val = offset + i
            cache.put(val, val)
            _ = cache.get(val)

    threads = [threading.Thread(target=worker, args=(i * 1000,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(cache) <= 100


def test_disk_cache(tmp_path):
    cache_dir = tmp_path / "disk_cache"
    disk = DiskCache(cache_dir)

    payload = {"status": "ok", "items": [1, 2, 3]}
    disk.put("test_key", payload)

    retrieved = disk.get("test_key")
    assert retrieved == payload

    assert disk.get("missing_key") is None
    assert disk.delete("test_key") is True
    assert disk.get("test_key") is None
