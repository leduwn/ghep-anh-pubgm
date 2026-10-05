"""Unit tests for OCR two-level caching (LRU + DiskCache), negative caching, and force bypass."""

import pytest

from core.models import Rect
from ocr.cache import OCRCache, build_ocr_cache_key
from ocr.models import OCRObservation


def test_build_ocr_cache_key_deterministic():
    key1 = build_ocr_cache_key("sha_abc", Rect(0, 10, 100, 50), route="gun_level")
    key2 = build_ocr_cache_key("sha_abc", Rect(0, 10, 100, 50), route="gun_level")
    assert key1 == key2

    # Different ROI yields different key
    key3 = build_ocr_cache_key("sha_abc", Rect(0, 20, 100, 50), route="gun_level")
    assert key1 != key3


def test_ocr_cache_memory_lru_eviction(tmp_path):
    cache = OCRCache(cache_dir=tmp_path / "cache", memory_capacity=2)
    obs1 = [OCRObservation(text="ONE", confidence=0.9)]
    obs2 = [OCRObservation(text="TWO", confidence=0.9)]
    obs3 = [OCRObservation(text="THREE", confidence=0.9)]

    cache.put("k1", obs1)
    cache.put("k2", obs2)
    assert len(cache.memory_cache) == 2

    # Accessing k1 makes it most recently used
    assert cache.get("k1")[0].text == "ONE"

    # Put k3: k2 should be evicted from memory cache
    cache.put("k3", obs3)
    assert len(cache.memory_cache) == 2
    assert "k1" in cache.memory_cache
    assert "k3" in cache.memory_cache
    assert "k2" not in cache.memory_cache

    # k2 is still available from disk cache!
    val2 = cache.get("k2")
    assert val2 is not None
    assert val2[0].text == "TWO"


def test_ocr_cache_negative_caching(tmp_path):
    """Verifies that empty observations (blank backgrounds) are cached and return []."""
    cache = OCRCache(cache_dir=tmp_path / "cache", memory_capacity=10)
    empty_obs = []

    cache.put("empty_key", empty_obs)
    res = cache.get("empty_key")
    assert res is not None
    assert len(res) == 0


def test_ocr_cache_force_bypasses_cache(tmp_path):
    cache = OCRCache(cache_dir=tmp_path / "cache", memory_capacity=10)
    cache.put("key_f", [OCRObservation(text="FOUND", confidence=1.0)])

    # Normal fetch returns value
    assert cache.get("key_f", force=False) is not None

    # Force=True bypasses and returns None
    assert cache.get("key_f", force=True) is None
