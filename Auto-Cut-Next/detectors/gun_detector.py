"""Specialized detector for PUBG weapon upgrade workshop screens."""

from __future__ import annotations

import time
from typing import Any, Optional
import cv2
import numpy as np

from core.constants import Category, GUN_DETECTOR_VERSION
from core.models import Rect
from core.settings import AutoCutSettings
from .detection_context import DetectionContext
from .detector_models import CardCandidate, SpecializedDetectionResult
from .card_quality import CardQualityEvaluator


class GunDetector:
    """Specialized weapon upgrade workshop detector extracting native weapon cards and M5 OCR ROIs."""

    NAME = "gun_workshop_detector"
    VERSION = GUN_DETECTOR_VERSION

    # Primary Orange Range (matches legacy catsung.py parameters)
    ORANGE_LOWER_PRIMARY = (5, 110, 110)
    ORANGE_UPPER_PRIMARY = (32, 255, 255)

    # Relaxed / Amber / Gold Range for lighting, bloom, or skin gradient variations
    ORANGE_LOWER_RELAXED = (4, 70, 70)
    ORANGE_UPPER_RELAXED = (35, 255, 255)

    def __init__(
        self,
        quality_evaluator: Optional[CardQualityEvaluator] = None,
        inner_trim_px: int = 4,
    ):
        self.quality_evaluator = quality_evaluator or CardQualityEvaluator()
        self.inner_trim_px = inner_trim_px

    def _find_orange_card_in_region(
        self,
        roi_bgr: np.ndarray,
        lower_hsv: tuple[int, int, int],
        upper_hsv: tuple[int, int, int],
        min_w: int,
        max_w: int,
        min_h: int,
        max_h: int,
        min_area: int,
        min_aspect: float = 1.50,
        max_aspect: float = 2.50,
    ) -> Optional[tuple[Rect, float, float]]:
        """Scans a BGR sub-region for an orange card border contour."""
        if roi_bgr is None or roi_bgr.size == 0:
            return None

        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(lower_hsv, dtype=np.uint8), np.array(upper_hsv, dtype=np.uint8))

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_rect: Optional[Rect] = None
        best_score = 0.0
        best_fill_ratio = 0.0

        for cnt in contours:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            area = rw * rh
            if area < min_area:
                continue
            if not (min_w <= rw <= max_w and min_h <= rh <= max_h):
                continue
            aspect = float(rw) / float(max(1, rh))
            if not (min_aspect <= aspect <= max_aspect):
                continue

            # Anti-solid-button check: card outlines have hollow centers, not solid orange fill
            card_mask_crop = mask[ry:ry + rh, rx:rx + rw]
            orange_ratio = float(np.count_nonzero(card_mask_crop)) / float(max(1, area))
            # Solid buttons/badges have > 0.55 orange fill; border outline typically has 0.03 .. 0.45
            if orange_ratio > 0.50:
                continue

            # Score prioritizes larger card area and aspect ratio close to 1.95 - 2.05
            aspect_dev = abs(aspect - 2.0)
            score = float(area) * max(0.5, (1.0 - aspect_dev * 0.4))

            if score > best_score:
                best_score = score
                best_rect = Rect(rx, ry, rw, rh)
                best_fill_ratio = orange_ratio

        if best_rect is not None:
            return best_rect, best_score, best_fill_ratio
        return None

    def _find_edge_contrast_card(
        self,
        roi_bgr: np.ndarray,
        min_w: int,
        max_w: int,
        min_h: int,
        max_h: int,
        min_area: int,
    ) -> Optional[Rect]:
        """Secondary signal: locates card candidate via edge gradient contrast in right workshop panel."""
        if roi_bgr is None or roi_bgr.size == 0:
            return None

        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 35, 110)
        kernel = np.ones((5, 5), np.uint8)
        edges_closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(edges_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_rect: Optional[Rect] = None
        best_area = 0

        for cnt in contours:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            area = rw * rh
            if area < min_area:
                continue
            if not (min_w <= rw <= max_w and min_h <= rh <= max_h):
                continue
            aspect = float(rw) / float(max(1, rh))
            if not (1.55 <= aspect <= 2.45):
                continue

            if area > best_area:
                best_area = area
                best_rect = Rect(rx, ry, rw, rh)

        return best_rect

    def detect(
        self,
        context: DetectionContext,
        classification: Optional[Any] = None,
        settings: Optional[AutoCutSettings] = None,
    ) -> SpecializedDetectionResult:
        """Locates the active weapon workshop card using robust multi-signal detection."""
        t0 = time.perf_counter()

        orig_w = context.original_w
        orig_h = context.original_h
        scan_w = context.scan_w
        scan_h = context.scan_h

        # Compute resolution-adaptive bounds
        scale_area = (float(orig_w) / 2778.0) * (float(orig_h) / 1284.0)
        min_area_orig = max(4_000, int(round(15_000 * scale_area)))
        min_w_orig = int(round(orig_w * 0.10))
        max_w_orig = int(round(orig_w * 0.45))
        min_h_orig = int(round(orig_h * 0.07))
        max_h_orig = int(round(orig_h * 0.42))

        best_rect_orig: Optional[Rect] = None
        detection_signal = "none"
        det_confidence = 0.0

        # ----------------------------------------------------------------------
        # SIGNAL 1: High-Resolution Primary Orange Contour Anchor (catsung.py reference)
        # Search in native right portion: x >= 0.54 * orig_w, full vertical extent
        # ----------------------------------------------------------------------
        right_ratio = 0.54
        x_min_orig = int(round(orig_w * right_ratio))
        right_roi_orig = context.original_bgr[:, x_min_orig:]

        res_primary = self._find_orange_card_in_region(
            right_roi_orig,
            self.ORANGE_LOWER_PRIMARY,
            self.ORANGE_UPPER_PRIMARY,
            min_w=min_w_orig,
            max_w=max_w_orig,
            min_h=min_h_orig,
            max_h=max_h_orig,
            min_area=min_area_orig,
        )

        if res_primary is not None:
            rel_rect, score, fill_ratio = res_primary
            best_rect_orig = Rect(x_min_orig + rel_rect.x, rel_rect.y, rel_rect.w, rel_rect.h)
            detection_signal = "native_orange_primary"
            det_confidence = 0.96

        # ----------------------------------------------------------------------
        # SIGNAL 2: High-Resolution Relaxed Orange / Amber / Gold Anchor
        # ----------------------------------------------------------------------
        if best_rect_orig is None:
            res_relaxed = self._find_orange_card_in_region(
                right_roi_orig,
                self.ORANGE_LOWER_RELAXED,
                self.ORANGE_UPPER_RELAXED,
                min_w=min_w_orig,
                max_w=max_w_orig,
                min_h=min_h_orig,
                max_h=max_h_orig,
                min_area=min_area_orig,
            )
            if res_relaxed is not None:
                rel_rect, score, fill_ratio = res_relaxed
                best_rect_orig = Rect(x_min_orig + rel_rect.x, rel_rect.y, rel_rect.w, rel_rect.h)
                detection_signal = "native_orange_relaxed"
                det_confidence = 0.92

        # ----------------------------------------------------------------------
        # SIGNAL 3: Scan-Space Contour Anchor (Synthetic & Low-Resolution Compatibility)
        # ----------------------------------------------------------------------
        if best_rect_orig is None:
            right_ratio_scan = 0.52
            x_min_scan = int(round(scan_w * right_ratio_scan))
            right_roi_scan = context.scan_bgr[:, x_min_scan:]

            min_w_scan = int(round(scan_w * 0.10))
            max_w_scan = int(round(scan_w * 0.45))
            min_h_scan = int(round(scan_h * 0.07))
            max_h_scan = int(round(scan_h * 0.42))
            min_area_scan = min_w_scan * min_h_scan

            res_scan = self._find_orange_card_in_region(
                right_roi_scan,
                (5, 90, 90),
                (35, 255, 255),
                min_w=min_w_scan,
                max_w=max_w_scan,
                min_h=min_h_scan,
                max_h=max_h_scan,
                min_area=min_area_scan,
            )
            if res_scan is not None:
                rel_rect, score, fill_ratio = res_scan
                rect_scan = Rect(x_min_scan + rel_rect.x, rel_rect.y, rel_rect.w, rel_rect.h)
                best_rect_orig = context.scan_to_original_rect(rect_scan)
                detection_signal = "scan_orange_fallback"
                det_confidence = 0.88

        # ----------------------------------------------------------------------
        # SIGNAL 4: Edge Contrast / Card Boundary in Right Workshop Panel
        # ----------------------------------------------------------------------
        if best_rect_orig is None:
            edge_rect = self._find_edge_contrast_card(
                right_roi_orig,
                min_w=min_w_orig,
                max_w=max_w_orig,
                min_h=min_h_orig,
                max_h=max_h_orig,
                min_area=min_area_orig,
            )
            if edge_rect is not None:
                cand_orig = Rect(x_min_orig + edge_rect.x, edge_rect.y, edge_rect.w, edge_rect.h)
                test_tile = context.crop_original(cand_orig)
                content_sc, _ = self.quality_evaluator.evaluate(test_tile).content_score, 0
                if content_sc >= 0.35:
                    best_rect_orig = cand_orig
                    detection_signal = "edge_contrast_boundary"
                    det_confidence = 0.85

        # ----------------------------------------------------------------------
        # SIGNAL 5: Canonical Layout Anchor for High-Confidence Gun Lab Screens
        # ----------------------------------------------------------------------
        is_verified_gun = False
        if classification is not None and hasattr(classification, "category"):
            is_verified_gun = (
                classification.category == Category.GUN.value
                and getattr(classification, "confidence", 0.0) >= 0.80
            )

        if best_rect_orig is None and is_verified_gun:
            # Standard PUBG Mobile Gun Lab active weapon card position
            canonical_x = int(round(orig_w * 0.70))
            canonical_y = int(round(orig_h * 0.20))
            canonical_w = int(round(orig_w * 0.26))
            canonical_h = int(round(orig_h * 0.13))
            cand_orig = Rect(canonical_x, canonical_y, canonical_w, canonical_h)
            test_tile = context.crop_original(cand_orig)
            q_res = self.quality_evaluator.evaluate(test_tile)
            if q_res.content_score >= 0.25:
                best_rect_orig = cand_orig
                detection_signal = "canonical_layout_fallback"
                det_confidence = 0.80

        # ----------------------------------------------------------------------
        # Final Decision: Candidate Acceptance or Fallback Recommendation
        # ----------------------------------------------------------------------
        if best_rect_orig is None:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SpecializedDetectionResult(
                detected=False,
                confidence=0.0,
                fallback_recommended=True,
                detector_name=self.NAME,
                detector_version=self.VERSION,
                reasons=["No workshop weapon card matched across multi-signal detector"],
                duration_ms=round(duration_ms, 2),
            )

        # Apply inner border trimming (removes border artifacts)
        trim = max(0, int(self.inner_trim_px))
        trimmed_orig = Rect(
            best_rect_orig.x + trim,
            best_rect_orig.y + trim,
            max(1, best_rect_orig.w - 2 * trim),
            max(1, best_rect_orig.h - 2 * trim),
        )

        orig_raw = best_rect_orig
        orig_content = trimmed_orig
        trimmed_scan = context.original_to_scan_rect(orig_content)

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

        # Compute ROIs for M5 OCR (in native full-resolution coordinates)
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
            "raw_bbox_orig": orig_raw.to_dict(),
            "raw_bbox_scan": context.original_to_scan_rect(orig_raw).to_dict(),
            "detection_signal": detection_signal,
        }

        duration_ms = (time.perf_counter() - t0) * 1000.0
        accepted = [] if (candidate.locked or candidate.empty or candidate.partial) else [candidate]
        rejected = [candidate] if (candidate.locked or candidate.empty or candidate.partial) else []

        return SpecializedDetectionResult(
            detected=True,
            confidence=det_confidence,
            candidates=[candidate],
            accepted=accepted,
            rejected=rejected,
            reasons=[f"Weapon card detected via {detection_signal} at ({orig_content.x}, {orig_content.y}, {orig_content.w}x{orig_content.h})"],
            diagnostics={
                "detection_signal": detection_signal,
                "orig_bbox": orig_raw.to_dict(),
                "content_bbox": orig_content.to_dict(),
            },
            fallback_recommended=False,
            detector_name=self.NAME,
            detector_version=self.VERSION,
            duration_ms=round(duration_ms, 2),
            metadata=metadata,
        )
