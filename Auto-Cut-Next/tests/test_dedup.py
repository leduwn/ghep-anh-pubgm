"""Unit tests for perceptual hashing and account-level visual deduplication."""

import cv2
import numpy as np
import pytest

from core.models import DetectedAsset, Rect
from detectors.dedup import (
    AccountDeduplicator,
    compute_phash,
    hamming_distance,
    are_visually_identical,
)


def test_compute_phash_determinism_and_stability():
    rng = np.random.default_rng(100)
    tile1 = rng.integers(50, 200, size=(120, 120, 3), dtype=np.uint8)

    h1 = compute_phash(tile1)
    h2 = compute_phash(tile1)
    assert h1 == h2
    assert isinstance(h1, int)

    # Slight brightness shift should have very small Hamming distance (<= 4)
    tile_shifted = np.clip(tile1.astype(np.int16) + 4, 0, 255).astype(np.uint8)
    h_shifted = compute_phash(tile_shifted)
    dist = hamming_distance(h1, h_shifted)
    assert dist <= 4


def test_hamming_distance():
    assert hamming_distance(0, 0) == 0
    assert hamming_distance(1, 0) == 1
    assert hamming_distance(0b1101, 0b1000) == 2


def test_are_visually_identical():
    rng = np.random.default_rng(200)
    tile_a = rng.integers(60, 180, size=(120, 120, 3), dtype=np.uint8)
    tile_b = np.clip(tile_a.astype(np.int16) + 2, 0, 255).astype(np.uint8)
    tile_diff = rng.integers(60, 180, size=(120, 120, 3), dtype=np.uint8)

    is_dup, mae, dist = are_visually_identical(tile_a, tile_b)
    assert is_dup is True
    assert dist <= 3

    is_dup_diff, mae_diff, dist_diff = are_visually_identical(tile_a, tile_diff)
    assert is_dup_diff is False


def test_account_deduplicator():
    dedup = AccountDeduplicator()

    rng = np.random.default_rng(300)
    tile_helmet_1 = rng.integers(50, 200, size=(100, 100, 3), dtype=np.uint8)
    tile_helmet_dup = np.clip(tile_helmet_1.astype(np.int16) + 1, 0, 255).astype(np.uint8)
    tile_helmet_2 = rng.integers(50, 200, size=(100, 100, 3), dtype=np.uint8)

    a1 = DetectedAsset(
        id="asset_h1",
        source_id="src_1",
        category="HELMET",
        crop_rect=Rect(10, 10, 80, 80),
        native_width=80,
        native_height=80,
        detector="generic_grid_detector",
        detector_version="1.0.0",
        grid_position=(0, 0),
    )
    a2 = DetectedAsset(
        id="asset_h_dup",
        source_id="src_2",
        category="HELMET",
        crop_rect=Rect(10, 10, 80, 80),
        native_width=80,
        native_height=80,
        detector="generic_grid_detector",
        detector_version="1.0.0",
        grid_position=(0, 0),
    )
    a3 = DetectedAsset(
        id="asset_h2",
        source_id="src_2",
        category="HELMET",
        crop_rect=Rect(100, 10, 80, 80),
        native_width=80,
        native_height=80,
        detector="generic_grid_detector",
        detector_version="1.0.0",
        grid_position=(0, 1),
    )

    source_tiles = {
        "asset_h1": tile_helmet_1,
        "asset_h_dup": tile_helmet_dup,
        "asset_h2": tile_helmet_2,
    }
    source_indices = {"src_1": 0, "src_2": 1}

    updated, dup_count = dedup.deduplicate_session_assets(
        [a2, a1, a3],  # unsorted input
        source_tiles=source_tiles,
        source_indices=source_indices,
    )

    assert dup_count == 1
    # Check deterministic ordering: a1 (src_1) is canonical, a2 (src_2) is duplicate
    a1_res = next(a for a in updated if a.id == "asset_h1")
    a2_res = next(a for a in updated if a.id == "asset_h_dup")
    a3_res = next(a for a in updated if a.id == "asset_h2")

    assert a1_res.duplicate is False
    assert a1_res.duplicate_of is None

    assert a2_res.duplicate is True
    assert a2_res.duplicate_of == "asset_h1"

    assert a3_res.duplicate is False


