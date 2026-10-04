"""Detection context providing scan-to-original coordinate mapping and image representations."""

from __future__ import annotations

from typing import Any, Optional
import numpy as np

from core.constants import DEFAULT_SCAN_MAX_DIMENSION
from core.models import Rect
from core.vision_context import VisionContext


class DetectionContext(VisionContext):
    """Context holding image representations and coordinate mapping between scan and original resolutions."""

    def __init__(
        self,
        original_bgr: np.ndarray,
        source_id: str = "",
        source_sha256: str = "",
        max_scan_dim: int = DEFAULT_SCAN_MAX_DIMENSION,
        source: Optional[Any] = None,
    ):
        super().__init__(original_bgr, max_scan_dim=max_scan_dim, source=source)
        self.source_id = source_id
        self.source_sha256 = source_sha256

    def scan_to_original_rect(self, rect_scan: Rect) -> Rect:
        """Deterministically maps a Rect in scan space to original full-resolution space."""
        if self.scan_scale_x <= 0 or self.scan_scale_y <= 0:
            return Rect(0, 0, 0, 0)

        ox = max(0, min(self.original_w, int(round(rect_scan.x / self.scan_scale_x))))
        oy = max(0, min(self.original_h, int(round(rect_scan.y / self.scan_scale_y))))
        ow = max(0, min(self.original_w - ox, int(round(rect_scan.w / self.scan_scale_x))))
        oh = max(0, min(self.original_h - oy, int(round(rect_scan.h / self.scan_scale_y))))
        return Rect(ox, oy, ow, oh)

    def original_to_scan_rect(self, rect_orig: Rect) -> Rect:
        """Deterministically maps a Rect in original space to scan space."""
        sx = max(0, min(self.scan_w, int(round(rect_orig.x * self.scan_scale_x))))
        sy = max(0, min(self.scan_h, int(round(rect_orig.y * self.scan_scale_y))))
        sw = max(0, min(self.scan_w - sx, int(round(rect_orig.w * self.scan_scale_x))))
        sh = max(0, min(self.scan_h - sy, int(round(rect_orig.h * self.scan_scale_y))))
        return Rect(sx, sy, sw, sh)

    def crop_original(self, rect_original: Rect) -> np.ndarray:
        """Safely extracts a crop from the full-resolution original image."""
        clamped = rect_original.clamp(self.original_w, self.original_h)
        if clamped.is_empty:
            return np.zeros((0, 0, 3), dtype=np.uint8)
        return self.original_bgr[clamped.y:clamped.bottom, clamped.x:clamped.right]

    def crop_scan(self, rect_scan: Rect) -> np.ndarray:
        """Safely extracts a crop from the scan image."""
        return self.roi_bgr(rect_scan)
