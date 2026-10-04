"""Base vision context with single-decode scan resizing and lazy cached color spaces."""

from __future__ import annotations

from typing import Any, Optional
import cv2
import numpy as np

from core.models import Rect
from core.constants import DEFAULT_SCAN_MAX_DIMENSION


class VisionContext:
    """Provides single-decode scan resizing, lazy cached color-spaces and coordinate mapping."""

    REF_WIDTH = 2778.0
    REF_HEIGHT = 1284.0

    def __init__(
        self,
        original_bgr: np.ndarray,
        max_scan_dim: int = DEFAULT_SCAN_MAX_DIMENSION,
        source: Optional[Any] = None,
    ):
        if original_bgr is None or original_bgr.size == 0:
            raise ValueError("original_bgr cannot be None or empty.")

        self.original_bgr = original_bgr
        self.original_h, self.original_w = original_bgr.shape[:2]
        self.source = source
        self.max_scan_dim = max(400, max_scan_dim)

        # Scale down once if needed
        max_dim = max(self.original_w, self.original_h)
        if max_dim > self.max_scan_dim:
            self._resize_scale = float(self.max_scan_dim) / float(max_dim)
            sw = max(1, round(self.original_w * self._resize_scale))
            sh = max(1, round(self.original_h * self._resize_scale))
            self.scan_bgr: np.ndarray = cv2.resize(original_bgr, (sw, sh), interpolation=cv2.INTER_AREA)
        else:
            self._resize_scale = 1.0
            self.scan_bgr = original_bgr

        self.scan_h, self.scan_w = self.scan_bgr.shape[:2]
        self.scan_scale_x = float(self.scan_w) / float(self.original_w) if self.original_w > 0 else 1.0
        self.scan_scale_y = float(self.scan_h) / float(self.original_h) if self.original_h > 0 else 1.0
        self.scale_x = float(self.scan_w) / self.REF_WIDTH
        self.scale_y = float(self.scan_h) / self.REF_HEIGHT
        self.aspect_ratio = float(self.original_w) / float(self.original_h) if self.original_h > 0 else 0.0

        # Lazy caches
        self._gray: Optional[np.ndarray] = None
        self._hsv: Optional[np.ndarray] = None

    @property
    def gray(self) -> np.ndarray:
        if self._gray is None:
            self._gray = cv2.cvtColor(self.scan_bgr, cv2.COLOR_BGR2GRAY)
        return self._gray

    @property
    def hsv(self) -> np.ndarray:
        if self._hsv is None:
            self._hsv = cv2.cvtColor(self.scan_bgr, cv2.COLOR_BGR2HSV)
        return self._hsv

    def norm_rect(self, x1_ratio: float, y1_ratio: float, x2_ratio: float, y2_ratio: float) -> Rect:
        """Converts normalized ratios [0.0, 1.0] to clamped pixel Rect on scan image."""
        rx1 = max(0, min(self.scan_w, int(round(x1_ratio * self.scan_w))))
        ry1 = max(0, min(self.scan_h, int(round(y1_ratio * self.scan_h))))
        rx2 = max(rx1, min(self.scan_w, int(round(x2_ratio * self.scan_w))))
        ry2 = max(ry1, min(self.scan_h, int(round(y2_ratio * self.scan_h))))
        return Rect(rx1, ry1, rx2 - rx1, ry2 - ry1)

    def ref_rect(self, x1: float, y1: float, x2: float, y2: float) -> Rect:
        """Converts reference 2778x1284 coordinates to scan coordinates and clamps."""
        rx1 = max(0, min(self.scan_w, int(round(x1 * self.scale_x))))
        ry1 = max(0, min(self.scan_h, int(round(y1 * self.scale_y))))
        rx2 = max(rx1, min(self.scan_w, int(round(x2 * self.scale_x))))
        ry2 = max(ry1, min(self.scan_h, int(round(y2 * self.scale_y))))
        return Rect(rx1, ry1, rx2 - rx1, ry2 - ry1)

    def roi_bgr(self, rect: Rect) -> np.ndarray:
        """Extracts BGR slice safely using Rect bounds."""
        clamped = rect.clamp(self.scan_w, self.scan_h)
        return self.scan_bgr[clamped.y:clamped.bottom, clamped.x:clamped.right]

    def roi_gray(self, rect: Rect) -> np.ndarray:
        """Extracts Grayscale slice safely using Rect bounds."""
        clamped = rect.clamp(self.scan_w, self.scan_h)
        return self.gray[clamped.y:clamped.bottom, clamped.x:clamped.right]

    def roi_hsv(self, rect: Rect) -> np.ndarray:
        """Extracts HSV slice safely using Rect bounds."""
        clamped = rect.clamp(self.scan_w, self.scan_h)
        return self.hsv[clamped.y:clamped.bottom, clamped.x:clamped.right]

    def close(self) -> None:
        """Releases cached numpy arrays to prevent memory pressure."""
        self._gray = None
        self._hsv = None
