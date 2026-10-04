"""Data models for candidate discovery, grid reconstruction, and detection results."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional

from core.constants import DetectionStatus, MISC_GRID_VERSION
from core.models import Rect
from core.detection_state import SourceDetectionResult


@dataclass(frozen=True)
class CardGeometryProfile:
    """Configurable geometric bounds defining expected card tile characteristics."""
    name: str = "SQUARE_INVENTORY"
    aspect_min: float = 0.60
    aspect_max: float = 1.30
    relative_width_min: float = 0.035
    relative_width_max: float = 0.99
    relative_height_min: float = 0.045
    relative_height_max: float = 0.99
    spacing_min_ratio: float = 0.85
    spacing_max_ratio: float = 1.35
    min_cards: int = 1
    max_cards: Optional[int] = None
    border_inset_ratio: float = 0.025
    allow_single: bool = True

    @property
    def fingerprint(self) -> str:
        """Deterministic fingerprint of geometry bounds for cache invalidation."""
        token = f"{self.name}:{self.aspect_min:.2f}:{self.aspect_max:.2f}:{self.relative_width_min:.3f}:{self.border_inset_ratio:.3f}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


@dataclass
class CardCandidate:
    """Individual card candidate in a reconstructed grid with quality scores and flags."""
    rect_scan: Rect
    rect_original: Rect
    content_rect_original: Rect
    geometry_score: float = 1.0
    row: int = 0
    column: int = 0
    partial_score: float = 0.0
    lock_score: float = 0.0
    content_score: float = 1.0
    locked: bool = False
    empty: bool = False
    partial: bool = False
    confidence: float = 1.0
    review_required: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rect_scan": self.rect_scan.to_dict(),
            "rect_original": self.rect_original.to_dict(),
            "content_rect_original": self.content_rect_original.to_dict(),
            "geometry_score": round(self.geometry_score, 4),
            "row": self.row,
            "column": self.column,
            "partial_score": round(self.partial_score, 4),
            "lock_score": round(self.lock_score, 4),
            "content_score": round(self.content_score, 4),
            "locked": self.locked,
            "empty": self.empty,
            "partial": self.partial,
            "confidence": round(self.confidence, 4),
            "review_required": self.review_required,
            "rejection_reasons": list(self.rejection_reasons),
            "diagnostics": dict(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CardCandidate":
        return cls(
            rect_scan=Rect.from_dict(data.get("rect_scan", {})),
            rect_original=Rect.from_dict(data.get("rect_original", {})),
            content_rect_original=Rect.from_dict(data.get("content_rect_original", {})),
            geometry_score=float(data.get("geometry_score", 1.0)),
            row=int(data.get("row", 0)),
            column=int(data.get("column", 0)),
            partial_score=float(data.get("partial_score", 0.0)),
            lock_score=float(data.get("lock_score", 0.0)),
            content_score=float(data.get("content_score", 1.0)),
            locked=bool(data.get("locked", False)),
            empty=bool(data.get("empty", False)),
            partial=bool(data.get("partial", False)),
            confidence=float(data.get("confidence", 1.0)),
            review_required=bool(data.get("review_required", False)),
            rejection_reasons=list(data.get("rejection_reasons", [])),
            diagnostics=dict(data.get("diagnostics", {})),
        )



@dataclass
class GridDetectionResult:
    """Result of candidate discovery and grid reconstruction."""
    detected: bool
    grid_confidence: float = 0.0
    rows: int = 0
    columns: int = 0
    candidates: list[CardCandidate] = field(default_factory=list)
    accepted: list[CardCandidate] = field(default_factory=list)
    rejected: list[CardCandidate] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


