"""High-level generic detector facade coordinating grid discovery, quality, and asset creation."""

from __future__ import annotations

from typing import Optional
import numpy as np

from core.constants import Category, Decision, MISC_GRID_VERSION
from core.models import DetectedAsset, Rect, generate_asset_id
from .detection_context import DetectionContext
from .detector_models import CardGeometryProfile, GridDetectionResult, CardCandidate
from .grid_detector import GenericGridDetector
from .card_quality import CardQualityEvaluator
from .dedup import AccountDeduplicator


class GenericDetector:
    """Coordinates generic grid detection, card quality filtering, and logical DetectedAsset creation."""

    VERSION = MISC_GRID_VERSION

    def __init__(
        self,
        profile: Optional[CardGeometryProfile] = None,
        lock_threshold: float = 0.50,
        empty_content_threshold: float = 0.35,
        duplicate_mae_threshold: float = 12.0,
        duplicate_phash_max_distance: int = 10,
        detector_confidence_threshold: float = 0.60,
        empty_detail_threshold: Optional[float] = None,
        duplicate_threshold: Optional[float] = None,
    ):
        self.profile = profile or CardGeometryProfile()
        eff_empty = empty_content_threshold if empty_detail_threshold is None else (0.35 if empty_detail_threshold == 0.15 else empty_detail_threshold)
        eff_mae = duplicate_mae_threshold if duplicate_threshold is None else (12.0 if duplicate_threshold <= 1.0 else duplicate_threshold)
        self.detector_confidence_threshold = detector_confidence_threshold

        self.quality_evaluator = CardQualityEvaluator(
            lock_threshold=lock_threshold,
            empty_content_threshold=eff_empty,
        )
        self.grid_detector = GenericGridDetector(
            default_profile=self.profile,
            quality_evaluator=self.quality_evaluator,
        )
        self.deduplicator = AccountDeduplicator(
            diff_threshold=eff_mae,
            phash_threshold=duplicate_phash_max_distance,
        )

    def detect_grid(
        self,
        context: DetectionContext,
        profile: Optional[CardGeometryProfile] = None,
    ) -> GridDetectionResult:
        """Executes candidate discovery and grid reconstruction on the detection context."""
        return self.grid_detector.detect(context, profile=profile or self.profile)

    def create_assets_from_candidates(
        self,
        candidates: list[CardCandidate],
        context: DetectionContext,
        category: str,
        detector_version: str = MISC_GRID_VERSION,
        source_review_required: bool = False,
        grid_confidence: Optional[float] = None,
    ) -> list[DetectedAsset]:
        """Converts CardCandidate items into canonical DetectedAsset instances with stable deterministic IDs."""
        assets: list[DetectedAsset] = []
        for idx, cand in enumerate(candidates):
            asset_id = generate_asset_id(
                source_sha=context.source_sha256,
                category=category,
                detector="generic_grid_detector",
                detector_version=detector_version,
                rect=cand.content_rect_original,
            )

            review_reasons = list(cand.rejection_reasons)
            review_req = cand.review_required
            if source_review_required:
                review_req = True
                review_reasons.append("Source classification requires review")

            if grid_confidence is not None and grid_confidence < self.detector_confidence_threshold:
                review_req = True
                review_reasons.append(f"Grid geometry confidence {grid_confidence:.2f} below threshold {self.detector_confidence_threshold:.2f}")

            asset = DetectedAsset(
                id=asset_id,
                source_id=context.source_id,
                category=category,
                crop_rect=cand.content_rect_original,
                native_width=cand.content_rect_original.w,
                native_height=cand.content_rect_original.h,
                detector="generic_grid_detector",
                detector_version=detector_version,
                confidence=cand.confidence,
                locked=cand.locked,
                partial=cand.partial,
                empty=cand.empty,
                duplicate=False,
                metadata={
                    "partial_score": cand.partial_score,
                    "lock_score": cand.lock_score,
                    "content_score": cand.content_score,
                    "geometry_score": cand.geometry_score,
                },
                review_required=review_req,
                review_reasons=review_reasons,
                order=idx,
                raw_crop_rect=cand.rect_original,
                duplicate_of=None,
                quality_scores={
                    "lock": cand.lock_score,
                    "content": cand.content_score,
                    "partial": cand.partial_score,
                },
                grid_position=(cand.row, cand.column),
            )
            assets.append(asset)
        return assets
