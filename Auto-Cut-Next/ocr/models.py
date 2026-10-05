"""Data structures and observation models for OCR subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from core.models import Rect, validate_confidence


@dataclass
class OCRObservation:
    """Raw observation from OCR engine for a single text fragment."""
    text: str
    box: list[list[float]] = field(default_factory=list)
    confidence: float = 0.0

    def __post_init__(self):
        self.confidence = validate_confidence(self.confidence, "confidence")

    @property
    def bounding_rect(self) -> Rect:
        if not self.box:
            return Rect(0, 0, 0, 0)
        xs = [p[0] for p in self.box]
        ys = [p[1] for p in self.box]
        min_x = int(round(min(xs)))
        min_y = int(round(min(ys)))
        max_x = int(round(max(xs)))
        max_y = int(round(max(ys)))
        return Rect(min_x, min_y, max(0, max_x - min_x), max(0, max_y - min_y))

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "box": self.box,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OCRObservation":
        return cls(
            text=str(data.get("text", "")),
            box=list(data.get("box", [])),
            confidence=float(data.get("confidence", 0.0)),
        )


@dataclass
class OCRFieldResult:
    """Parsed result for a specific semantic field (level, weapon name, counter, etc.)."""
    field_name: str
    value: Any
    confidence: float
    raw_text: str
    source_id: str
    status: str = "ACCEPT"  # "ACCEPT", "REVIEW", "REJECT"
    reasons: list[str] = field(default_factory=list)
    roi: Optional[Rect] = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.confidence = validate_confidence(self.confidence, "confidence")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.roi is not None:
            d["roi"] = self.roi.to_dict()
        return d


@dataclass
class GunOCRResult:
    """Composite OCR extraction result for a weapon asset."""
    level: Optional[int] = None
    level_source: str = "none"  # "progress", "title", "manual", "none"
    weapon_name: Optional[str] = None
    weapon_family: Optional[str] = None
    counter_present: bool = False
    kill_counter: Optional[str] = None
    ocr_confidence: float = 0.0
    level_confidence: float = 0.0
    name_confidence: float = 0.0
    counter_confidence: float = 0.0
    review_required: bool = False
    review_reasons: list[str] = field(default_factory=list)
    raw_level_text: Optional[str] = None
    raw_name_text: Optional[str] = None
    raw_counter_text: Optional[str] = None

    def __post_init__(self):
        self.ocr_confidence = validate_confidence(self.ocr_confidence, "ocr_confidence")
        self.level_confidence = validate_confidence(self.level_confidence, "level_confidence")
        self.name_confidence = validate_confidence(self.name_confidence, "name_confidence")
        self.counter_confidence = validate_confidence(self.counter_confidence, "counter_confidence")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UIDCandidate:
    """Individual UID candidate extracted from a screenshot."""
    uid: str
    confidence: float
    source_id: str
    raw_text: str
    box: list[list[float]] = field(default_factory=list)
    has_label: bool = False
    roi_name: str = "primary"

    def __post_init__(self):
        self.confidence = validate_confidence(self.confidence, "confidence")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UIDCandidate":
        return cls(
            uid=str(data.get("uid", "")),
            confidence=float(data.get("confidence", 0.0)),
            source_id=str(data.get("source_id", "")),
            raw_text=str(data.get("raw_text", "")),
            box=list(data.get("box", [])),
            has_label=bool(data.get("has_label", False)),
            roi_name=str(data.get("roi_name", "primary")),
        )


@dataclass
class UIDConsensusResult:
    """Resolved UID from multi-source cross-validation."""
    uid: Optional[str]
    confidence: float
    candidates: list[UIDCandidate] = field(default_factory=list)
    sources_count: int = 0
    has_conflict: bool = False
    review_required: bool = False
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.confidence = validate_confidence(self.confidence, "confidence")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["candidates"] = [c.to_dict() for c in self.candidates]
        return d
