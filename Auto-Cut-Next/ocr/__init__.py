"""Optical Character Recognition subsystem for Auto-Cut-Next."""

from .cache import OCRCache, build_ocr_cache_key
from .engine import EasyOCREngine, FakeOCREngine, OCREngine
from .gun_ocr import GunOCRExtractor
from .models import (
    GunOCRResult,
    OCRObservation,
    OCRFieldResult,
    UIDCandidate,
    UIDConsensusResult,
)
from .parsers import (
    CANONICAL_WEAPONS,
    parse_gun_level,
    parse_gun_name,
    parse_kill_counter,
    parse_progress_level,
    parse_title_level,
    parse_uid,
)
from .preprocessing import (
    check_counter_badge_presence,
    clamp_roi,
    enhance_text_contrast,
    extract_roi,
)
from .scheduler import OCRScheduler
from .uid_ocr import UIDOCRExtractor, resolve_uid_consensus

__all__ = [
    "OCREngine",
    "EasyOCREngine",
    "FakeOCREngine",
    "OCRCache",
    "build_ocr_cache_key",
    "OCRObservation",
    "OCRFieldResult",
    "GunOCRResult",
    "UIDCandidate",
    "UIDConsensusResult",
    "GunOCRExtractor",
    "UIDOCRExtractor",
    "OCRScheduler",
    "check_counter_badge_presence",
    "clamp_roi",
    "enhance_text_contrast",
    "extract_roi",
    "parse_gun_level",
    "parse_gun_name",
    "parse_kill_counter",
    "parse_progress_level",
    "parse_title_level",
    "parse_uid",
    "resolve_uid_consensus",
    "CANONICAL_WEAPONS",
]
