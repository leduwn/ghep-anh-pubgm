"""Persisted source-level detection status and summary in AccountSession."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .constants import DetectionStatus, MISC_GRID_VERSION


@dataclass
class SourceDetectionResult:
    """Persisted source-level detection status and summary in AccountSession."""
    source_id: str
    status: str = DetectionStatus.PENDING.value
    detector: str = "generic_grid_detector"
    detector_version: str = MISC_GRID_VERSION
    primary_detector: Optional[str] = None
    fallback_detector: Optional[str] = None
    fallback_attempted: bool = False
    fallback_used: bool = False
    confidence: float = 0.0
    specialized_attempted: bool = False
    specialized_confidence: float = 0.0
    fallback_confidence: float = 0.0
    card_count: int = 0
    active_count: int = 0
    locked_count: int = 0
    empty_count: int = 0
    partial_count: int = 0
    duplicate_count: int = 0
    review_count: int = 0
    reasons: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "detector": self.detector,
            "detector_version": self.detector_version,
            "primary_detector": self.primary_detector,
            "fallback_detector": self.fallback_detector,
            "fallback_attempted": self.fallback_attempted,
            "fallback_used": self.fallback_used,
            "confidence": round(self.confidence, 4),
            "specialized_attempted": self.specialized_attempted,
            "specialized_confidence": round(self.specialized_confidence, 4),
            "fallback_confidence": round(self.fallback_confidence, 4),
            "card_count": self.card_count,
            "active_count": self.active_count,
            "locked_count": self.locked_count,
            "empty_count": self.empty_count,
            "partial_count": self.partial_count,
            "duplicate_count": self.duplicate_count,
            "review_count": self.review_count,
            "reasons": list(self.reasons),
            "error_message": self.error_message,
            "duration_ms": round(self.duration_ms, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceDetectionResult":
        fallback_used = bool(data.get("fallback_used", False))
        spec_conf = float(data.get("specialized_confidence", 0.0))
        fb_conf = float(data.get("fallback_confidence", 0.0))
        default_conf = fb_conf if fallback_used else spec_conf

        conf = float(data.get("confidence", default_conf))
        spec_att = bool(
            data.get(
                "specialized_attempted",
                bool(data.get("primary_detector") and data.get("primary_detector") != "generic_grid_detector")
                or spec_conf > 0.0,
            )
        )

        return cls(
            source_id=str(data.get("source_id", "")),
            status=str(data.get("status", DetectionStatus.PENDING.value)),
            detector=str(data.get("detector", "generic_grid_detector")),
            detector_version=str(data.get("detector_version", MISC_GRID_VERSION)),
            primary_detector=data.get("primary_detector"),
            fallback_detector=data.get("fallback_detector"),
            fallback_attempted=bool(data.get("fallback_attempted", False)),
            fallback_used=fallback_used,
            confidence=conf,
            specialized_attempted=spec_att,
            specialized_confidence=spec_conf,
            fallback_confidence=fb_conf,
            card_count=int(data.get("card_count", 0)),
            active_count=int(data.get("active_count", 0)),
            locked_count=int(data.get("locked_count", 0)),
            empty_count=int(data.get("empty_count", 0)),
            partial_count=int(data.get("partial_count", 0)),
            duplicate_count=int(data.get("duplicate_count", 0)),
            review_count=int(data.get("review_count", 0)),
            reasons=list(data.get("reasons", [])),
            error_message=data.get("error_message"),
            duration_ms=float(data.get("duration_ms", 0.0)),
        )
