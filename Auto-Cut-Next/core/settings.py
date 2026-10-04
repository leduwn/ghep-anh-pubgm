"""Configuration and settings management for Auto-Cut-Next."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from .constants import (
    DEFAULT_WORKSPACE_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD,
    DEFAULT_CLASSIFIER_REVIEW_THRESHOLD,
    DEFAULT_DETECTOR_CONFIDENCE_THRESHOLD,
    DEFAULT_LOCK_THRESHOLD,
    DEFAULT_EMPTY_DETAIL_THRESHOLD,
    DEFAULT_DUPLICATE_THRESHOLD,
    DEFAULT_MAX_CANVAS_WIDTH,
    DEFAULT_MAX_CANVAS_HEIGHT,
)
from .exceptions import ConfigurationError


@dataclass
class AutoCutSettings:
    """Configurable system-wide settings for Auto-Cut-Next."""
    workspace_dir: Path = field(default_factory=lambda: DEFAULT_WORKSPACE_DIR)
    output_dir: Path = field(default_factory=lambda: DEFAULT_OUTPUT_DIR)
    photoshop_path: Optional[str] = None

    # OCR Settings
    ocr_device: str = "auto"  # "auto", "gpu", "cpu"
    ocr_workers: int = 1

    # Classifier & Detector Thresholds
    classifier_accept_threshold: float = DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD
    classifier_review_threshold: float = DEFAULT_CLASSIFIER_REVIEW_THRESHOLD
    detector_confidence_threshold: float = DEFAULT_DETECTOR_CONFIDENCE_THRESHOLD
    lock_threshold: float = DEFAULT_LOCK_THRESHOLD
    empty_detail_threshold: float = DEFAULT_EMPTY_DETAIL_THRESHOLD
    duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD

    # Layout Settings
    max_output_size: tuple[int, int] = (DEFAULT_MAX_CANVAS_WIDTH, DEFAULT_MAX_CANVAS_HEIGHT)
    default_gun_columns: int = 4
    default_vehicle_rows: int = 2

    # Color & Diagnostics
    auto_color: str = "preview"  # "off", "preview", "photoshop"
    enable_debug: bool = False

    def __post_init__(self):
        self.workspace_dir = Path(self.workspace_dir).resolve()
        self.output_dir = Path(self.output_dir).resolve()
        self.validate()

    def validate(self) -> None:
        if self.ocr_device.lower() not in {"auto", "gpu", "cpu"}:
            raise ConfigurationError(f"Invalid ocr_device: '{self.ocr_device}'.")
        if not (1 <= self.ocr_workers <= 8):
            raise ConfigurationError(f"ocr_workers must be 1..8, got {self.ocr_workers}.")
        for name, val in [
            ("classifier_accept_threshold", self.classifier_accept_threshold),
            ("classifier_review_threshold", self.classifier_review_threshold),
            ("detector_confidence_threshold", self.detector_confidence_threshold),
            ("lock_threshold", self.lock_threshold),
            ("empty_detail_threshold", self.empty_detail_threshold),
            ("duplicate_threshold", self.duplicate_threshold),
        ]:
            if not 0.0 <= val <= 1.0:
                raise ConfigurationError(f"{name} must be in [0.0, 1.0], got {val}.")
        if self.classifier_review_threshold > self.classifier_accept_threshold:
            raise ConfigurationError("classifier_review_threshold > classifier_accept_threshold.")
        if self.auto_color.lower() not in {"off", "preview", "photoshop"}:
            raise ConfigurationError(f"Invalid auto_color mode: '{self.auto_color}'.")
        w, h = self.max_output_size
        if w < 100 or h < 100 or w > 20000 or h > 20000:
            raise ConfigurationError(f"Invalid max_output_size: ({w}, {h}).")

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_dir": str(self.workspace_dir),
            "output_dir": str(self.output_dir),
            "photoshop_path": self.photoshop_path,
            "ocr_device": self.ocr_device,
            "ocr_workers": self.ocr_workers,
            "classifier_accept_threshold": self.classifier_accept_threshold,
            "classifier_review_threshold": self.classifier_review_threshold,
            "detector_confidence_threshold": self.detector_confidence_threshold,
            "lock_threshold": self.lock_threshold,
            "empty_detail_threshold": self.empty_detail_threshold,
            "duplicate_threshold": self.duplicate_threshold,
            "max_output_size": list(self.max_output_size),
            "default_gun_columns": self.default_gun_columns,
            "default_vehicle_rows": self.default_vehicle_rows,
            "auto_color": self.auto_color,
            "enable_debug": self.enable_debug,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutoCutSettings":
        max_size_raw = data.get("max_output_size", [DEFAULT_MAX_CANVAS_WIDTH, DEFAULT_MAX_CANVAS_HEIGHT])
        max_size = (int(max_size_raw[0]), int(max_size_raw[1])) if len(max_size_raw) >= 2 else (DEFAULT_MAX_CANVAS_WIDTH, DEFAULT_MAX_CANVAS_HEIGHT)
        return cls(
            workspace_dir=Path(data.get("workspace_dir", DEFAULT_WORKSPACE_DIR)),
            output_dir=Path(data.get("output_dir", DEFAULT_OUTPUT_DIR)),
            photoshop_path=data.get("photoshop_path"),
            ocr_device=str(data.get("ocr_device", "auto")),
            ocr_workers=int(data.get("ocr_workers", 1)),
            classifier_accept_threshold=float(data.get("classifier_accept_threshold", DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD)),
            classifier_review_threshold=float(data.get("classifier_review_threshold", DEFAULT_CLASSIFIER_REVIEW_THRESHOLD)),
            detector_confidence_threshold=float(data.get("detector_confidence_threshold", DEFAULT_DETECTOR_CONFIDENCE_THRESHOLD)),
            lock_threshold=float(data.get("lock_threshold", DEFAULT_LOCK_THRESHOLD)),
            empty_detail_threshold=float(data.get("empty_detail_threshold", DEFAULT_EMPTY_DETAIL_THRESHOLD)),
            duplicate_threshold=float(data.get("duplicate_threshold", DEFAULT_DUPLICATE_THRESHOLD)),
            max_output_size=max_size,
            default_gun_columns=int(data.get("default_gun_columns", 4)),
            default_vehicle_rows=int(data.get("default_vehicle_rows", 2)),
            auto_color=str(data.get("auto_color", "preview")),
            enable_debug=bool(data.get("enable_debug", False)),
        )

    def save(self, target_path: Union[str, Path]) -> None:
        path = Path(target_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            f.flush()
        temp_path.replace(path)

    @classmethod
    def load(cls, source_path: Union[str, Path]) -> "AutoCutSettings":
        path = Path(source_path).resolve()
        if not path.is_file():
            raise ConfigurationError(f"Settings file not found: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            raise ConfigurationError(f"Failed to load settings from {path}: {e}") from e

