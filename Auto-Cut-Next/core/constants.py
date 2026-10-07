"""Constants, versions, and enumeration types for Auto-Cut-Next."""

from enum import Enum
from pathlib import Path
from typing import Any

# Application and Schema Versions
APP_NAME = "Auto-Cut-Next"
APP_VERSION = "0.1.0"
SESSION_SCHEMA_VERSION = 1

# Subsystem Versions (used for cache invalidation)
CLASSIFIER_VERSION = "2.0.0"
GUN_DETECTOR_VERSION = "2.0.0"
VEHICLE_DETECTOR_VERSION = "1.0.0"
OUTFIT_DETECTOR_VERSION = "1.0.0"
EQUIPMENT_DETECTOR_VERSION = "1.0.0"
ACCESSORY_DETECTOR_VERSION = "1.0.0"
INVENTORY_DETECTOR_VERSION = "1.0.0"
ROUTER_VERSION = "1.1.0"
MISC_GRID_VERSION = "2.1.0"
OCR_VERSION = "2.0.0"
LAYOUT_VERSION = "1.0.0"
REVIEW_ENGINE_VERSION = "1.0.0"

# Default paths
DEFAULT_ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE_DIR = DEFAULT_ROOT_DIR / "workspace"
DEFAULT_OUTPUT_DIR = DEFAULT_ROOT_DIR / "output"
DEFAULT_CONFIG_PATH = DEFAULT_ROOT_DIR / "config" / "default_settings.json"

# Supported image formats
SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})


class Category(str, Enum):
    """Normalized category constants."""
    GUN = "GUN"
    VEHICLE = "VEHICLE"
    OUTFIT = "OUTFIT"
    ITEM_SET = "ITEM_SET"
    HELMET = "HELMET"
    BACKPACK = "BACKPACK"
    MASK = "MASK"
    GRENADE = "GRENADE"
    PARACHUTE = "PARACHUTE"
    EMOTE = "EMOTE"
    MISC = "MISC"
    OTHER = "OTHER"

    @classmethod
    def from_str(cls, value: str) -> "Category":
        normalized = value.strip().upper()
        try:
            return cls(normalized)
        except ValueError:
            return cls.OTHER


class Stage(str, Enum):
    """Pipeline execution stages for logging and metrics."""
    INGEST = "INGEST"
    CLASSIFY = "CLASSIFY"
    DETECT = "DETECT"
    FILTER = "FILTER"
    OCR = "OCR"
    REVIEW = "REVIEW"
    LAYOUT = "LAYOUT"
    PHOTOSHOP = "PHOTOSHOP"


class SourceStatus(str, Enum):
    """Source file ingestion status."""
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILED = "FAILED"




class Decision(str, Enum):
    """Categorization confidence decision."""
    AUTO_ACCEPT = "AUTO_ACCEPT"
    REVIEW = "REVIEW"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class DetectionStatus(str, Enum):
    """Detection process status for a source image."""
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    NO_GRID = "NO_GRID"
    REVIEW = "REVIEW"
    ERROR = "ERROR"
    DEFERRED = "DEFERRED"


class ReviewSubsystem(str, Enum):
    """Subsystems that can generate review items."""
    CLASSIFICATION = "CLASSIFICATION"
    DETECTION = "DETECTION"
    ASSET_QUALITY = "ASSET_QUALITY"
    OCR_GUN = "OCR_GUN"
    UID = "UID"


class ReviewStatus(str, Enum):
    """Workflow status for a review item."""
    OPEN = "OPEN"
    RESOLVED_AUTO = "RESOLVED_AUTO"
    RESOLVED_MANUAL = "RESOLVED_MANUAL"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"
    STALE = "STALE"


class ReviewPriority(str, Enum):
    """Deterministic priority levels for review triage."""
    P0 = "P0"  # Pipeline error / unhandled crash
    P1 = "P1"  # UID conflict / unknown classification
    P2 = "P2"  # Semantic fallback / OCR required field uncertain / classification review
    P3 = "P3"  # Asset quality / partial / empty suspected / low confidence non-critical


