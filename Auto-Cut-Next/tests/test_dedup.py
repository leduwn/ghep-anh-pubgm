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
