"""Data models and serialization structures for Auto-Cut-Next."""

from __future__ import annotations

import datetime
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .constants import (
    Category,
    Decision,
    SourceStatus,
    SESSION_SCHEMA_VERSION,
    CLASSIFIER_VERSION,
    GUN_DETECTOR_VERSION,
    MISC_GRID_VERSION,
    OCR_VERSION,
    LAYOUT_VERSION,
    validate_confidence,
)
from .detection_state import SourceDetectionResult
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

    @property
    def is_empty(self) -> bool:
        return self.w == 0 or self.h == 0

    @property
    def is_valid_crop(self) -> bool:
        return self.w > 0 and self.h > 0

    def clamp(self, max_w: int, max_h: int) -> "Rect":
        cx = max(0, min(self.x, max_w))
        cy = max(0, min(self.y, max_h))
        cw = max(0, min(self.w, max_w - cx))
        ch = max(0, min(self.h, max_h - cy))
        return Rect(cx, cy, cw, ch)

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
    decision: str = Decision.AUTO_ACCEPT.value
    reasons: list[str] = field(default_factory=list)
    detector: str = "screen_classifier"
    detector_version: str = CLASSIFIER_VERSION
    signals: dict[str, float] = field(default_factory=dict)
    candidate_category: Optional[str] = None
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    error_message: Optional[str] = None

    def __post_init__(self):
        self.confidence = validate_confidence(self.confidence, "confidence")
        if self.decision not in {d.value for d in Decision}:
            self.decision = Decision.AUTO_ACCEPT.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClassificationResult":
        return cls(
            category=str(data.get("category", Category.OTHER.value)),
            confidence=float(data.get("confidence", 0.0)),
            decision=str(data.get("decision", Decision.AUTO_ACCEPT.value)),
            reasons=list(data.get("reasons", [])),
            detector=str(data.get("detector", "screen_classifier")),
            detector_version=str(data.get("detector_version", CLASSIFIER_VERSION)),
            signals=dict(data.get("signals", {})),
            candidate_category=data.get("candidate_category"),
            alternatives=list(data.get("alternatives", [])),
            duration_ms=float(data.get("duration_ms", 0.0)),
            error_message=data.get("error_message"),
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

    def __post_init__(self):
        self.ocr_confidence = validate_confidence(self.ocr_confidence, "ocr_confidence")

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
    raw_crop_rect: Optional[Rect] = None
    duplicate_of: Optional[str] = None
    quality_scores: dict[str, float] = field(default_factory=dict)
    grid_position: tuple[int, int] = (0, 0)

    def __post_init__(self):
        self.confidence = validate_confidence(self.confidence, "confidence")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["crop_rect"] = self.crop_rect.to_dict()
        if self.raw_crop_rect is not None:
            result["raw_crop_rect"] = self.raw_crop_rect.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectedAsset":
        crop_data = data.get("crop_rect", {})
        rect = Rect.from_dict(crop_data) if isinstance(crop_data, dict) else Rect(0, 0, 0, 0)
        raw_crop_data = data.get("raw_crop_rect")
        raw_rect = Rect.from_dict(raw_crop_data) if isinstance(raw_crop_data, dict) else None
        grid_pos_raw = data.get("grid_position", [0, 0])
        grid_pos = tuple(grid_pos_raw) if isinstance(grid_pos_raw, (list, tuple)) and len(grid_pos_raw) == 2 else (0, 0)

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
            raw_crop_rect=raw_rect,
            duplicate_of=data.get("duplicate_of"),
            quality_scores=dict(data.get("quality_scores", {})),
            grid_position=grid_pos,
        )


def generate_asset_id(source_sha: str, category: str, detector: str, detector_version: str, rect: Rect) -> str:
    """Produces a deterministic, stable identifier for an extracted asset."""
    token = f"{source_sha}:{category}:{detector}:{detector_version}:{rect.x}:{rect.y}:{rect.w}:{rect.h}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]




