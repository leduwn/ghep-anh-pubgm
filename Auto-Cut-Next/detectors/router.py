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

        return self.generic_grid_detector, GenericGridDetector.NAME, GenericGridDetector.VERSION

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

        conf_thresh = (
            settings.detector_confidence_threshold
            if (settings and hasattr(settings, "detector_confidence_threshold"))
            else self.detector_confidence_threshold
        )

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
                detector_version=GenericGridDetector.VERSION,
                duration_ms=round(duration_ms, 2),
                metadata={
                    "primary_detector": GenericGridDetector.NAME,
                    "fallback_detector": None,
                    "fallback_attempted": False,
                    "fallback_used": False,
                    "specialized_attempted": False,
                    "specialized_success": False,
                    "fallback_success": False,
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
        spec_has_cands = len(spec_res.candidates) > 0
        spec_detected = spec_res.detected and spec_has_cands

        # Case A: Specialized detected and confidence >= threshold -> use specialized directly.
        # Do NOT invoke generic detector (fallback_attempted=False, fallback_used=False).
        if spec_detected and specialized_confidence >= conf_thresh and not spec_res.fallback_recommended:
            spec_res.metadata["primary_detector"] = primary_detector
            spec_res.metadata["fallback_detector"] = None
            spec_res.metadata["fallback_attempted"] = False
            spec_res.metadata["fallback_used"] = False
            spec_res.metadata["specialized_attempted"] = True
            spec_res.metadata["specialized_success"] = True
            spec_res.metadata["fallback_success"] = False
            spec_res.metadata["specialized_confidence"] = round(specialized_confidence, 4)
            spec_res.metadata["fallback_confidence"] = 0.0
            return spec_res

        # Fallback executed for Cases B & C
        fallback_attempted = True
        generic_res = self.generic_grid_detector.detect(context)
        fallback_confidence = generic_res.grid_confidence
        generic_usable = generic_res.detected and len(generic_res.candidates) > 0
        duration_ms = (time.perf_counter() - t0) * 1000.0

        combined_diagnostics = {
            "specialized_diagnostics": spec_res.diagnostics,
            "fallback_diagnostics": generic_res.diagnostics,
        }

        # Case B: Specialized failed or 0 candidates -> run generic fallback.
        # If generic succeeds -> use generic.
        if not spec_detected or spec_res.fallback_recommended:
            if generic_usable:
                fallback_reasons = list(spec_res.reasons)
                fallback_reasons.append(
                    f"Fallback to GenericGridDetector triggered (specialized failed, generic conf: {fallback_confidence:.2f})"
                )
                if cat in {"GUN", "VEHICLE", "OUTFIT"}:
                    fallback_reasons.append(f"Semantic fallback to generic grid for {cat} requires review")
                    for c in generic_res.candidates:
                        c.review_required = True
                        c.rejection_reasons.append(f"Semantic fallback to generic grid for {cat} requires review")

                return SpecializedDetectionResult(
                    detected=True,
                    confidence=generic_res.grid_confidence,
                    candidates=generic_res.candidates,
                    accepted=generic_res.accepted,
                    rejected=generic_res.rejected,
                    reasons=fallback_reasons,
                    diagnostics=combined_diagnostics,
                    fallback_recommended=False,
                    detector_name=GenericGridDetector.NAME,
                    detector_version=GenericGridDetector.VERSION,
                    duration_ms=round(duration_ms, 2),
                    metadata={
                        "primary_detector": primary_detector,
                        "fallback_detector": GenericGridDetector.NAME,
                        "fallback_attempted": True,
                        "fallback_used": True,
                        "specialized_attempted": True,
                        "specialized_success": False,
                        "fallback_success": True,
                        "specialized_confidence": round(specialized_confidence, 4),
                        "fallback_confidence": round(fallback_confidence, 4),
                    },
                )
            else:
                # Both failed
                fail_reasons = list(spec_res.reasons)
                fail_reasons.append(
                    f"Generic fallback also failed (generic conf: {fallback_confidence:.2f})"
                )
                return SpecializedDetectionResult(
                    detected=False,
                    confidence=0.0,
                    candidates=[],
                    accepted=[],
                    rejected=[],
                    reasons=fail_reasons,
                    diagnostics=combined_diagnostics,
                    fallback_recommended=False,
                    detector_name=GenericGridDetector.NAME,
                    detector_version=GenericGridDetector.VERSION,
                    duration_ms=round(duration_ms, 2),
                    metadata={
                        "primary_detector": primary_detector,
                        "fallback_detector": GenericGridDetector.NAME,
                        "fallback_attempted": True,
                        "fallback_used": False,
                        "specialized_attempted": True,
                        "specialized_success": False,
                        "fallback_success": False,
                        "specialized_confidence": round(specialized_confidence, 4),
                        "fallback_confidence": round(fallback_confidence, 4),
                    },
                )

        # Case C: Specialized detected but confidence < threshold -> compare both results.
        # If generic is clearly better: choose generic.
        # If specialized is still better: retain specialized but mark REVIEW.
        # If both are weak: preserve best plausible result and require REVIEW.
        if generic_usable and (fallback_confidence > specialized_confidence):
            # Generic clearly better
            fallback_reasons = list(spec_res.reasons)
            fallback_reasons.append(
                f"Generic fallback selected over weak specialized (specialized conf: {specialized_confidence:.2f} < generic conf: {fallback_confidence:.2f})"
            )
            if cat in {"GUN", "VEHICLE", "OUTFIT"}:
                fallback_reasons.append(f"Semantic fallback to generic grid for {cat} requires review")
                for c in generic_res.candidates:
                    c.review_required = True
                    c.rejection_reasons.append(f"Semantic fallback to generic grid for {cat} requires review")

            return SpecializedDetectionResult(
                detected=True,
                confidence=generic_res.grid_confidence,
                candidates=generic_res.candidates,
                accepted=generic_res.accepted,
                rejected=generic_res.rejected,
                reasons=fallback_reasons,
                diagnostics=combined_diagnostics,
                fallback_recommended=False,
                detector_name=GenericGridDetector.NAME,
                detector_version=GenericGridDetector.VERSION,
                duration_ms=round(duration_ms, 2),
                metadata={
                    "primary_detector": primary_detector,
                    "fallback_detector": GenericGridDetector.NAME,
                    "fallback_attempted": True,
                    "fallback_used": True,
                    "specialized_attempted": True,
                    "specialized_success": True,
                    "fallback_success": True,
                    "specialized_confidence": round(specialized_confidence, 4),
                    "fallback_confidence": round(fallback_confidence, 4),
                },
            )
        else:
            # Retain specialized result (it is better or equal to fallback) but mark REVIEW
            spec_reasons = list(spec_res.reasons)
            spec_reasons.append(
                f"Retained specialized result (conf: {specialized_confidence:.2f}) over fallback (conf: {fallback_confidence:.2f}); review required"
            )
            for c in spec_res.candidates:
                c.review_required = True
                c.rejection_reasons.append(
                    f"Low confidence specialized detection ({specialized_confidence:.2f} < {conf_thresh:.2f})"
                )

            spec_res.reasons = spec_reasons
            spec_res.diagnostics = {**spec_res.diagnostics, **combined_diagnostics}
            spec_res.metadata["primary_detector"] = primary_detector
            spec_res.metadata["fallback_detector"] = GenericGridDetector.NAME
            spec_res.metadata["fallback_attempted"] = True
            spec_res.metadata["fallback_used"] = False
            spec_res.metadata["specialized_attempted"] = True
            spec_res.metadata["specialized_success"] = True
            spec_res.metadata["fallback_success"] = generic_usable
            spec_res.metadata["specialized_confidence"] = round(specialized_confidence, 4)
            spec_res.metadata["fallback_confidence"] = round(fallback_confidence, 4)
            spec_res.metadata["review_required"] = True
            return spec_res

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
        fallback_attempted = bool(result.metadata.get("fallback_attempted", False))
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

            # Semantic fallback review policy: generic grid fallback for GUN, VEHICLE, OUTFIT requires review
            if fallback_used and category.upper() in {"GUN", "VEHICLE", "OUTFIT"}:
                review_req = True
                sem_reason = f"Semantic fallback to generic grid for {category.upper()} requires review"
                if not any("Semantic fallback" in r for r in review_reasons):
                    review_reasons.append(sem_reason)

            asset_meta = {
                "partial_score": cand.partial_score,
                "lock_score": cand.lock_score,
                "content_score": cand.content_score,
                "geometry_score": cand.geometry_score,
                "primary_detector": primary_detector,
                "fallback_detector": fallback_detector,
                "fallback_attempted": fallback_attempted,
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
