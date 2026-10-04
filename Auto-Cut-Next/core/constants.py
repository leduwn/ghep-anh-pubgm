"""Constants, versions, and enumeration types for Auto-Cut-Next."""

from enum import Enum
from pathlib import Path

# Application and Schema Versions
APP_NAME = "Auto-Cut-Next"
APP_VERSION = "0.1.0"
SESSION_SCHEMA_VERSION = 1

# Subsystem Versions (used for cache invalidation)
CLASSIFIER_VERSION = "1.0.0"
GUN_DETECTOR_VERSION = "1.0.0"
MISC_GRID_VERSION = "1.0.0"
OCR_VERSION = "1.0.0"
LAYOUT_VERSION = "1.0.0"

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


# Threshold Defaults
DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD = 0.85
DEFAULT_CLASSIFIER_REVIEW_THRESHOLD = 0.55
DEFAULT_DETECTOR_CONFIDENCE_THRESHOLD = 0.60
DEFAULT_LOCK_THRESHOLD = 0.50
DEFAULT_EMPTY_DETAIL_THRESHOLD = 0.15
DEFAULT_DUPLICATE_THRESHOLD = 0.92

# Layout Limits
DEFAULT_MAX_CANVAS_WIDTH = 5000
DEFAULT_MAX_CANVAS_HEIGHT = 5000
DEFAULT_MAX_OUTPUT_SIZE = (DEFAULT_MAX_CANVAS_WIDTH, DEFAULT_MAX_CANVAS_HEIGHT)

# Memory and Cache
DEFAULT_LRU_CACHE_CAPACITY = 512
DEFAULT_THUMBNAIL_MAX_DIMENSION = 320
DEFAULT_SCAN_MAX_DIMENSION = 1600
