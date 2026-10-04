"""Classification context inheriting base VisionContext with blue mask caching."""

from __future__ import annotations

from typing import Any, Optional
import cv2
import numpy as np

from core.constants import DEFAULT_SCAN_MAX_DIMENSION
from core.vision_context import VisionContext


class ClassificationContext(VisionContext):
    """Provides classification-specific blue indicator masks on top of VisionContext."""

    def __init__(
        self,
        original_bgr: np.ndarray,
        max_scan_dim: int = DEFAULT_SCAN_MAX_DIMENSION,
        source: Optional[Any] = None,
    ):
        super().__init__(original_bgr, max_scan_dim=max_scan_dim, source=source)
        self._strict_blue: Optional[np.ndarray] = None
        self._relaxed_blue: Optional[np.ndarray] = None

    @property
    def strict_blue_mask(self) -> np.ndarray:
        if self._strict_blue is None:
            self._strict_blue = cv2.inRange(
                self.hsv,
                np.array([100, 120, 120], dtype=np.uint8),
                np.array([130, 255, 255], dtype=np.uint8),
            )
        return self._strict_blue

    @property
    def relaxed_blue_mask(self) -> np.ndarray:
        if self._relaxed_blue is None:
            self._relaxed_blue = cv2.inRange(
                self.hsv,
                np.array([92, 65, 75], dtype=np.uint8),
                np.array([142, 255, 255], dtype=np.uint8),
            )
        return self._relaxed_blue

    def close(self) -> None:
        """Releases cached numpy arrays to prevent memory pressure."""
        super().close()
        self._strict_blue = None
        self._relaxed_blue = None

