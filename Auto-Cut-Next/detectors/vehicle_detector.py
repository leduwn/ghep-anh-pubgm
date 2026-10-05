"""Specialized detector for PUBG vehicle gallery screens."""

from __future__ import annotations

import time
from typing import Any, Optional
import cv2
import numpy as np

from core.constants import VEHICLE_DETECTOR_VERSION
from core.models import Rect
from core.settings import AutoCutSettings
from .detection_context import DetectionContext
from .detector_models import CardCandidate, SpecializedDetectionResult
from .card_quality import CardQualityEvaluator


class VehicleDetector:
    """Specialized vehicle gallery detector extracting wide horizontal vehicle cards."""

    NAME = "vehicle_card_detector"
    VERSION = VEHICLE_DETECTOR_VERSION

    # Reference column ratios at 2778x1284
    COL_X_MIN_RATIO = 1840.0 / 2778.0  # ~0.662
    COL_X_MAX_RATIO = 2420.0 / 2778.0  # ~0.871
    CARD_ASPECT_MIN = 2.1
    CARD_ASPECT_MAX = 3.1
    STD_ASPECT = 498.0 / 190.0          # ~2.62

    def __init__(
        self,
        quality_evaluator: Optional[CardQualityEvaluator] = None,
        border_trim_px: int = 3,
    ):
        self.quality_evaluator = quality_evaluator or CardQualityEvaluator()
        self.border_trim_px = border_trim_px

    def detect(
        self,
        context: DetectionContext,
        classification: Optional[Any] = None,
        settings: Optional[AutoCutSettings] = None,
    ) -> SpecializedDetectionResult:
        """Locates vehicle cards in the right gallery column with boundary and partial checks."""
        t0 = time.perf_counter()

        scan_w = context.scan_w
        scan_h = context.scan_h

        col_x1 = max(0, int(round(scan_w * (self.COL_X_MIN_RATIO - 0.04))))
        col_x2 = min(scan_w, int(round(scan_w * (self.COL_X_MAX_RATIO + 0.04))))
        col_roi = context.scan_bgr[:, col_x1:col_x2]

        if col_roi.size == 0:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SpecializedDetectionResult(
                detected=False,
                confidence=0.0,
                fallback_recommended=True,
                detector_name=self.NAME,
                detector_version=self.VERSION,
                reasons=["Vehicle column region empty"],
                duration_ms=round(duration_ms, 2),
            )

        gray_col = cv2.cvtColor(col_roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray_col, 30, 100)
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        expected_w = int(round((self.COL_X_MAX_RATIO - self.COL_X_MIN_RATIO) * scan_w * 0.90))
        min_card_w = int(round(expected_w * 0.65))

        raw_candidates: list[Rect] = []
        for cnt in contours:
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            aspect = float(rw) / float(max(1, rh))
            if rw >= min_card_w and (self.CARD_ASPECT_MIN <= aspect <= self.CARD_ASPECT_MAX):
                global_x = col_x1 + rx
                raw_candidates.append(Rect(global_x, ry, rw, rh))

        if not raw_candidates:
            # Fallback to thresholding on brightness
            bright = (gray_col > 60).astype(np.uint8) * 255
            b_contours, _ = cv2.findContours(bright, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in b_contours:
                rx, ry, rw, rh = cv2.boundingRect(cnt)
                aspect = float(rw) / float(max(1, rh))
                if rw >= min_card_w and (self.CARD_ASPECT_MIN <= aspect <= self.CARD_ASPECT_MAX):
                    global_x = col_x1 + rx
                    raw_candidates.append(Rect(global_x, ry, rw, rh))

        if not raw_candidates:
            # Fallback to expanded column search ROI: x: 0.54..0.96 * scan_w
            exp_x1 = max(0, int(round(scan_w * 0.54)))
            exp_x2 = min(scan_w, int(round(scan_w * 0.96)))
            exp_roi = context.scan_bgr[:, exp_x1:exp_x2]
            if exp_roi.size > 0:
                exp_gray = cv2.cvtColor(exp_roi, cv2.COLOR_BGR2GRAY)
                exp_edges = cv2.Canny(exp_gray, 30, 100)
                exp_edges = cv2.morphologyEx(exp_edges, cv2.MORPH_CLOSE, kernel)
                exp_contours, _ = cv2.findContours(exp_edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                for cnt in exp_contours:
                    rx, ry, rw, rh = cv2.boundingRect(cnt)
                    aspect = float(rw) / float(max(1, rh))
                    if rw >= min_card_w and (self.CARD_ASPECT_MIN <= aspect <= self.CARD_ASPECT_MAX):
                        raw_candidates.append(Rect(exp_x1 + rx, ry, rw, rh))

        if not raw_candidates:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SpecializedDetectionResult(
                detected=False,
                confidence=0.0,
                fallback_recommended=True,
                detector_name=self.NAME,
                detector_version=self.VERSION,
                reasons=["No vehicle cards matching aspect 2.1..3.1 in vehicle gallery column"],
                duration_ms=round(duration_ms, 2),
            )

        # Median width and X alignment
        med_x = int(np.median([r.x for r in raw_candidates]))
        med_w = int(np.median([r.w for r in raw_candidates]))
        med_h = int(np.median([r.h for r in raw_candidates]))

        # Filter candidates aligned with median column
        aligned = [
            r for r in raw_candidates
            if abs(r.x - med_x) <= max(15, int(round(0.02 * scan_w))) and (r.w >= 0.80 * med_w)
        ]

        # Sort top-to-bottom and deduplicate overlapping vertical boxes
        aligned = sorted(aligned, key=lambda r: r.y)
        deduped: list[Rect] = []
        min_v_distance = max(10, int(round(0.35 * med_h)))
        for r in aligned:
            if not deduped or (r.y - deduped[-1].y) >= min_v_distance:
                deduped.append(r)

        all_candidates: list[CardCandidate] = []
        accepted_candidates: list[CardCandidate] = []
        rejected_candidates: list[CardCandidate] = []

        trim = self.border_trim_px
        for idx, r_scan in enumerate(deduped):
            # Check partial / boundary cut
            is_cut_edge = (r_scan.y < 8) or (r_scan.bottom > scan_h - 8)
            is_short = r_scan.h < 0.85 * med_h
            partial_score = 0.5 if (is_cut_edge or is_short) else 0.0

            # Trim border
            trimmed_scan = Rect(
                r_scan.x + trim,
                r_scan.y + trim,
                max(1, r_scan.w - 2 * trim),
                max(1, r_scan.h - 2 * trim),
            )

            raw_orig = context.scan_to_original_rect(r_scan)
            content_orig = context.scan_to_original_rect(trimmed_scan)

            tile_bgr = context.crop_original(content_orig)
            quality_res = self.quality_evaluator.evaluate(tile_bgr, partial_score=partial_score)

            candidate = CardCandidate(
                rect_scan=trimmed_scan,
                rect_original=raw_orig,
                content_rect_original=content_orig,
                geometry_score=round(1.0 - partial_score, 4),
                row=idx,
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
                diagnostics={
                    "aspect_ratio": round(r_scan.w / max(1, r_scan.h), 3),
                    **quality_res.diagnostics,
                },
            )

            all_candidates.append(candidate)
            if candidate.locked or candidate.empty or candidate.partial:
                rejected_candidates.append(candidate)
            else:
                accepted_candidates.append(candidate)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        conf = 0.95 if accepted_candidates else 0.70

        return SpecializedDetectionResult(
            detected=True,
            confidence=conf,
            candidates=all_candidates,
            accepted=accepted_candidates,
            rejected=rejected_candidates,
            reasons=[f"Detected {len(all_candidates)} vehicle cards ({len(accepted_candidates)} active)"],
            diagnostics={
                "card_count": len(all_candidates),
                "active_count": len(accepted_candidates),
                "med_w": med_w,
                "med_h": med_h,
            },
            fallback_recommended=False,
            detector_name=self.NAME,
            detector_version=self.VERSION,
            duration_ms=round(duration_ms, 2),
            metadata={
                "column_x": med_x,
                "card_width": med_w,
            },
        )
