"""Unit tests for generic grid detector: candidate discovery, grid reconstruction, and asset creation."""

import cv2
import numpy as np
import pytest

from core.constants import Category
from core.models import Rect
from detectors.detector_models import CardGeometryProfile
from detectors.detection_context import DetectionContext
from detectors.grid_detector import GenericGridDetector
from detectors.generic_detector import GenericDetector


def make_synthetic_grid(w: int = 1280, h: int = 720, rows: int = 2, cols: int = 3) -> np.ndarray:
    """Creates synthetic canvas with dark cards having textured content and borders."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = (180, 180, 180)

    card_w, card_h = 100, 100
    start_x, start_y = 300, 150
    step_x, step_y = 120, 120

    rng = np.random.default_rng(500)

    for r in range(rows):
        cy = start_y + r * step_y
        for c in range(cols):
            cx = start_x + c * step_x
            # Dark background
            img[cy:cy + card_h, cx:cx + card_w] = (35, 30, 25)
            # Texture content inside
            noise = rng.integers(60, 200, size=(card_h - 20, card_w - 20, 3), dtype=np.uint8)
            img[cy + 10:cy + card_h - 10, cx + 10:cx + card_w - 10] = noise
            cv2.rectangle(img, (cx, cy), (cx + card_w, cy + card_h), (80, 80, 80), 2)

    return img


def test_discover_candidates():
    img = make_synthetic_grid(rows=2, cols=3)
    ctx = DetectionContext(img)
    detector = GenericGridDetector()
    profile = CardGeometryProfile()

    candidates = detector.discover_candidates(ctx, profile)
    assert len(candidates) >= 6
    for c in candidates:
        assert isinstance(c, Rect)
        assert c.w > 40
        assert c.h > 40

    ctx.close()


def test_reconstruct_grid_multi_row():
    detector = GenericGridDetector()
    profile = CardGeometryProfile()

    # Create 2 rows x 3 columns of candidate rects
    cands = []
    for r in range(2):
        for c in range(3):
            cands.append(Rect(100 + c * 120, 200 + r * 130, 100, 100))

    # Shuffle to ensure reconstruction handles unordered inputs
    rng = np.random.default_rng(42)
    shuffled = list(cands)
    rng.shuffle(shuffled)

    ordered = detector.reconstruct_grid(shuffled, profile, scan_w=1280, scan_h=720)
    assert len(ordered) == 6

    # Verify rows and columns assignments
    for rect, r_idx, c_idx in ordered:
        assert 0 <= r_idx <= 1
        assert 0 <= c_idx <= 2
        expected_x = 100 + c_idx * 120
        expected_y = 200 + r_idx * 130
        assert rect.x == expected_x
        assert rect.y == expected_y


def test_reconstruct_grid_single_fallback():
    detector = GenericGridDetector()
    profile = CardGeometryProfile(allow_single=True)

    # Single large card (covers >18% of screen)
    single_cand = [Rect(100, 100, 400, 400)]
    ordered = detector.reconstruct_grid(single_cand, profile, scan_w=800, scan_h=800)
    assert len(ordered) == 1
    assert ordered[0][1] == 0
    assert ordered[0][2] == 0


def test_generic_grid_detector_detect_end_to_end():
    img = make_synthetic_grid(rows=2, cols=3)
    ctx = DetectionContext(img)
    detector = GenericGridDetector()

    res = detector.detect(ctx)
    assert res.detected is True
    assert res.rows == 2
    assert res.columns == 3
    assert len(res.candidates) == 6
    assert len(res.accepted) >= 5
    assert res.grid_confidence >= 0.80

    ctx.close()


def test_generic_detector_create_assets_from_candidates():
    img = make_synthetic_grid(rows=1, cols=2)
    ctx = DetectionContext(img, source_id="src_42", source_sha256="deadbeef1234")
    facade = GenericDetector()

    grid_res = facade.detect_grid(ctx)
    assert grid_res.detected is True

    assets = facade.create_assets_from_candidates(
        grid_res.candidates,
        context=ctx,
        category=Category.ITEM_SET.value,
        detector_version="1.0.0",
        source_review_required=False,
    )

    assert len(assets) == len(grid_res.candidates)
    for idx, asset in enumerate(assets):
        assert asset.source_id == "src_42"
        assert asset.category == Category.ITEM_SET.value
        assert asset.order == idx
        assert len(asset.id) == 16
        assert "partial_score" in asset.metadata
        assert "lock" in asset.quality_scores
        assert asset.grid_position[0] == 0

    ctx.close()


def test_reconstruct_grid_shifted_coordinates():
    detector = GenericGridDetector()
    profile = CardGeometryProfile()

    # Shifted grid: offset x + 70, y + 113
    shift_x, shift_y = 70, 113
    cands = []
    for r in range(2):
        for c in range(2):
            cands.append(Rect(shift_x + c * 120, shift_y + r * 125, 100, 100))

    ordered = detector.reconstruct_grid(cands, profile, scan_w=1280, scan_h=720)
    assert len(ordered) == 4
    for rect, r_idx, c_idx in ordered:
        assert rect.x == shift_x + c_idx * 120
        assert rect.y == shift_y + r_idx * 125


def test_reconstruct_grid_missing_cell():
    detector = GenericGridDetector()
    profile = CardGeometryProfile()

    # 3 cards in row 0, 2 cards in row 1 (missing middle cell in row 1)
    # Row 0: c0, c1, c2
    # Row 1: c0, c2 (missing c1)
    cands = [
        Rect(100, 200, 90, 90),
        Rect(220, 200, 90, 90),
        Rect(340, 200, 90, 90),
        Rect(100, 320, 90, 90),
        # missing (220, 320)
        Rect(340, 320, 90, 90),
    ]

    ordered = detector.reconstruct_grid(cands, profile, scan_w=1280, scan_h=720)
    assert len(ordered) == 5
    # Check that missing cell is not faked, existing cards are properly assigned
    row_1_cols = [c_idx for _, r_idx, c_idx in ordered if r_idx == 1]
    assert sorted(row_1_cols) == [0, 2]


def test_generic_grid_detector_random_dark_background_no_grid():
    # Random noisy canvas with no structured rectangular grid
    rng = np.random.default_rng(777)
    noisy_img = rng.integers(20, 70, size=(720, 1280, 3), dtype=np.uint8)

    ctx = DetectionContext(noisy_img)
    detector = GenericGridDetector()
    profile = CardGeometryProfile(allow_single=False)

    res = detector.detect(ctx, profile=profile)
    assert res.detected is False
    assert len(res.candidates) == 0

    ctx.close()

