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
