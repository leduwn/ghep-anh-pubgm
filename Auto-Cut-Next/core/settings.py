"""Configuration and settings management for Auto-Cut-Next."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from .constants import (
    DEFAULT_ROOT_DIR,
    DEFAULT_WORKSPACE_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_CONFIG_PATH,
    DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD,
    DEFAULT_CLASSIFIER_REVIEW_THRESHOLD,
    DEFAULT_CLASSIFIER_AMBIGUITY_MARGIN,
    DEFAULT_CLASSIFIER_SCAN_MAX_DIMENSION,
    DEFAULT_DETECTOR_CONFIDENCE_THRESHOLD,
    DEFAULT_LOCK_THRESHOLD,
    DEFAULT_EMPTY_CONTENT_THRESHOLD,
    DEFAULT_DUPLICATE_PHASH_MAX_DISTANCE,
    DEFAULT_DUPLICATE_MAE_THRESHOLD,
    DEFAULT_MAX_CANVAS_WIDTH,
    DEFAULT_MAX_CANVAS_HEIGHT,
    MIN_COLUMNS,
    MAX_COLUMNS,
    MIN_ROWS,
    MAX_ROWS,
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
    classifier_ambiguity_margin: float = DEFAULT_CLASSIFIER_AMBIGUITY_MARGIN
    classifier_scan_max_dimension: int = DEFAULT_CLASSIFIER_SCAN_MAX_DIMENSION
    detector_confidence_threshold: float = DEFAULT_DETECTOR_CONFIDENCE_THRESHOLD
    lock_threshold: float = DEFAULT_LOCK_THRESHOLD
    empty_content_threshold: float = DEFAULT_EMPTY_CONTENT_THRESHOLD
    duplicate_phash_max_distance: int = DEFAULT_DUPLICATE_PHASH_MAX_DISTANCE
    duplicate_mae_threshold: float = DEFAULT_DUPLICATE_MAE_THRESHOLD

    # Layout Settings
    max_output_size: tuple[int, int] = (DEFAULT_MAX_CANVAS_WIDTH, DEFAULT_MAX_CANVAS_HEIGHT)
    default_gun_columns: int = 4
    default_vehicle_rows: int = 2

    # Color & Diagnostics
    auto_color: str = "preview"  # "off", "preview", "photoshop"
    enable_debug: bool = False

    # Backward-compatibility property aliases
    @property
    def empty_detail_threshold(self) -> float:
        return self.empty_content_threshold

    @empty_detail_threshold.setter
    def empty_detail_threshold(self, val: float) -> None:
        self.empty_content_threshold = val

    @property
    def duplicate_threshold(self) -> float:
        return self.duplicate_mae_threshold

    @duplicate_threshold.setter
    def duplicate_threshold(self, val: float) -> None:
        self.duplicate_mae_threshold = val

    def __post_init__(self):
        # Resolve relative paths against DEFAULT_ROOT_DIR for deterministic behavior
        ws = Path(self.workspace_dir)
        self.workspace_dir = (DEFAULT_ROOT_DIR / ws).resolve() if not ws.is_absolute() else ws.resolve()

        out = Path(self.output_dir)
        self.output_dir = (DEFAULT_ROOT_DIR / out).resolve() if not out.is_absolute() else out.resolve()

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
            ("empty_content_threshold", self.empty_content_threshold),
        ]:
            if not 0.0 <= val <= 1.0:
                raise ConfigurationError(f"{name} must be in [0.0, 1.0], got {val}.")
        if not (0 <= self.duplicate_phash_max_distance <= 64):
            raise ConfigurationError(f"duplicate_phash_max_distance must be in [0, 64], got {self.duplicate_phash_max_distance}.")
        if not (0.1 <= self.duplicate_mae_threshold <= 100.0):
            raise ConfigurationError(f"duplicate_mae_threshold must be in [0.1, 100.0], got {self.duplicate_mae_threshold}.")
        if self.classifier_review_threshold > self.classifier_accept_threshold:
            raise ConfigurationError("classifier_review_threshold > classifier_accept_threshold.")
        if not (0.0 <= self.classifier_ambiguity_margin <= 0.5):
            raise ConfigurationError(f"classifier_ambiguity_margin must be in [0.0, 0.5], got {self.classifier_ambiguity_margin}.")
        if not (400 <= self.classifier_scan_max_dimension <= 4000):
            raise ConfigurationError(f"classifier_scan_max_dimension must be in [400, 4000], got {self.classifier_scan_max_dimension}.")
        if self.auto_color.lower() not in {"off", "preview", "photoshop"}:
            raise ConfigurationError(f"Invalid auto_color mode: '{self.auto_color}'.")
        if not (MIN_COLUMNS <= self.default_gun_columns <= MAX_COLUMNS):
            raise ConfigurationError(f"default_gun_columns must be {MIN_COLUMNS}..{MAX_COLUMNS}, got {self.default_gun_columns}.")
        if not (MIN_ROWS <= self.default_vehicle_rows <= MAX_ROWS):
            raise ConfigurationError(f"default_vehicle_rows must be {MIN_ROWS}..{MAX_ROWS}, got {self.default_vehicle_rows}.")
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
            "classifier_ambiguity_margin": self.classifier_ambiguity_margin,
            "classifier_scan_max_dimension": self.classifier_scan_max_dimension,
            "detector_confidence_threshold": self.detector_confidence_threshold,
            "lock_threshold": self.lock_threshold,
            "empty_content_threshold": self.empty_content_threshold,
            "duplicate_phash_max_distance": self.duplicate_phash_max_distance,
            "duplicate_mae_threshold": self.duplicate_mae_threshold,
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

        # Handle backward compatibility for duplicate thresholds
        dup_mae = DEFAULT_DUPLICATE_MAE_THRESHOLD
        if "duplicate_mae_threshold" in data:
            dup_mae = float(data["duplicate_mae_threshold"])
        elif "duplicate_threshold" in data:
            legacy_val = float(data["duplicate_threshold"])
            # If legacy was normalized 0..1 (like 0.92), migrate safely to new default MAE 12.0
            if legacy_val <= 1.0:
                dup_mae = DEFAULT_DUPLICATE_MAE_THRESHOLD
            else:
                dup_mae = legacy_val

        dup_phash = int(data.get("duplicate_phash_max_distance", DEFAULT_DUPLICATE_PHASH_MAX_DISTANCE))

        # Handle backward compatibility for empty content threshold
        empty_content = DEFAULT_EMPTY_CONTENT_THRESHOLD
        if "empty_content_threshold" in data:
            empty_content = float(data["empty_content_threshold"])
        elif "empty_detail_threshold" in data:
            legacy_val = float(data["empty_detail_threshold"])
            if legacy_val == 0.15:
                empty_content = DEFAULT_EMPTY_CONTENT_THRESHOLD
            else:
                empty_content = legacy_val

        return cls(
            workspace_dir=Path(data.get("workspace_dir", DEFAULT_WORKSPACE_DIR)),
            output_dir=Path(data.get("output_dir", DEFAULT_OUTPUT_DIR)),
            photoshop_path=data.get("photoshop_path"),
            ocr_device=str(data.get("ocr_device", "auto")),
            ocr_workers=int(data.get("ocr_workers", 1)),
            classifier_accept_threshold=float(data.get("classifier_accept_threshold", DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD)),
            classifier_review_threshold=float(data.get("classifier_review_threshold", DEFAULT_CLASSIFIER_REVIEW_THRESHOLD)),
            classifier_ambiguity_margin=float(data.get("classifier_ambiguity_margin", DEFAULT_CLASSIFIER_AMBIGUITY_MARGIN)),
            classifier_scan_max_dimension=int(data.get("classifier_scan_max_dimension", DEFAULT_CLASSIFIER_SCAN_MAX_DIMENSION)),
            detector_confidence_threshold=float(data.get("detector_confidence_threshold", DEFAULT_DETECTOR_CONFIDENCE_THRESHOLD)),
            lock_threshold=float(data.get("lock_threshold", DEFAULT_LOCK_THRESHOLD)),
            empty_content_threshold=empty_content,
            duplicate_phash_max_distance=dup_phash,
            duplicate_mae_threshold=dup_mae,
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
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        except Exception as exc:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise ConfigurationError(f"Failed to atomically save settings to {path}: {exc}") from exc

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

    @classmethod
    def load_default(cls, config_path: Optional[Union[str, Path]] = None) -> "AutoCutSettings":
        """Loads canonical default settings from config/default_settings.json with fallback."""
        target = Path(config_path).resolve() if config_path else DEFAULT_CONFIG_PATH.resolve()
        if target.is_file():
            try:
                return cls.load(target)
            except Exception as exc:
                logging.getLogger("AutoCutNext.settings").warning(
                    f"Failed to load default settings from {target}: {exc}. Using built-in defaults."
                )
        return cls()

