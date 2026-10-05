"""Specialized detector for accessory categories: GRENADE, PARACHUTE, EMOTE."""

from __future__ import annotations

import time
from typing import Any, Optional
import cv2
import numpy as np

from core.constants import Category, ACCESSORY_DETECTOR_VERSION
from core.models import Rect
from core.settings import AutoCutSettings
from .detection_context import DetectionContext
from .detector_models import CardCandidate, CardGeometryProfile, GridDetectionResult, SpecializedDetectionResult
from .card_quality import CardQualityEvaluator
from .grid_detector import GenericGridDetector


class AccessoryDetector:
    """Specialized grid detector for accessory categories with subtab exclusion and tailored bounds."""

    NAME = "accessory_grid_detector"
    VERSION = ACCESSORY_DETECTOR_VERSION

    def __init__(
        self,
        quality_evaluator: Optional[CardQualityEvaluator] = None,
        detector_confidence_threshold: float = 0.60,
    ):
        self.quality_evaluator = quality_evaluator or CardQualityEvaluator()
        self.detector_confidence_threshold = detector_confidence_threshold
        self.grid_detector = GenericGridDetector(quality_evaluator=self.quality_evaluator)

    def detect(
        self,
        context: DetectionContext,
        classification: Optional[Any] = None,
        settings: Optional[AutoCutSettings] = None,
    ) -> SpecializedDetectionResult:
        """Runs accessory detection enforcing subtab exclusions and inventory bounds."""
        t0 = time.perf_counter()

        cat = classification.category.upper() if (classification and hasattr(classification, "category")) else "ACCESSORY"
        scan_w = context.scan_w
        scan_h = context.scan_h

        # Grenade subtab header exclusion: y >= 0.22 * H
        y_min_ratio = 0.22 if cat == Category.GRENADE.value else 0.14
        y_max_ratio = 0.92
        x_min_ratio = 0.58
        x_max_ratio = 0.89

        # Custom geometry profile
        profile = CardGeometryProfile(
            name=f"ACCESSORY_{cat}",
            aspect_min=0.75,
            aspect_max=1.35,
            relative_width_min=0.045,
            relative_width_max=0.16,
            relative_height_min=0.06,
            relative_height_max=0.20,
            allow_single=True,
        )

        raw_rects = self.grid_detector.discover_candidates(context, profile)

        roi_rect = Rect(
            int(round(scan_w * x_min_ratio)),
            int(round(scan_h * y_min_ratio)),
            int(round(scan_w * (x_max_ratio - x_min_ratio))),
            int(round(scan_h * (y_max_ratio - y_min_ratio))),
        )

        in_roi = [r for r in raw_rects if (roi_rect.intersection(r) is not None and roi_rect.intersection(r).area >= 0.50 * r.area)]
        ordered_grid = self.grid_detector.reconstruct_grid(in_roi, profile, scan_w, scan_h)

        if not ordered_grid:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SpecializedDetectionResult(
                detected=False,
                confidence=0.0,
                fallback_recommended=True,
                detector_name=self.NAME,
                detector_version=self.VERSION,
                reasons=[f"No {cat} grid reconstructed in accessory ROI"],
                duration_ms=round(duration_ms, 2),
            )

        median_w = float(np.median([r.w for r, _, _ in ordered_grid]))
        median_h = float(np.percentile([r.h for r, _, _ in ordered_grid], 65))

        all_candidates: list[CardCandidate] = []
        accepted_candidates: list[CardCandidate] = []
        rejected_candidates: list[CardCandidate] = []

        for r_scan, row_idx, col_idx in ordered_grid:
            partial_score = 0.0
            if r_scan.w < median_w * 0.95 or r_scan.h < median_h * 0.95:
                ratio = min(float(r_scan.w) / max(1.0, median_w), float(r_scan.h) / max(1.0, median_h))
                partial_score = max(0.0, 1.0 - ratio)

            trim_x = max(0, int(round((r_scan.w - median_w) / 2.0)))
            trim_y = max(0, int(round((r_scan.h - median_h) / 2.0)))
            trimmed_scan = Rect(
                r_scan.x + trim_x,
                r_scan.y + trim_y,
                max(1, r_scan.w - 2 * trim_x),
                max(1, r_scan.h - 2 * trim_y),
            )

            inset_px = max(1, int(round(min(trimmed_scan.w, trimmed_scan.h) * profile.border_inset_ratio)))
            content_scan = Rect(
                trimmed_scan.x + inset_px,
                trimmed_scan.y + inset_px,
                max(1, trimmed_scan.w - 2 * inset_px),
                max(1, trimmed_scan.h - 2 * inset_px),
            )

            raw_orig = context.scan_to_original_rect(trimmed_scan)
            content_orig = context.scan_to_original_rect(content_scan)

            tile_bgr = context.crop_original(content_orig)
            quality_res = self.quality_evaluator.evaluate(tile_bgr, partial_score=partial_score)

            candidate = CardCandidate(
                rect_scan=trimmed_scan,
                rect_original=raw_orig,
                content_rect_original=content_orig,
                geometry_score=round(1.0 - partial_score, 4),
                row=row_idx,
                column=col_idx,
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

            all_candidates.append(candidate)
            if candidate.locked or candidate.empty or candidate.partial:
                rejected_candidates.append(candidate)
            else:
                accepted_candidates.append(candidate)

        grid_conf, geom_diag = self.grid_detector.compute_grid_confidence(
            ordered_grid,
            scan_w=scan_w,
            scan_h=scan_h,
            profile=profile,
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        fallback_rec = grid_conf < self.detector_confidence_threshold or len(accepted_candidates) == 0

        return SpecializedDetectionResult(
            detected=True,
            confidence=grid_conf,
            candidates=all_candidates,
            accepted=accepted_candidates,
            rejected=rejected_candidates,
            reasons=[f"{cat} grid detected ({len(accepted_candidates)} active / {len(all_candidates)} total)"],
            diagnostics={
                "category": cat,
                "grid_confidence": grid_conf,
                "median_w": median_w,
                "median_h": median_h,
                **geom_diag,
            },
            fallback_recommended=fallback_rec,
            detector_name=self.NAME,
            detector_version=self.VERSION,
            duration_ms=round(duration_ms, 2),
            metadata={"category": cat},
        )