def test_account_deduplicator_category_isolation():
    dedup = AccountDeduplicator()

    rng = np.random.default_rng(400)
    tile_same = rng.integers(50, 200, size=(100, 100, 3), dtype=np.uint8)

    # Identical visual appearance but different categories (HELMET vs BACKPACK)
    a1 = DetectedAsset("a1", "src_1", "HELMET", Rect(10, 10, 80, 80), 80, 80, "det", "1.0")
    a2 = DetectedAsset("a2", "src_2", "BACKPACK", Rect(10, 10, 80, 80), 80, 80, "det", "1.0")

    updated, dup_count = dedup.deduplicate_session_assets(
        [a1, a2],
        source_tiles={"a1": tile_same, "a2": tile_same},
        source_indices={"src_1": 0, "src_2": 1},
    )

    assert dup_count == 0
    assert not updated[0].duplicate
    assert not updated[1].duplicate


def test_dedup_realistic_variants():
    """Validates that real-world image degradations (brightness, JPEG compression, resize) are identified as duplicates."""
    rng = np.random.default_rng(555)
    base_tile = np.zeros((120, 120, 3), dtype=np.uint8)
    base_tile[:, :] = (35, 30, 25)
    # Draw prominent textured helmet icon in center
    cv2.circle(base_tile, (60, 60), 35, (180, 140, 80), -1)
    cv2.rectangle(base_tile, (40, 60), (80, 80), (70, 70, 70), -1)
    noise = rng.integers(-20, 20, size=(50, 50, 3), dtype=np.int16)
    base_tile[35:85, 35:85] = np.clip(base_tile[35:85, 35:85].astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # 1. Brightness shift +2 and +5
    tile_b2 = np.clip(base_tile.astype(np.int16) + 2, 0, 255).astype(np.uint8)
    tile_b5 = np.clip(base_tile.astype(np.int16) + 5, 0, 255).astype(np.uint8)

    # 2. JPEG compression Q95 and Q75
    _, enc_q95 = cv2.imencode(".jpg", base_tile, [cv2.IMWRITE_JPEG_QUALITY, 95])
    tile_q95 = cv2.imdecode(enc_q95, cv2.IMREAD_COLOR)
    _, enc_q75 = cv2.imencode(".jpg", base_tile, [cv2.IMWRITE_JPEG_QUALITY, 75])
    tile_q75 = cv2.imdecode(enc_q75, cv2.IMREAD_COLOR)

    # 3. Downscale and upscale back
    tile_scaled = cv2.resize(cv2.resize(base_tile, (60, 60)), (120, 120), interpolation=cv2.INTER_LINEAR)

    for variant_name, var_tile in [
        ("brightness+2", tile_b2),
        ("brightness+5", tile_b5),
        ("jpeg_q95", tile_q95),
        ("jpeg_q75", tile_q75),
        ("down_up_scale", tile_scaled),
    ]:
        is_dup, mae, dist = are_visually_identical(base_tile, var_tile, diff_threshold=12.0, phash_threshold=10)
        assert is_dup is True, f"Failed dedup on variant {variant_name} (mae={mae}, dist={dist})"


def test_dedup_different_items_no_false_duplicate():
    """Confirms different items sharing dark inventory background and similar dominant tone do not falsely duplicate."""
    # Item A: Yellow Circle (e.g. Helmet)
    tile_a = np.zeros((120, 120, 3), dtype=np.uint8)
    tile_a[:, :] = (35, 30, 25)
    cv2.circle(tile_a, (60, 60), 30, (50, 160, 220), -1)

    # Item B: Yellow Cross (e.g. Grenade/Medkit)
    tile_b = np.zeros((120, 120, 3), dtype=np.uint8)
    tile_b[:, :] = (35, 30, 25)
    cv2.rectangle(tile_b, (50, 30), (70, 90), (50, 160, 220), -1)
    cv2.rectangle(tile_b, (30, 50), (90, 70), (50, 160, 220), -1)

    is_dup, mae, dist = are_visually_identical(tile_a, tile_b, diff_threshold=12.0, phash_threshold=10)
    assert is_dup is False


def test_dedup_filtered_card_does_not_win_over_active_canonical():
    """Confirms that a complete active card becomes canonical even if a partial card was seen in an earlier source."""
    dedup = AccountDeduplicator(diff_threshold=12.0)

    tile = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.circle(tile, (50, 50), 30, (200, 200, 200), -1)

    # Asset 1: from source 1 (seen first), but PARTIAL
    a1_partial = DetectedAsset(
        id="asset_partial_src1",
        source_id="src_1",
        category="ITEM_SET",
        crop_rect=Rect(10, 10, 80, 80),
        native_width=80,
        native_height=80,
        detector="generic_grid_detector",
        detector_version="1.0.0",
        partial=True,
        grid_position=(0, 0),
    )

    # Asset 2: from source 2 (seen later), COMPLETE ACTIVE
    a2_active = DetectedAsset(
        id="asset_active_src2",
        source_id="src_2",
        category="ITEM_SET",
        crop_rect=Rect(10, 10, 80, 80),
        native_width=80,
        native_height=80,
        detector="generic_grid_detector",
        detector_version="1.0.0",
        partial=False,
        grid_position=(0, 0),
    )

    source_tiles = {"asset_partial_src1": tile, "asset_active_src2": tile}
    source_indices = {"src_1": 0, "src_2": 1}

    updated, dup_count = dedup.deduplicate_session_assets(
        [a1_partial, a2_active],
        source_tiles=source_tiles,
        source_indices=source_indices,
    )

    # Active asset from src_2 must be canonical (duplicate=False)
    # Partial asset from src_1 must be marked duplicate of active asset
    res_active = next(a for a in updated if a.id == "asset_active_src2")
    res_partial = next(a for a in updated if a.id == "asset_partial_src1")

    assert res_active.duplicate is False
    assert res_active.duplicate_of is None
    assert res_partial.duplicate is True
    assert res_partial.duplicate_of == "asset_active_src2"


def test_dedup_empty_tile_phash_zero_no_duplicate_chain():
    """Confirms empty tiles do not form false duplicate chains."""
    dedup = AccountDeduplicator()

    empty_tile1 = np.zeros((100, 100, 3), dtype=np.uint8)
    empty_tile1[:, :] = (35, 30, 25)
    empty_tile2 = np.zeros((100, 100, 3), dtype=np.uint8)
    empty_tile2[:, :] = (35, 30, 25)

    a1 = DetectedAsset("empty_1", "src_1", "MISC", Rect(0, 0, 50, 50), 50, 50, "det", "1.0", empty=True)
    a2 = DetectedAsset("empty_2", "src_2", "MISC", Rect(0, 0, 50, 50), 50, 50, "det", "1.0", empty=True)

    updated, dup_count = dedup.deduplicate_session_assets(
        [a1, a2],
        source_tiles={"empty_1": empty_tile1, "empty_2": empty_tile2},
        source_indices={"src_1": 0, "src_2": 1},
    )

    assert dup_count == 0
    assert not updated[0].duplicate
    assert not updated[1].duplicate


def test_dedup_mae_threshold_setting():
    """Validates that varying duplicate_mae_threshold directly controls duplicate decision."""
    tile_a = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.circle(tile_a, (50, 50), 30, (180, 180, 180), -1)

    # Add moderate noise to create difference
    tile_b = tile_a.copy()
    tile_b[30:70, 30:70] = np.clip(tile_b[30:70, 30:70].astype(np.int16) + 15, 0, 255).astype(np.uint8)

    # Tight MAE (e.g. 5.0) -> Not duplicate
    is_dup_strict, mae, _ = are_visually_identical(tile_a, tile_b, diff_threshold=5.0)
    assert is_dup_strict is False

    # Relaxed MAE (e.g. 25.0) -> Duplicate
    is_dup_relaxed, _, _ = are_visually_identical(tile_a, tile_b, diff_threshold=25.0)
    assert is_dup_relaxed is True
