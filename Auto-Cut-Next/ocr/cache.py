"""Two-level caching subsystem for OCR observations (Memory LRU + DiskCache)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Optional, Union

from core.cache import DiskCache, LRUCache
from core.constants import DEFAULT_OCR_CACHE_SIZE, OCR_VERSION
from core.models import Rect
from .models import OCRObservation

logger = logging.getLogger("auto_cut.ocr.cache")


def build_ocr_cache_key(
    source_sha256: str,
    roi: Optional[Rect] = None,
    route: str = "ocr",
    preprocess_profile: str = "raw",
) -> str:
    """Builds a deterministic composite cache key incorporating source hash, OCR version, and ROI."""
    roi_str = f"{roi.x}_{roi.y}_{roi.w}_{roi.h}" if roi else "full"
    token = f"{source_sha256}:{OCR_VERSION}:{route}:{roi_str}:{preprocess_profile}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class OCRCache:
    """Manages two-level caching for raw OCR observations with negative caching support."""

    def __init__(
        self,
        cache_dir: Union[str, Path],
        memory_capacity: int = DEFAULT_OCR_CACHE_SIZE,
    ):
        self.memory_cache: LRUCache[str, list[OCRObservation]] = LRUCache(capacity=memory_capacity)
        self.disk_cache: DiskCache = DiskCache(cache_dir=cache_dir)
        self._disk_hits: int = 0
        self._memory_hits: int = 0
        self._misses: int = 0

    def get(self, key: str, force: bool = False) -> Optional[list[OCRObservation]]:
        """Retrieves cached observations if present and force=False.

        Returns None on cache miss or when force=True.
        """
        if force:
            return None

        # Level 1: In-memory LRU
        mem_val = self.memory_cache.get(key)
        if mem_val is not None:
            self._memory_hits += 1
            return [
                OCRObservation(text=o.text, box=o.box, confidence=o.confidence)
                for o in mem_val
            ]

        # Level 2: Persistent Disk Cache
        try:
            disk_val = self.disk_cache.get(key)
            if disk_val is not None and "observations" in disk_val:
                self._disk_hits += 1
                observations = [
                    OCRObservation.from_dict(item)
                    for item in disk_val["observations"]
                ]
                # Populate Memory LRU
                self.memory_cache.put(key, observations)
                return observations
        except Exception as exc:
            logger.warning(f"Error reading OCR cache for key {key}: {exc}")

        self._misses += 1
        return None

    def put(self, key: str, observations: list[OCRObservation]) -> None:
        """Stores observations into memory and disk cache. Supports negative caching of empty observations."""
        try:
            # Level 1: Memory
            self.memory_cache.put(key, observations)

            # Level 2: Disk
            payload = {
                "version": OCR_VERSION,
                "observations": [o.to_dict() for o in observations],
                "count": len(observations),
            }
            self.disk_cache.put(key, payload)
        except Exception as exc:
            logger.warning(f"Failed to write OCR cache for key {key}: {exc}")

    def clear(self) -> None:
        self.memory_cache.clear()

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "memory_hits": self._memory_hits,
            "disk_hits": self._disk_hits,
            "misses": self._misses,
            "total_hits": self._memory_hits + self._disk_hits,
            "memory_cache_size": len(self.memory_cache),
        }
