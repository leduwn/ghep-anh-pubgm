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
)
from .grid_detector import GenericGridDetector
from .card_quality import CardQualityEvaluator, CardQualityResult, compute_lock_score, compute_content_score
from .dedup import AccountDeduplicator, compute_phash, are_visually_identical
from .generic_detector import GenericDetector

__all__ = [
    "ClassificationContext",
    "SignalResult",
    "ScreenClassifier",
    "DetectionContext",
    "CardGeometryProfile",
    "CardCandidate",
    "GridDetectionResult",
    "SourceDetectionResult",
    "GenericGridDetector",
    "CardQualityEvaluator",
    "CardQualityResult",
    "compute_lock_score",
    "compute_content_score",
    "AccountDeduplicator",
    "compute_phash",
    "are_visually_identical",
    "GenericDetector",
]


