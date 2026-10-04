"""Core foundation layer for Auto-Cut-Next."""

from .constants import (
    APP_NAME,
    APP_VERSION,
    SESSION_SCHEMA_VERSION,
    CLASSIFIER_VERSION,
    GUN_DETECTOR_VERSION,
    MISC_GRID_VERSION,
    OCR_VERSION,
    LAYOUT_VERSION,
    Category,
    Stage,
    SourceStatus,
    SUPPORTED_IMAGE_EXTENSIONS,
)
from .exceptions import (
    AutoCutError,
    IngestError,
    CorruptImageError,
    PathTraversalError,
    SessionError,
    SessionCorruptError,
    SessionIncompatibleError,
    CacheError,
    ConfigurationError,
)
from .models import (
    Rect,
    SourceImage,
    ClassificationResult,
    GunMetadata,
    VehicleMetadata,
    OutfitMetadata,
    DetectedAsset,
    AccountSession,
)
from .settings import AutoCutSettings
from .logging import StageLogger
from .cache import LRUCache, DiskCache, CacheKeyGenerator
from .metrics import MetricsCollector
from .ingest import ImageIngestor
from .session import WorkspaceManager

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "SESSION_SCHEMA_VERSION",
    "CLASSIFIER_VERSION",
    "GUN_DETECTOR_VERSION",
    "MISC_GRID_VERSION",
    "OCR_VERSION",
    "LAYOUT_VERSION",
    "Category",
    "Stage",
    "SourceStatus",
    "SUPPORTED_IMAGE_EXTENSIONS",
    "AutoCutError",
    "IngestError",
    "CorruptImageError",
    "PathTraversalError",
    "SessionError",
    "SessionCorruptError",
    "SessionIncompatibleError",
    "CacheError",
    "ConfigurationError",
    "Rect",
    "SourceImage",
    "ClassificationResult",
    "GunMetadata",
    "VehicleMetadata",
    "OutfitMetadata",
    "DetectedAsset",
    "AccountSession",
    "AutoCutSettings",
    "StageLogger",
    "LRUCache",
    "DiskCache",
    "CacheKeyGenerator",
    "MetricsCollector",
    "ImageIngestor",
    "WorkspaceManager",
]
