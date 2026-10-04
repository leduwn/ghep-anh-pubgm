"""Unit tests for configuration validation and persistence."""

from pathlib import Path
import pytest
from core.exceptions import ConfigurationError
from core.settings import AutoCutSettings


def test_default_settings():
    s = AutoCutSettings()
    assert s.ocr_device == "auto"
    assert s.ocr_workers == 1
    assert s.classifier_accept_threshold == 0.85
    assert s.classifier_review_threshold == 0.55
    assert s.max_output_size == (5000, 5000)
    assert s.default_gun_columns == 4
    assert s.auto_color == "preview"


def test_invalid_settings_rejected():
    with pytest.raises(ConfigurationError):
        AutoCutSettings(ocr_device="invalid_dev")

    with pytest.raises(ConfigurationError):
        AutoCutSettings(ocr_workers=0)

    with pytest.raises(ConfigurationError):
        AutoCutSettings(classifier_accept_threshold=1.5)

    with pytest.raises(ConfigurationError):
        # review threshold cannot be higher than accept
        AutoCutSettings(classifier_accept_threshold=0.5, classifier_review_threshold=0.8)

    with pytest.raises(ConfigurationError):
        AutoCutSettings(max_output_size=(10, 10))


def test_save_and_load_settings(tmp_path):
    settings_file = tmp_path / "custom_settings.json"
    original = AutoCutSettings(
        ocr_device="cpu",
        ocr_workers=2,
        default_gun_columns=5,
        default_vehicle_rows=3,
        enable_debug=True,
    )
    original.save(settings_file)
    assert settings_file.is_file()

    loaded = AutoCutSettings.load(settings_file)
    assert loaded.ocr_device == "cpu"
    assert loaded.ocr_workers == 2
    assert loaded.default_gun_columns == 5
    assert loaded.default_vehicle_rows == 3
    assert loaded.enable_debug is True


def test_load_nonexistent_settings():
    with pytest.raises(ConfigurationError):
        AutoCutSettings.load("nonexistent_path_xyz.json")



def test_settings_relative_path_semantics():
    s = AutoCutSettings(workspace_dir="workspace_rel", output_dir="output_rel")
    from core.constants import DEFAULT_ROOT_DIR
    assert s.workspace_dir == (DEFAULT_ROOT_DIR / "workspace_rel").resolve()
    assert s.output_dir == (DEFAULT_ROOT_DIR / "output_rel").resolve()


def test_settings_load_default():
    s = AutoCutSettings.load_default()
    assert s is not None
    assert s.workspace_dir.is_absolute()
    assert s.default_gun_columns == 4


def test_settings_bounds_validation():
    with pytest.raises(ConfigurationError):
        AutoCutSettings(default_gun_columns=0)
    with pytest.raises(ConfigurationError):
        AutoCutSettings(default_gun_columns=25)
    with pytest.raises(ConfigurationError):
        AutoCutSettings(default_vehicle_rows=0)
    with pytest.raises(ConfigurationError):
        AutoCutSettings(default_vehicle_rows=30)


def test_settings_atomic_save_no_tmp(tmp_path):
    target = tmp_path / "settings.json"
    s = AutoCutSettings()
    s.save(target)
    assert target.is_file()
    assert not target.with_suffix(".tmp").exists()


def test_settings_legacy_migration_and_bounds():
    # 1. Legacy dictionary with duplicate_threshold=0.92 and empty_detail_threshold=0.15
    legacy_data = {
        "duplicate_threshold": 0.92,
        "empty_detail_threshold": 0.15,
        "detector_confidence_threshold": 0.60,
    }
    migrated = AutoCutSettings.from_dict(legacy_data)
    assert migrated.duplicate_mae_threshold == 12.0
    assert migrated.empty_content_threshold == 0.35
    assert migrated.duplicate_phash_max_distance == 10

    # 2. Backward compatibility properties
    assert migrated.duplicate_threshold == 12.0
    assert migrated.empty_detail_threshold == 0.35

    # 3. Explicit modern values preserved
    modern_data = {
        "duplicate_mae_threshold": 15.5,
        "empty_content_threshold": 0.42,
        "duplicate_phash_max_distance": 8,
    }
    modern = AutoCutSettings.from_dict(modern_data)
    assert modern.duplicate_mae_threshold == 15.5
    assert modern.empty_content_threshold == 0.42
    assert modern.duplicate_phash_max_distance == 8

    # 4. Bounds validation
    with pytest.raises(ConfigurationError):
        AutoCutSettings(empty_content_threshold=-0.1)
    with pytest.raises(ConfigurationError):
        AutoCutSettings(empty_content_threshold=1.1)
    with pytest.raises(ConfigurationError):
        AutoCutSettings(duplicate_phash_max_distance=0)
    with pytest.raises(ConfigurationError):
        AutoCutSettings(duplicate_phash_max_distance=65)
    with pytest.raises(ConfigurationError):
        AutoCutSettings(duplicate_mae_threshold=0.0)
    with pytest.raises(ConfigurationError):
        AutoCutSettings(duplicate_mae_threshold=150.0)


