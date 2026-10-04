"""Data models and serialization structures for Auto-Cut-Next."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .constants import (
    Category,
    SourceStatus,
    SESSION_SCHEMA_VERSION,
    CLASSIFIER_VERSION,
    GUN_DETECTOR_VERSION,
    MISC_GRID_VERSION,
    OCR_VERSION,
    LAYOUT_VERSION,
)
from .exceptions import SessionCorruptError


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass(frozen=True)
class Rect:
    """Immutable 2D bounding rectangle in pixel coordinates."""
    x: int
    y: int
    w: int
    h: int

    def __post_init__(self):
        if self.w < 0 or self.h < 0:
            raise ValueError(f"Rect w/h must be non-negative: w={self.w}, h={self.h}")

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def aspect_ratio(self) -> float:
        return float(self.w) / float(self.h) if self.h > 0 else 0.0

    def intersection(self, other: "Rect") -> Optional["Rect"]:
        ix1 = max(self.x, other.x)
        iy1 = max(self.y, other.y)
        ix2 = min(self.right, other.right)
        iy2 = min(self.bottom, other.bottom)
        if ix2 > ix1 and iy2 > iy1:
            return Rect(ix1, iy1, ix2 - ix1, iy2 - iy1)
        return None

    def iou(self, other: "Rect") -> float:
        inter = self.intersection(other)
        if inter is None or inter.area == 0:
            return 0.0
        union_area = self.area + other.area - inter.area
        return inter.area / union_area if union_area > 0 else 0.0

    def scale(self, scale_x: float, scale_y: float) -> "Rect":
        return Rect(
            x=round(self.x * scale_x),
            y=round(self.y * scale_y),
            w=max(0, round(self.w * scale_x)),
            h=max(0, round(self.h * scale_y)),
        )

    def to_dict(self) -> dict[str, int]:
        return {"x": int(self.x), "y": int(self.y), "w": int(self.w), "h": int(self.h)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rect":
        return cls(
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            w=int(data.get("w", 0)),
            h=int(data.get("h", 0)),
        )


@dataclass
class SourceImage:
    """Metadata describing an ingested screenshot source."""
    id: str
    path: str
    sha256: str
    filename: str
    width: int
    height: int
    mtime: float
    source_index: int
    status: str = SourceStatus.SUCCESS.value
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceImage":
        return cls(
            id=str(data["id"]),
            path=str(data["path"]),
            sha256=str(data["sha256"]),
            filename=str(data["filename"]),
            width=int(data["width"]),
            height=int(data["height"]),
            mtime=float(data["mtime"]),
            source_index=int(data["source_index"]),
            status=str(data.get("status", SourceStatus.SUCCESS.value)),
            error_message=data.get("error_message"),
        )



@dataclass
class ClassificationResult:
    """Detailed result of screen categorization."""
    category: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    detector: str = "screen_classifier"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassificationResult":
        return cls(
            category=str(data.get("category", Category.OTHER.value)),
            confidence=float(data.get("confidence", 0.0)),
            reasons=list(data.get("reasons", [])),
            detector=str(data.get("detector", "screen_classifier")),
        )


@dataclass
class GunMetadata:
    """Specialized metadata for weapon cards."""
    level: Optional[int] = None
    weapon_name: Optional[str] = None
    weapon_family: Optional[str] = None
    kill_counter: Optional[str] = None
    badge: Optional[str] = None
    ocr_confidence: float = 0.0
    level_manual: Optional[int] = None
    name_manual: Optional[str] = None

    @property
    def effective_level(self) -> Optional[int]:
        return self.level_manual if self.level_manual is not None else self.level

    @property
    def effective_name(self) -> Optional[str]:
        return self.name_manual if self.name_manual is not None else self.weapon_name

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GunMetadata":
        return cls(
            level=data.get("level"),
            weapon_name=data.get("weapon_name"),
            weapon_family=data.get("weapon_family"),
            kill_counter=data.get("kill_counter"),
            badge=data.get("badge"),
            ocr_confidence=float(data.get("ocr_confidence", 0.0)),
            level_manual=data.get("level_manual"),
            name_manual=data.get("name_manual"),
        )


@dataclass
class VehicleMetadata:
    """Specialized metadata for vehicle cards."""
    ticket_count: int = 1
    vip: bool = False
    label: Optional[str] = None
    manual_order: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VehicleMetadata":
        return cls(
            ticket_count=int(data.get("ticket_count", 1)),
            vip=bool(data.get("vip", False)),
            label=data.get("label"),
            manual_order=data.get("manual_order"),
        )


@dataclass
class OutfitMetadata:
    """Specialized metadata for outfit / suit items."""
    stars: int = 0
    vip: bool = False
    priority: bool = False
    label: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutfitMetadata":
        return cls(
            stars=int(data.get("stars", 0)),
            vip=bool(data.get("vip", False)),
            priority=bool(data.get("priority", False)),
            label=data.get("label"),
        )


@dataclass
class DetectedAsset:
    """Logical asset extracted from a screenshot with crop and classification."""
    id: str
    source_id: str
    category: str
    crop_rect: Rect
    native_width: int
    native_height: int
    detector: str
    detector_version: str
    confidence: float = 1.0
    locked: bool = False
    partial: bool = False
    empty: bool = False
    duplicate: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    manual_override: bool = False
    review_required: bool = False
    review_reasons: list[str] = field(default_factory=list)
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["crop_rect"] = self.crop_rect.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectedAsset":
        crop_data = data.get("crop_rect", {})
        rect = Rect.from_dict(crop_data) if isinstance(crop_data, dict) else Rect(0, 0, 0, 0)
        return cls(
            id=str(data["id"]),
            source_id=str(data["source_id"]),
            category=str(data.get("category", Category.OTHER.value)),
            crop_rect=rect,
            native_width=int(data.get("native_width", rect.w)),
            native_height=int(data.get("native_height", rect.h)),
            detector=str(data.get("detector", "unknown")),
            detector_version=str(data.get("detector_version", "1.0.0")),
            confidence=float(data.get("confidence", 1.0)),
            locked=bool(data.get("locked", False)),
            partial=bool(data.get("partial", False)),
            empty=bool(data.get("empty", False)),
            duplicate=bool(data.get("duplicate", False)),
            metadata=dict(data.get("metadata", {})),
            manual_override=bool(data.get("manual_override", False)),
            review_required=bool(data.get("review_required", False)),
            review_reasons=list(data.get("review_reasons", [])),
            order=int(data.get("order", 0)),
        )



@dataclass
class AccountSession:
    """Root session state representing a processed PUBG Mobile account."""
    account_id: str
    version: int = SESSION_SCHEMA_VERSION
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    sources: dict[str, SourceImage] = field(default_factory=dict)
    assets: list[DetectedAsset] = field(default_factory=list)
    uid: Optional[str] = None
    uid_confidence: float = 0.0
    layout_settings: dict[str, Any] = field(default_factory=dict)
    manual_changes: list[dict[str, Any]] = field(default_factory=list)
    detector_versions: dict[str, str] = field(default_factory=lambda: {
        "classifier": CLASSIFIER_VERSION,
        "gun_detector": GUN_DETECTOR_VERSION,
        "misc_grid": MISC_GRID_VERSION,
        "layout": LAYOUT_VERSION,
    })
    ocr_version: str = OCR_VERSION

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def add_source(self, source: SourceImage) -> bool:
        """Add source image if SHA-256 not already present. Returns True if added."""
        for existing in self.sources.values():
            if existing.sha256 == source.sha256:
                return False
        self.sources[source.id] = source
        self.touch()
        return True

    def get_source_by_sha256(self, sha256_hash: str) -> Optional[SourceImage]:
        for src in self.sources.values():
            if src.sha256 == sha256_hash:
                return src
        return None

    def add_asset(self, asset: DetectedAsset) -> None:
        self.assets.append(asset)
        self.touch()

    def get_assets_by_category(self, category: str) -> list[DetectedAsset]:
        target = category.upper()
        return [
            a for a in self.assets
            if a.category.upper() == target
            and not a.locked and not a.empty and not a.partial and not a.duplicate
        ]

    def record_manual_change(self, action: str, details: dict[str, Any]) -> None:
        change_record = {
            "id": uuid.uuid4().hex,
            "timestamp": _utc_now_iso(),
            "action": action,
            "details": details,
        }
        self.manual_changes.append(change_record)
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "account_id": self.account_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "assets": [a.to_dict() for a in self.assets],
            "uid": self.uid,
            "uid_confidence": self.uid_confidence,
            "layout_settings": self.layout_settings,
            "manual_changes": self.manual_changes,
            "detector_versions": self.detector_versions,
            "ocr_version": self.ocr_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountSession":
        if "account_id" not in data:
            raise SessionCorruptError("Session data missing required 'account_id' field.")

        sources_raw = data.get("sources", {})
        sources = {k: SourceImage.from_dict(v) for k, v in sources_raw.items()}

        assets_raw = data.get("assets", [])
        assets = [DetectedAsset.from_dict(a) for a in assets_raw]

        return cls(
            account_id=str(data["account_id"]),
            version=int(data.get("version", SESSION_SCHEMA_VERSION)),
            created_at=str(data.get("created_at", _utc_now_iso())),
            updated_at=str(data.get("updated_at", _utc_now_iso())),
            sources=sources,
            assets=assets,
            uid=data.get("uid"),
            uid_confidence=float(data.get("uid_confidence", 0.0)),
            layout_settings=dict(data.get("layout_settings", {})),
            manual_changes=list(data.get("manual_changes", [])),
            detector_versions=dict(data.get("detector_versions", {})),
            ocr_version=str(data.get("ocr_version", OCR_VERSION)),
        )

