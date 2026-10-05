"""Detectors subsystem for Auto-Cut-Next."""

from .classification_context import ClassificationContext
from .classification_signals import SignalResult
from .screen_classifier import ScreenClassifier
from .detection_context import DetectionContext
from .detector_models import (
    CardGeometryProfile,
    CardCandidate,
    GridDetectionResult,
    SourceDetectionResult,
    SpecializedDetectionResult,
)
from .grid_detector import GenericGridDetector
from .card_quality import CardQualityEvaluator, CardQualityResult, compute_lock_score, compute_content_score
from .dedup import (
    AccountDeduplicator,
    DedupProfile,
    DEFAULT_CATEGORY_DEDUP_PROFILES,
    compute_phash,
    are_visually_identical,
)
from .generic_detector import GenericDetector
from .gun_detector import GunDetector
from .vehicle_detector import VehicleDetector
from .outfit_detector import OutfitDetector
from .equipment_detector import EquipmentDetector
from .accessory_detector import AccessoryDetector
from .inventory_detector import InventoryDetector
from .router import CategoryRouter

__all__ = [
    "ClassificationContext",
    "SignalResult",
    "ScreenClassifier",
    "DetectionContext",
    "CardGeometryProfile",
    "CardCandidate",
    "GridDetectionResult",
    "SourceDetectionResult",
    "SpecializedDetectionResult",
    "GenericGridDetector",
    "CardQualityEvaluator",
    "CardQualityResult",
    "compute_lock_score",
    "compute_content_score",
    "AccountDeduplicator",
    "DedupProfile",
    "DEFAULT_CATEGORY_DEDUP_PROFILES",
    "compute_phash",
    "are_visually_identical",
    "GenericDetector",
    "GunDetector",
    "VehicleDetector",
    "OutfitDetector",
    "EquipmentDetector",
    "AccessoryDetector",
    "InventoryDetector",
    "CategoryRouter",
]