@dataclass
class AccountSession:
    """Root session state representing a processed PUBG Mobile account."""
    account_id: str
    version: int = SESSION_SCHEMA_VERSION
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    sources: dict[str, SourceImage] = field(default_factory=dict)
    assets: list[DetectedAsset] = field(default_factory=list)
    classifications: dict[str, ClassificationResult] = field(default_factory=dict)
    detections: dict[str, Any] = field(default_factory=dict)
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
    _sha256_to_id: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self.uid_confidence = validate_confidence(self.uid_confidence, "uid_confidence")
        self._rebuild_sha256_index()

    def _rebuild_sha256_index(self) -> None:
        self._sha256_to_id = {src.sha256: src.id for src in self.sources.values() if src.sha256}

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def upsert_source(self, source: SourceImage, force: bool = False) -> tuple[SourceImage, bool]:
        """Adds a new source or refreshes an existing source when force=True.

        Returns:
            tuple[SourceImage, bool]: (source_instance, is_affected)
            is_affected is True if the source was freshly added or forced/refreshed;
            False if it was skipped as an existing duplicate.
        """
        existing_id = self._sha256_to_id.get(source.sha256)
        if existing_id is None:
            # Check for ID collision with differing full SHA-256
            if source.id in self.sources and self.sources[source.id].sha256 != source.sha256:
                source.id = source.sha256[:24]

            self.sources[source.id] = source
            if source.sha256:
                self._sha256_to_id[source.sha256] = source.id
            self.touch()
            return source, True

        existing = self.sources[existing_id]
        if not force:
            return existing, False

        # Force reprocess: refresh source metadata and invalidate derived products
        existing.path = source.path
        existing.filename = source.filename
        existing.mtime = source.mtime
        existing.width = source.width
        existing.height = source.height
        existing.status = source.status
        existing.error_message = source.error_message

        self.invalidate_classification(existing.id)
        self.invalidate_source_products(existing.id)
        self.touch()
        return existing, True

    def invalidate_classification(self, source_id: str) -> bool:
        """Invalidates and removes classification for source_id."""
        if source_id in self.classifications:
            del self.classifications[source_id]
            self.touch()
            return True
        return False

    def add_source(self, source: SourceImage) -> bool:
        """Add source image if SHA-256 not already present. Returns True if added."""
        _, is_new = self.upsert_source(source, force=False)
        return is_new

    def get_source_by_sha256(self, sha256_hash: str) -> Optional[SourceImage]:
        src_id = self._sha256_to_id.get(sha256_hash)
        if src_id and src_id in self.sources:
            return self.sources[src_id]
        return None

    def invalidate_source_products(self, source_id: str, detector: Optional[str] = None) -> int:
        """Invalidates and removes downstream detected assets derived from source_id, optionally filtered by detector."""
        initial_count = len(self.assets)
        if detector:
            self.assets = [a for a in self.assets if not (a.source_id == source_id and a.detector == detector)]
        else:
            self.assets = [a for a in self.assets if a.source_id != source_id]
            if source_id in self.detections:
                del self.detections[source_id]
        removed = initial_count - len(self.assets)
        if removed > 0:
            self.touch()
        return removed

    def invalidate_detection_assets_for_source(
        self,
        source_id: str,
        detector_names: Optional[set[str]] = None,
    ) -> int:
        """Removes stale detection assets for source_id generated by the detection route family.

        Retains manually overridden assets (manual_override=True) and does not delete
        manual history (session.manual_changes) or classifications.
        """
        targets = detector_names if detector_names is not None else {
            "gun_workshop_detector",
            "vehicle_card_detector",
            "outfit_character_detector",
            "equipment_grid_detector",
            "accessory_grid_detector",
            "inventory_grid_detector",
            "generic_grid_detector",
        }
        initial_count = len(self.assets)
        self.assets = [
            a for a in self.assets
            if not (a.source_id == source_id and a.detector in targets and not a.manual_override)
        ]
        removed = initial_count - len(self.assets)
        if removed > 0:
            self.touch()
        return removed

    def remove_assets_for_source(self, source_id: str) -> int:
        """Alias for invalidate_source_products."""
        return self.invalidate_source_products(source_id)

    def add_asset(self, asset: DetectedAsset) -> None:
        self.assets.append(asset)
        self.touch()

    def get_assets_by_category(self, category: str, include_filtered: bool = True) -> list[DetectedAsset]:
        """Returns assets in a given category, optionally including locked/empty/partial items."""
        target = category.upper()
        if include_filtered:
            return [a for a in self.assets if a.category.upper() == target]
        return [
            a for a in self.assets
            if a.category.upper() == target
            and not a.locked and not a.empty and not a.partial and not a.duplicate
        ]

    def get_active_assets_by_category(self, category: str) -> list[DetectedAsset]:
        """Returns only usable (active) assets in a given category."""
        return self.get_assets_by_category(category, include_filtered=False)

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
            "classifications": {k: v.to_dict() for k, v in self.classifications.items()},
            "detections": {k: (v.to_dict() if hasattr(v, "to_dict") else v) for k, v in self.detections.items()},
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

        classifications_raw = data.get("classifications", {})
        classifications = {k: ClassificationResult.from_dict(v) for k, v in classifications_raw.items()}

        detections_raw = data.get("detections", {})
        detections = {}
        for k, v in detections_raw.items():
            if isinstance(v, dict):
                try:
                    detections[k] = SourceDetectionResult.from_dict(v)
                except Exception:
                    detections[k] = v
            else:
                detections[k] = v

        return cls(
            account_id=str(data["account_id"]),
            version=int(data.get("version", SESSION_SCHEMA_VERSION)),
            created_at=str(data.get("created_at", _utc_now_iso())),
            updated_at=str(data.get("updated_at", _utc_now_iso())),
            sources=sources,
            assets=assets,
            classifications=classifications,
            detections=detections,
            uid=data.get("uid"),
            uid_confidence=float(data.get("uid_confidence", 0.0)),
            layout_settings=dict(data.get("layout_settings", {})),
            manual_changes=list(data.get("manual_changes", [])),
            detector_versions=dict(data.get("detector_versions", {})),
            ocr_version=str(data.get("ocr_version", OCR_VERSION)),
        )

