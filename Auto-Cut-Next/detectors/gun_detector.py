"""Specialized detector for PUBG weapon upgrade workshop screens."""

from __future__ import annotations

import time
from typing import Any, Optional
import cv2
import numpy as np

from core.constants import GUN_DETECTOR_VERSION
from core.models import Rect
from core.settings import AutoCutSettings
from .detection_context import DetectionContext
from .detector_models import CardCandidate, SpecializedDetectionResult
from .card_quality import CardQualityEvaluator


class GunDetector:
    """Specialized weapon upgrade workshop detector extracting native weapon cards and M5 OCR ROIs."""

    NAME = "gun_workshop_detector"
    VERSION = GUN_DETECTOR_VERSION

    ORANGE_LOWER = (5, 100, 100)
    ORANGE_UPPER = (30, 255, 255)

    def __init__(
        self,
        quality_evaluator: Optional[CardQualityEvaluator] = None,
        inner_trim_px: int = 4,
    ):
        self.quality_evaluator = quality_evaluator or CardQualityEvaluator()
        self.inner_trim_px = inner_trim_px

    def detect(
        self,
        context: DetectionContext,
        classification: Optional[Any] = None,
        settings: Optional[AutoCutSettings] = None,
    ) -> SpecializedDetectionResult:
        """Locates the active weapon workshop card and computes metadata ROIs for OCR."""
        t0 = time.perf_counter()

        scan_w = context.scan_w
        scan_h = context.scan_h

        # Search in right portion: x >= 0.52 * scan_w, y <= 0.80 * scan_h (exclude bottom action button)
        right_ratio = 0.52
        x_min = int(round(scan_w * right_ratio))
        y_max = int(round(scan_h * 0.80))
        right_roi_bgr = context.scan_bgr[:y_max, x_min:]

        hsv = cv2.cvtColor(right_roi_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array(self.ORANGE_LOWER, dtype=np.uint8)
        upper = np.array(self.ORANGE_UPPER, dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_rect_scan: Optional[Rect] = None
        best_area = 0
        min_card_w = int(round(scan_w * 0.15))
        min_card_h = int(round(scan_h * 0.12))
        max_card_w = int(round(scan_w * 0.45))
        max_card_h = int(round(scan_h * 0.45))
        min_area = min_card_w * min_card_h

        for cnt in contours:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            area = rw * rh
            if area < min_area:
                continue
            if not (min_card_w <= rw <= max_card_w and min_card_h <= rh <= max_card_h):
                continue
            aspect = float(rw) / float(max(1, rh))
            if not (1.45 <= aspect <= 2.65):
                continue

            # Anti-solid-button check: a card outline has a hollow center, not solid orange fill
            card_mask_crop = mask[ry:ry + rh, rx:rx + rw]
            orange_ratio = float(np.count_nonzero(card_mask_crop)) / float(max(1, area))
            # Solid buttons/badges have > 0.55 orange fill; border outline typically has 0.04 .. 0.40
            if orange_ratio > 0.50:
                continue

            if area > best_area:
                best_area = area
                best_rect_scan = Rect(x_min + rx, ry, rw, rh)

        if best_rect_scan is None:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SpecializedDetectionResult(
                detected=False,
                confidence=0.0,
                fallback_recommended=True,
                detector_name=self.NAME,
                detector_version=self.VERSION,
                reasons=["No workshop weapon card contour matched in right screen region"],
                duration_ms=round(duration_ms, 2),
            )

        # Apply inner border trimming (to remove border artifacts)
        trim = self.inner_trim_px
        trimmed_scan = Rect(
            best_rect_scan.x + trim,
            best_rect_scan.y + trim,
            max(1, best_rect_scan.w - 2 * trim),
            max(1, best_rect_scan.h - 2 * trim),
        )

        orig_raw = context.scan_to_original_rect(best_rect_scan)
        orig_content = context.scan_to_original_rect(trimmed_scan)

        tile_bgr = context.crop_original(orig_content)
        quality_res = self.quality_evaluator.evaluate(tile_bgr, partial_score=0.0)

        candidate = CardCandidate(
            rect_scan=trimmed_scan,
            rect_original=orig_raw,
            content_rect_original=orig_content,
            geometry_score=1.0,
            row=0,
            column=0,
            partial_score=quality_res.partial_score,
            lock_score=quality_res.lock_score,
            content_score=quality_res.content_score,
            locked=quality_res.locked,
            empty=quality_res.empty,
            partial=quality_res.partial,
            confidence=quality_res.confidence,
            review_required=quality_res.review_required,
            rejection_reasons=quality_res.reasons,
            diagnostics=quality_res.diagnostics,
        )

        # Compute ROIs for M5 OCR (in original pixel coordinates)
        orig_w = context.original_w
        orig_h = context.original_h

        # Fast level ROI: upper left region (x: 0..0.25 * W, y: 0.08..0.20 * H)
        level_roi = Rect(0, int(round(0.08 * orig_h)), int(round(0.25 * orig_w)), int(round(0.12 * orig_h)))

        # Name ROI: top left region (x: 0..0.45 * W, y: 0.02..0.12 * H)
        name_roi = Rect(0, int(round(0.02 * orig_h)), int(round(0.45 * orig_w)), int(round(0.10 * orig_h)))

        # Elimination tracker / kill counter ROI: adjacent to left of card
        card_gx = orig_raw.x
        c_x2 = max(0, card_gx - 10)
        c_x1 = max(0, card_gx - int(round(orig_w * 0.16)))
        c_y1 = int(round(orig_h * 0.07))
        c_y2 = int(round(orig_h * 0.20))
        counter_roi = Rect(c_x1, c_y1, max(1, c_x2 - c_x1), max(1, c_y2 - c_y1))

        metadata = {
            "level_roi": level_roi.to_dict(),
            "name_roi": name_roi.to_dict(),
            "kill_counter_roi": counter_roi.to_dict(),
            "raw_bbox_scan": best_rect_scan.to_dict(),
        }

        duration_ms = (time.perf_counter() - t0) * 1000.0
        accepted = [] if (candidate.locked or candidate.empty or candidate.partial) else [candidate]
        rejected = [candidate] if (candidate.locked or candidate.empty or candidate.partial) else []

        conf = 0.95 if best_area > min_area * 1.5 else 0.85
        return SpecializedDetectionResult(
            detected=True,
            confidence=conf,
            candidates=[candidate],
            accepted=accepted,
            rejected=rejected,
            reasons=[f"Weapon card detected at ({orig_content.x}, {orig_content.y}, {orig_content.w}x{orig_content.h})"],
            diagnostics={"best_area": best_area, "min_area": min_area},
            fallback_recommended=False,
            detector_name=self.NAME,
            detector_version=self.VERSION,
            duration_ms=round(duration_ms, 2),
            metadata=metadata,
        )
