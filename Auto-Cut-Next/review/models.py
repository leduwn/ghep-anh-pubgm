"""Data models for review items, resolutions, and audit tracking."""

from __future__ import annotations

import datetime
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from core.constants import (
    ReviewSubsystem,
    ReviewStatus,
    ReviewPriority,
    ReviewReason,
    validate_confidence,
)
from core.serialization import to_json_native


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def make_classification_review_id(source_id: str) -> str:
    """Deterministic review item ID for screen classification."""
    return f"review:{source_id}:classification"


def make_detection_review_id(source_id: str) -> str:
    """Deterministic review item ID for source-level card detection."""
    return f"review:{source_id}:detection"


def make_asset_quality_review_id(asset_id: str, reason: str) -> str:
    """Deterministic review item ID for asset quality condition."""
    return f"review:{asset_id}:quality:{reason}"


def make_ocr_review_id(asset_id: str, field_name: str) -> str:
    """Deterministic review item ID for field-level OCR extraction."""
    return f"review:{asset_id}:ocr:{field_name}"


def make_uid_review_id(account_id: str) -> str:
    """Deterministic review item ID for account-level UID consensus."""
    return f"review:{account_id}:uid"


def compute_machine_fingerprint(
    subsystem_version: str,
    value: Any,
    confidence: float,
    reason: str,
    extra_token: str = "",
) -> str:
    """Computes a deterministic hash fingerprint of the machine output.

    Used to detect if machine state materially changed after user accepted it.
    """
    token = f"{subsystem_version}|{value}|{confidence:.4f}|{reason}|{extra_token}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


@dataclass
class ReviewResolution:
    """Resolution details recorded when a review item is acted upon."""
    action: str  # "accept_machine", "set_category", "set_level", "set_name", "set_counter", "clear_counter", "set_uid", "reject", "skip", etc.
    resolved_by: str = "manual"  # "manual" or "auto"
    resolved_at: str = field(default_factory=_utc_now_iso)
    value: Any = None
    notes: Optional[str] = None
    subsystem_version: str = ""
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return to_json_native(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewResolution":
        return cls(
            action=str(data.get("action", "")),
            resolved_by=str(data.get("resolved_by", "manual")),
            resolved_at=str(data.get("resolved_at", _utc_now_iso())),
            value=data.get("value"),
            notes=data.get("notes"),
            subsystem_version=str(data.get("subsystem_version", "")),
            fingerprint=str(data.get("fingerprint", "")),
        )


@dataclass
class ReviewAction:
    """Lightweight audit trail entry for manual corrections and decisions."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=_utc_now_iso)
    review_item_id: str = ""
    action: str = ""
    old_value: Any = None
    new_value: Any = None
    source: str = "manual"
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return to_json_native(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewAction":
        return cls(
            id=str(data.get("id", uuid.uuid4().hex[:12])),
            timestamp=str(data.get("timestamp", _utc_now_iso())),
            review_item_id=str(data.get("review_item_id", "")),
            action=str(data.get("action", "")),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            source=str(data.get("source", "manual")),
            notes=data.get("notes"),
        )


@dataclass
class ReviewItem:
    """Individual typed review task consolidated into the review queue."""
    id: str
    subsystem: str  # ReviewSubsystem enum value
    status: str = ReviewStatus.OPEN.value  # ReviewStatus enum value
    priority: str = ReviewPriority.P2.value  # ReviewPriority enum value
    reason: str = ReviewReason.QUALITY_REVIEW.value  # ReviewReason enum value
    message: str = ""
    source_id: Optional[str] = None
    asset_id: Optional[str] = None
    category: Optional[str] = None
    field_name: Optional[str] = None
    confidence: float = 0.0
    machine_value: Any = None
    candidates: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    resolution: Optional[ReviewResolution] = None
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    order_index: int = 0

    def __post_init__(self):
        self.confidence = validate_confidence(self.confidence, "confidence")

    @property
    def is_open(self) -> bool:
        return self.status == ReviewStatus.OPEN.value

    @property
    def is_resolved(self) -> bool:
        return self.status in {
            ReviewStatus.RESOLVED_AUTO.value,
            ReviewStatus.RESOLVED_MANUAL.value,
            ReviewStatus.REJECTED.value,
            ReviewStatus.SKIPPED.value,
        }

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.resolution is not None:
            data["resolution"] = self.resolution.to_dict()
        return to_json_native(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewItem":
        res_data = data.get("resolution")
        resolution = ReviewResolution.from_dict(res_data) if isinstance(res_data, dict) else None
        return cls(
            id=str(data["id"]),
            subsystem=str(data.get("subsystem", ReviewSubsystem.ASSET_QUALITY.value)),
            status=str(data.get("status", ReviewStatus.OPEN.value)),
            priority=str(data.get("priority", ReviewPriority.P2.value)),
            reason=str(data.get("reason", ReviewReason.QUALITY_REVIEW.value)),
            message=str(data.get("message", "")),
            source_id=data.get("source_id"),
            asset_id=data.get("asset_id"),
            category=data.get("category"),
            field_name=data.get("field_name"),
            confidence=float(data.get("confidence", 0.0)),
            machine_value=data.get("machine_value"),
            candidates=list(data.get("candidates", [])),
            metadata=dict(data.get("metadata", {})),
            fingerprint=str(data.get("fingerprint", "")),
            resolution=resolution,
            created_at=str(data.get("created_at", _utc_now_iso())),
            updated_at=str(data.get("updated_at", _utc_now_iso())),
            order_index=int(data.get("order_index", 0)),
        )
