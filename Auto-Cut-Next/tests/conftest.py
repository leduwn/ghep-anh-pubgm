"""Pytest fixtures for Auto-Cut-Next test suite."""

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

# Ensure Auto-Cut-Next root is in sys.path
TESTS_DIR = Path(__file__).resolve().parent
NEXT_ROOT = TESTS_DIR.parent
if str(NEXT_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXT_ROOT))

from core.ingest import write_image_cv2


@pytest.fixture
def temp_workspace(tmp_path):
    """Provides an isolated temporary workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def sample_image_1080p(tmp_path):
    """Creates a synthetic 1920x1080 test image."""
    img_path = tmp_path / "test_1080p.png"
    # Create simple colored canvas with geometric shapes
    canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
    canvas[:, :] = (40, 40, 50)  # dark background
    cv2.rectangle(canvas, (200, 200), (600, 500), (0, 140, 255), -1)
    cv2.putText(canvas, "TEST", (300, 350), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    write_image_cv2(img_path, canvas)
    return img_path


@pytest.fixture
def sample_image_pubg(tmp_path):
    """Creates a synthetic 2778x1284 baseline PUBG test image."""
    img_path = tmp_path / "test_pubg.png"
    canvas = np.zeros((1284, 2778, 3), dtype=np.uint8)
    canvas[:, :] = (30, 28, 35)
    write_image_cv2(img_path, canvas)
    return img_path


@pytest.fixture
def sample_corrupt_file(tmp_path):
    """Creates a corrupted non-image file with a .png extension."""
    corrupt_path = tmp_path / "corrupt.png"
    corrupt_path.write_bytes(b"NOT_A_VALID_IMAGE_DATA_1234567890")
    return corrupt_path


@pytest.fixture
def sample_text_file(tmp_path):
    """Creates a plain text file."""
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("Hello Auto-Cut-Next", encoding="utf-8")
    return txt_path