class ReviewReason(str, Enum):
    """Structured machine reason codes for review items."""
    # Classification
    CLASSIFICATION_LOW_CONFIDENCE = "classification_low_confidence"
    CLASSIFICATION_AMBIGUOUS = "classification_ambiguous"
    CLASSIFICATION_UNKNOWN = "classification_unknown"
    CLASSIFICATION_ERROR = "classification_error"

    # Detection
    SPECIALIZED_DETECTOR_LOW_CONFIDENCE = "specialized_detector_low_confidence"
    GENERIC_FALLBACK_SELECTED = "generic_fallback_selected"
    SEMANTIC_FALLBACK = "semantic_fallback"
    NO_GRID = "no_grid"
    DETECTION_REVIEW = "detection_review"

    # Asset Quality
    PARTIAL_ASSET = "partial_asset"
    LOCKED_ASSET = "locked_asset"
    EMPTY_SUSPECTED = "empty_suspected"
    QUALITY_REVIEW = "quality_review"

    # OCR
    OCR_LEVEL_LOW_CONFIDENCE = "ocr_level_low_confidence"
    OCR_NAME_LOW_CONFIDENCE = "ocr_name_low_confidence"
    OCR_COUNTER_UNCERTAIN = "ocr_counter_uncertain"
    OCR_REVIEW = "ocr_review"

    # UID
    UID_LOW_CONFIDENCE = "uid_low_confidence"
    UID_CONFLICT = "uid_conflict"
    UID_MISSING_LABEL = "uid_missing_label"

    # Pipeline
    PIPELINE_ERROR = "pipeline_error"


# Threshold Defaults
DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD = 0.85
DEFAULT_CLASSIFIER_AMBIGUITY_MARGIN = 0.10
DEFAULT_CLASSIFIER_SCAN_MAX_DIMENSION = 1600

DEFAULT_CLASSIFIER_REVIEW_THRESHOLD = 0.55
DEFAULT_DETECTOR_CONFIDENCE_THRESHOLD = 0.60
DEFAULT_LOCK_THRESHOLD = 0.50
DEFAULT_EMPTY_CONTENT_THRESHOLD = 0.35
DEFAULT_EMPTY_DETAIL_THRESHOLD = 0.35  # Legacy alias
DEFAULT_DUPLICATE_PHASH_MAX_DISTANCE = 10
DEFAULT_DUPLICATE_MAE_THRESHOLD = 12.0
DEFAULT_DUPLICATE_THRESHOLD = 12.0  # Legacy alias

# OCR Threshold Defaults
DEFAULT_OCR_ACCEPT_THRESHOLD = 0.80
DEFAULT_OCR_REVIEW_THRESHOLD = 0.50
DEFAULT_OCR_CACHE_SIZE = 512

# Layout Limits
DEFAULT_MAX_CANVAS_WIDTH = 5000
DEFAULT_MAX_CANVAS_HEIGHT = 5000
DEFAULT_MAX_OUTPUT_SIZE = (DEFAULT_MAX_CANVAS_WIDTH, DEFAULT_MAX_CANVAS_HEIGHT)

# Memory and Cache
DEFAULT_LRU_CACHE_CAPACITY = 512
DEFAULT_THUMBNAIL_MAX_DIMENSION = 320
DEFAULT_SCAN_MAX_DIMENSION = 1600

# Validation Bounds
MIN_COLUMNS = 1
MAX_COLUMNS = 20
MIN_ROWS = 1
MAX_ROWS = 20


def validate_confidence(val: Any, name: str = "confidence") -> float:
    """Validates that a confidence value is a float in [0.0, 1.0] and not NaN/Inf."""
    import math
    try:
        f = float(val)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a real number, got {val!r}") from exc
    if math.isnan(f) or math.isinf(f):
        raise ValueError(f"{name} cannot be NaN or Infinite: {f}")
    if not (0.0 <= f <= 1.0):
        raise ValueError(f"{name} must be in [0.0, 1.0], got {f}")
    return f

