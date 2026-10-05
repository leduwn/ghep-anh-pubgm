"""CategoryRouter dispatching specialized PUBG detectors with shared-context fallback."""

from __future__ import annotations

import time
from typing import Any, Optional

from core.constants import (
    Category,
    Decision,
    MISC_GRID_VERSION,
    ROUTER_VERSION,
    GUN_DETECTOR_VERSION,
    VEHICLE_DETECTOR_VERSION,
    OUTFIT_DETECTOR_VERSION,
    EQUIPMENT_DETECTOR_VERSION,
    ACCESSORY_DETECTOR_VERSION,
    INVENTORY_DETECTOR_VERSION,
)
from core.models import DetectedAsset, Rect, generate_asset_id
from core.settings import AutoCutSettings
from .detection_context import DetectionContext
from .detector_models import CardCandidate, SpecializedDetectionResult, GridDetectionResult
from .card_quality import CardQualityEvaluator
from .grid_detector import GenericGridDetector
from .gun_detector import GunDetector
from .vehicle_detector import VehicleDetector
from .outfit_detector import OutfitDetector
from .equipment_detector import EquipmentDetector
from .accessory_detector import AccessoryDetector
from .inventory_detector import InventoryDetector


class CategoryRouter:
    """Dispatches category-specific detectors and provides shared-context zero-redecode generic fallback."""

    NAME = "category_router"
    VERSION = ROUTER_VERSION

    def __init__(
        self,
        quality_evaluator: Optional[CardQualityEvaluator] = None,
        detector_confidence_threshold: float = 0.60,
    ):
        self.quality_evaluator = quality_evaluator or CardQualityEvaluator()
        self.detector_confidence_threshold = detector_confidence_threshold

        # Specialized detectors
        self.gun_detector = GunDetector(quality_evaluator=self.quality_evaluator)
        self.vehicle_detector = VehicleDetector(quality_evaluator=self.quality_evaluator)
        self.outfit_detector = OutfitDetector(quality_evaluator=self.quality_evaluator)
        self.equipment_detector = EquipmentDetector(
            quality_evaluator=self.quality_evaluator,
            detector_confidence_threshold=self.detector_confidence_threshold,
        )
        self.accessory_detector = AccessoryDetector(
            quality_evaluator=self.quality_evaluator,
            detector_confidence_threshold=self.detector_confidence_threshold,
        )
        self.inventory_detector = InventoryDetector(
            quality_evaluator=self.quality_evaluator,
            detector_confidence_threshold=self.detector_confidence_threshold,
        )
        self.generic_grid_detector = GenericGridDetector(quality_evaluator=self.quality_evaluator)

    def get_detector_for_category(self, category_str: str) -> tuple[Any, str, str]:
        """Resolves the specialized detector instance, its name, and version for a given category."""
        cat = category_str.upper()
        if cat == Category.GUN.value:
            return self.gun_detector, GunDetector.NAME, GunDetector.VERSION
        if cat == Category.VEHICLE.value:
            return self.vehicle_detector, VehicleDetector.NAME, VehicleDetector.VERSION
        if cat == Category.OUTFIT.value:
            return self.outfit_detector, OutfitDetector.NAME, OutfitDetector.VERSION
        if cat in (Category.HELMET.value, Category.BACKPACK.value, Category.MASK.value):
            return self.equipment_detector, EquipmentDetector.NAME, EquipmentDetector.VERSION
        if cat in (Category.GRENADE.value, Category.PARACHUTE.value, Category.EMOTE.value):
            return self.accessory_detector, AccessoryDetector.NAME, AccessoryDetector.VERSION
        if cat in (Category.ITEM_SET.value, Category.MISC.value):
            return self.inventory_detector, InventoryDetector.NAME, InventoryDetector.VERSION

        return self.generic_grid_detector, GenericGridDetector.NAME, MISC_GRID_VERSION

    def route(
        self,
        context: DetectionContext,
        classification: Optional[Any] = None,
        settings: Optional[AutoCutSettings] = None,
    ) -> SpecializedDetectionResult:
        """Runs the appropriate specialized detector with shared-context fallback to GenericGridDetector."""
        t0 = time.perf_counter()

        cat = classification.category.upper() if (classification and hasattr(classification, "category")) else "UNKNOWN"
        detector, det_name, det_ver = self.get_detector_for_category(cat)

        primary_detector = det_name
        fallback_detector: Optional[str] = None
        fallback_used = False
        specialized_confidence = 0.0
        fallback_confidence = 0.0

        if det_name == GenericGridDetector.NAME:
            # Direct generic grid detection
            generic_res = self.generic_grid_detector.detect(context)
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SpecializedDetectionResult(
                detected=generic_res.detected,
                confidence=generic_res.grid_confidence,
                candidates=generic_res.candidates,
                accepted=generic_res.accepted,
                rejected=generic_res.rejected,
                reasons=[f"Generic grid detection ({len(generic_res.accepted)} active / {len(generic_res.candidates)} total)"],
                diagnostics=generic_res.diagnostics,
                fallback_recommended=False,
                detector_name=GenericGridDetector.NAME,
                detector_version=MISC_GRID_VERSION,
                duration_ms=round(duration_ms, 2),
                metadata={
                    "primary_detector": GenericGridDetector.NAME,
                    "fallback_detector": None,
                    "fallback_used": False,
                    "specialized_confidence": generic_res.grid_confidence,
                    "fallback_confidence": 0.0,
                },
            )

        # Run specialized detector
        spec_res: SpecializedDetectionResult = detector.detect(
            context,
            classification=classification,
            settings=settings,
        )
        specialized_confidence = spec_res.confidence

        # Determine if fallback is required
        needs_fallback = (
            spec_res.fallback_recommended
            or not spec_res.detected
            or len(spec_res.candidates) == 0
        )

        if not needs_fallback:
            # Succeeded without fallback
            spec_res.metadata["primary_detector"] = primary_detector
            spec_res.metadata["fallback_detector"] = None
            spec_res.metadata["fallback_used"] = False
            spec_res.metadata["specialized_confidence"] = round(specialized_confidence, 4)
            spec_res.metadata["fallback_confidence"] = 0.0
            return spec_res

        # Fallback triggered: execute GenericGridDetector on the exact same context (zero-redecode)
        fallback_detector = GenericGridDetector.NAME
        fallback_used = True

        generic_res = self.generic_grid_detector.detect(context)
        fallback_confidence = generic_res.grid_confidence
        duration_ms = (time.perf_counter() - t0) * 1000.0

        fallback_reasons = list(spec_res.reasons)
        fallback_reasons.append(
            f"Fallback to GenericGridDetector triggered (specialized conf: {specialized_confidence:.2f}, generic conf: {fallback_confidence:.2f})"
        )

        combined_diagnostics = {
            "specialized_diagnostics": spec_res.diagnostics,
            "fallback_diagnostics": generic_res.diagnostics,
        }

        return SpecializedDetectionResult(
            detected=generic_res.detected,
            confidence=generic_res.grid_confidence,
            candidates=generic_res.candidates,
            accepted=generic_res.accepted,
            rejected=generic_res.rejected,
            reasons=fallback_reasons,
            diagnostics=combined_diagnostics,
            fallback_recommended=False,
            detector_name=GenericGridDetector.NAME,
            detector_version=MISC_GRID_VERSION,
            duration_ms=round(duration_ms, 2),
            metadata={
                "primary_detector": primary_detector,
                "fallback_detector": fallback_detector,
                "fallback_used": fallback_used,
                "specialized_confidence": round(specialized_confidence, 4),
                "fallback_confidence": round(fallback_confidence, 4),
            },
        )

    def create_assets_from_result(
        self,
        result: SpecializedDetectionResult,
        context: DetectionContext,
        category: str,
        source_review_required: bool = False,
    ) -> list[DetectedAsset]:
        """Creates canonical DetectedAsset instances preserving provenance of specialized and fallback detection."""
        assets: list[DetectedAsset] = []
        detector_name = result.detector_name
        detector_ver = result.detector_version

        primary_detector = result.metadata.get("primary_detector", detector_name)
        fallback_detector = result.metadata.get("fallback_detector")
        fallback_used = bool(result.metadata.get("fallback_used", False))
        specialized_conf = float(result.metadata.get("specialized_confidence", result.confidence))
        fallback_conf = float(result.metadata.get("fallback_confidence", 0.0))

        for idx, cand in enumerate(result.candidates):
            asset_id = generate_asset_id(
                source_sha=context.source_sha256,
                category=category,
                detector=detector_name,
                detector_version=detector_ver,
                rect=cand.content_rect_original,
            )

            review_reasons = list(cand.rejection_reasons)
            review_req = cand.review_required
            if source_review_required:
                review_req = True
                review_reasons.append("Source classification requires review")

            if result.confidence < self.detector_confidence_threshold:
                review_req = True
                review_reasons.append(
                    f"Detector confidence {result.confidence:.2f} below threshold {self.detector_confidence_threshold:.2f}"
                )

            asset_meta = {
                "partial_score": cand.partial_score,
                "lock_score": cand.lock_score,
                "content_score": cand.content_score,
                "geometry_score": cand.geometry_score,
                "primary_detector": primary_detector,
                "fallback_detector": fallback_detector,
                "fallback_used": fallback_used,
                "specialized_confidence": specialized_conf,
                "fallback_confidence": fallback_conf,
                **result.metadata,
                **cand.diagnostics,
            }

            asset = DetectedAsset(
                id=asset_id,
                source_id=context.source_id,
                category=category,
                crop_rect=cand.content_rect_original,
                native_width=cand.content_rect_original.w,
                native_height=cand.content_rect_original.h,
                detector=detector_name,
                detector_version=detector_ver,
                confidence=cand.confidence,
                locked=cand.locked,
                partial=cand.partial,
                empty=cand.empty,
                duplicate=False,
                metadata=asset_meta,
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
