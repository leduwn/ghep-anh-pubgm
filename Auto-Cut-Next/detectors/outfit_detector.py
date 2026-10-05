"""Specialized detector for PUBG character full-body outfit screens (normal and supercar lobby)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional
import cv2
import numpy as np

from core.constants import OUTFIT_DETECTOR_VERSION
from core.models import Rect
from core.settings import AutoCutSettings
from .detection_context import DetectionContext
from .detector_models import CardCandidate, SpecializedDetectionResult
from .card_quality import CardQualityEvaluator


SUPERCAR_CEILING_PATH = Path(__file__).resolve().parent.parent / "assets" / "classifier" / "supercar_ceiling.png"
_SUPERCAR_CEILING_CACHE: Optional[np.ndarray] = None


def get_supercar_ceiling_template() -> Optional[np.ndarray]:
    """Loads and caches the supercar ceiling grayscale template."""
    global _SUPERCAR_CEILING_CACHE
    if _SUPERCAR_CEILING_CACHE is None and SUPERCAR_CEILING_PATH.is_file():
        img = cv2.imread(str(SUPERCAR_CEILING_PATH), cv2.IMREAD_GRAYSCALE)
        if img is not None:
            _SUPERCAR_CEILING_CACHE = img
    return _SUPERCAR_CEILING_CACHE


class OutfitDetector:
    """Specialized detector extracting full-body character crops for normal and supercar lobby."""

    NAME = "outfit_character_detector"
    VERSION = OUTFIT_DETECTOR_VERSION

    # Reference coordinates at 2778x1284
    REF_W = 2778.0
    REF_H = 1284.0
    SUPERCAR_CROP = (786, 123, 642, 994)  # x, y, w, h
    NORMAL_CROP_W = 774
    NORMAL_CROP_H = 1220
    DEFAULT_ANCHOR_X = 842.0

    def __init__(
        self,
        quality_evaluator: Optional[CardQualityEvaluator] = None,
        supercar_threshold: float = 0.75,
    ):
        self.quality_evaluator = quality_evaluator or CardQualityEvaluator()
        self.supercar_threshold = supercar_threshold

    def is_supercar_lobby(self, scan_bgr: np.ndarray) -> tuple[bool, float]:
        """Matches upper ceiling region against supercar ceiling template."""
        tmpl = get_supercar_ceiling_template()
        if tmpl is None or scan_bgr is None or scan_bgr.size == 0:
            return False, 0.0

        h, w = scan_bgr.shape[:2]
        roi_h = max(1, int(round(280.0 * h / self.REF_H)))
        roi_w = max(1, int(round(1500.0 * w / self.REF_W)))
        roi = scan_bgr[:roi_h, :roi_w]

        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        th = cv2.resize(gray_roi, (tmpl.shape[1], tmpl.shape[0]), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(th, tmpl, cv2.TM_CCOEFF_NORMED)
        score = float(res[0, 0])
        return score >= self.supercar_threshold, score

    def estimate_character_anchor_x(self, scan_bgr: np.ndarray) -> Optional[float]:
        """Calculates horizontal character center from vertical edge density profile."""
        h, w = scan_bgr.shape[:2]
        scale_x = w / self.REF_W
        scale_y = h / self.REF_H

        x1 = max(0, int(round(250.0 * scale_x)))
        x2 = min(w, int(round(1500.0 * scale_x)))
        y1 = max(0, int(round(80.0 * scale_y)))
        y2 = min(h, int(round(1180.0 * scale_y)))

        roi = scan_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edge_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
        edge_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
        profile = np.mean(edge_x + edge_y, axis=0)

        window = max(40, int(round(350.0 * scale_x)))
        if profile.size <= window:
            return None

        scores = np.convolve(profile, np.ones(window, dtype=np.float32), mode="valid")
        best_idx = int(np.argmax(scores))
        center_px = x1 + best_idx + window / 2.0
        return float(center_px) / scale_x

    def detect(
        self,
        context: DetectionContext,
        classification: Optional[Any] = None,
        settings: Optional[AutoCutSettings] = None,
    ) -> SpecializedDetectionResult:
        """Extracts character bounding crop from lobby screen."""
        t0 = time.perf_counter()

        scan_w = context.scan_w
        scan_h = context.scan_h
        scale_x = scan_w / self.REF_W
        scale_y = scan_h / self.REF_H

        # Differentiate full-body lobby vs wardrobe inventory grid
        is_wardrobe_grid = False
        if classification and hasattr(classification, "reasons"):
            for r in classification.reasons:
                if "wardrobe" in r.lower() or "inventory" in r.lower():
                    is_wardrobe_grid = True
                    break

        # Check lobby type
        is_supercar, ceiling_score = self.is_supercar_lobby(context.scan_bgr)
        lobby_type = "supercar" if is_supercar else "normal"

        if not is_wardrobe_grid and not is_supercar:
            # Check for multiple inventory card outlines in right inventory column
            rx1 = int(round(0.60 * scan_w))
            right_roi = context.scan_bgr[:, rx1:]
            if right_roi.size > 0:
                gray_r = cv2.cvtColor(right_roi, cv2.COLOR_BGR2GRAY)
                edges_r = cv2.Canny(gray_r, 40, 120)
                contours_r, _ = cv2.findContours(edges_r, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                card_like_count = 0
                min_cw = int(round(0.04 * scan_w))
                max_cw = int(round(0.18 * scan_w))
                for cnt in contours_r:
                    _, _, rw, rh = cv2.boundingRect(cnt)
                    if min_cw <= rw <= max_cw and min_cw <= rh <= max_cw:
                        aspect = float(rw) / float(max(1, rh))
                        if 0.70 <= aspect <= 1.40:
                            card_like_count += 1
                if card_like_count >= 3:
                    is_wardrobe_grid = True

        if is_wardrobe_grid:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SpecializedDetectionResult(
                detected=False,
                confidence=0.0,
                fallback_recommended=True,
                detector_name=self.NAME,
                detector_version=self.VERSION,
                reasons=["Wardrobe outfit screen contains inventory grid; falling back to generic grid detector"],
                duration_ms=round(duration_ms, 2),
            )

        if is_supercar:
            ref_x, ref_y, ref_w, ref_h = self.SUPERCAR_CROP
            crop_scan = Rect(
                int(round(ref_x * scale_x)),
                int(round(ref_y * scale_y)),
                int(round(ref_w * scale_x)),
                int(round(ref_h * scale_y)),
            )
        else:
            anchor_x = self.estimate_character_anchor_x(context.scan_bgr) or self.DEFAULT_ANCHOR_X
            if abs(anchor_x - self.DEFAULT_ANCHOR_X) <= 30.0:
                anchor_x = self.DEFAULT_ANCHOR_X

            base_x = max(120.0, min(408.0 + (anchor_x - self.DEFAULT_ANCHOR_X), 920.0))
            crop_scan = Rect(
                int(round(base_x * scale_x)),
                0,
                int(round(self.NORMAL_CROP_W * scale_x)),
                min(scan_h, int(round(self.NORMAL_CROP_H * scale_y))),
            )

        # Clamp to scan dimensions
        clamped_scan = crop_scan.clamp(scan_w, scan_h)
        if clamped_scan.w < int(round(200 * scale_x)) or clamped_scan.h < int(round(400 * scale_y)):
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SpecializedDetectionResult(
                detected=False,
                confidence=0.0,
                fallback_recommended=True,
                detector_name=self.NAME,
                detector_version=self.VERSION,
                reasons=["Character crop dimensions too small or out of bounds"],
                duration_ms=round(duration_ms, 2),
            )

        orig_crop = context.scan_to_original_rect(clamped_scan)
        tile_bgr = context.crop_original(orig_crop)

        # Check content
        quality_res = self.quality_evaluator.evaluate(tile_bgr, partial_score=0.0)

        candidate = CardCandidate(
            rect_scan=clamped_scan,
            rect_original=orig_crop,
            content_rect_original=orig_crop,
            geometry_score=1.0,
            row=0,
            column=0,
            partial_score=quality_res.partial_score,
            lock_score=quality_res.lock_score,
            content_score=quality_res.content_score,
            locked=False,
            empty=quality_res.empty,
            partial=quality_res.partial,
            confidence=quality_res.confidence,
            review_required=quality_res.review_required,
            rejection_reasons=quality_res.reasons,
            diagnostics={
                "lobby_type": lobby_type,
                "ceiling_score": round(ceiling_score, 4),
                **quality_res.diagnostics,
            },
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        conf = 0.95 if is_supercar else 0.90

        return SpecializedDetectionResult(
            detected=True,
            confidence=conf,
            candidates=[candidate],
            accepted=[candidate],
            rejected=[],
            reasons=[f"Outfit character crop ({lobby_type} lobby) at ({orig_crop.x}, {orig_crop.y}, {orig_crop.w}x{orig_crop.h})"],
            diagnostics={
                "lobby_type": lobby_type,
                "ceiling_score": round(ceiling_score, 4),
            },
            fallback_recommended=False,
            detector_name=self.NAME,
            detector_version=self.VERSION,
            duration_ms=round(duration_ms, 2),
            metadata={
                "lobby_type": lobby_type,
                "anchor_x": round(anchor_x, 1) if not is_supercar else None,
            },
        )
