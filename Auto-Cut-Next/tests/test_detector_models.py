"""Unit tests for detector data models and detection context coordinate mapping."""

import numpy as np
import pytest

from core.constants import DEFAULT_SCAN_MAX_DIMENSION, DetectionStatus, MISC_GRID_VERSION
from core.models import Rect, generate_asset_id
from core.detection_state import SourceDetectionResult
from detectors.detector_models import (
    CardGeometryProfile,
    CardCandidate,
    GridDetectionResult,
)
from detectors.detection_context import DetectionContext


def test_card_geometry_profile_defaults_and_fingerprint():
    p1 = CardGeometryProfile()
    assert p1.name == "SQUARE_INVENTORY"
    assert p1.aspect_min == 0.60
    assert p1.aspect_max == 1.30
    assert p1.relative_width_min == 0.035
    assert p1.border_inset_ratio == 0.025
    assert p1.allow_single is True
    assert len(p1.fingerprint) == 10

    # Fingerprint determinism
    p2 = CardGeometryProfile()
    assert p1.fingerprint == p2.fingerprint

    # Differing profile yields different fingerprint
    p3 = CardGeometryProfile(aspect_min=0.80)
    assert p1.fingerprint != p3.fingerprint


def test_card_candidate_serialization():
    cand = CardCandidate(
        rect_scan=Rect(10, 20, 100, 120),
        rect_original=Rect(20, 40, 200, 240),
        content_rect_original=Rect(25, 45, 190, 230),
        geometry_score=0.95,
        row=1,
        column=2,
        partial_score=0.05,
        lock_score=0.12,
        content_score=0.88,
        locked=False,
        empty=False,
        partial=False,
        confidence=0.92,
        review_required=False,
        rejection_reasons=[],
        diagnostics={"test_key": "test_val"},
    )

    d = cand.to_dict()
    assert d["row"] == 1
    assert d["column"] == 2
    assert d["rect_scan"]["x"] == 10
    assert d["rect_original"]["w"] == 200
    assert d["diagnostics"]["test_key"] == "test_val"

    rebuilt = CardCandidate.from_dict(d)
    assert rebuilt.row == cand.row
    assert rebuilt.column == cand.column
    assert rebuilt.rect_scan == cand.rect_scan
    assert rebuilt.rect_original == cand.rect_original
    assert rebuilt.content_rect_original == cand.content_rect_original
    assert rebuilt.geometry_score == pytest.approx(cand.geometry_score, 0.001)
    assert rebuilt.confidence == pytest.approx(cand.confidence, 0.001)
    assert rebuilt.locked is False
    assert rebuilt.empty is False


def test_source_detection_result_serialization():
    res = SourceDetectionResult(
        source_id="src_123",
        status=DetectionStatus.SUCCESS.value,
        detector="generic_grid_detector",
        detector_version=MISC_GRID_VERSION,
        card_count=6,
        active_count=4,
        locked_count=1,
        empty_count=1,
        partial_count=0,
        duplicate_count=0,
        review_count=1,
        reasons=["Found 2x3 grid"],
        error_message=None,
        duration_ms=45.2,
    )

    d = res.to_dict()
    assert d["source_id"] == "src_123"
    assert d["status"] == "SUCCESS"
    assert d["card_count"] == 6
    assert d["active_count"] == 4

    rebuilt = SourceDetectionResult.from_dict(d)
    assert rebuilt.source_id == "src_123"
    assert rebuilt.status == DetectionStatus.SUCCESS.value
    assert rebuilt.card_count == 6
    assert rebuilt.locked_count == 1
    assert rebuilt.reasons == ["Found 2x3 grid"]
    assert rebuilt.duration_ms == 45.2


def test_detection_context_scaling_and_mapping():
    # 2778x1284 original image scaled to max_scan_dim=1600
    orig = np.zeros((1284, 2778, 3), dtype=np.uint8)
    ctx = DetectionContext(orig, source_id="s1", source_sha256="abc", max_scan_dim=1600)

    assert ctx.original_w == 2778
    assert ctx.original_h == 1284
    assert ctx.scan_w == 1600
    assert ctx.scan_h == int(round(1284 * (1600 / 2778.0)))

    # Test coordinate mapping: scan to original and back
    scan_r = Rect(100, 50, 200, 150)
    orig_r = ctx.scan_to_original_rect(scan_r)

    assert orig_r.x >= 100
    assert orig_r.w >= 200
    # Map back to scan
    scan_mapped = ctx.original_to_scan_rect(orig_r)
    assert abs(scan_mapped.x - scan_r.x) <= 2
    assert abs(scan_mapped.y - scan_r.y) <= 2
    assert abs(scan_mapped.w - scan_r.w) <= 2
    assert abs(scan_mapped.h - scan_r.h) <= 2

    ctx.close()


def test_detection_context_crop_original_and_scan():
    orig = np.zeros((500, 800, 3), dtype=np.uint8)
    orig[50:150, 100:200] = (255, 128, 64)

    ctx = DetectionContext(orig, max_scan_dim=800)
    crop_orig = ctx.crop_original(Rect(100, 50, 100, 100))
    assert crop_orig.shape == (100, 100, 3)
    assert np.all(crop_orig == (255, 128, 64))

    # Empty / out of bounds crop
    empty_crop = ctx.crop_original(Rect(1000, 1000, 50, 50))
    assert empty_crop.shape == (0, 0, 3)

    ctx.close()


def test_generate_asset_id_determinism():
    base_id = generate_asset_id("sha1", "GUN", "detector", "v1", Rect(10, 20, 30, 40))
    same_id = generate_asset_id("sha1", "GUN", "detector", "v1", Rect(10, 20, 30, 40))
    rect_diff_id = generate_asset_id("sha1", "GUN", "detector", "v1", Rect(10, 20, 31, 40))
    ver_diff_id = generate_asset_id("sha1", "GUN", "detector", "v2", Rect(10, 20, 30, 40))
    cat_diff_id = generate_asset_id("sha1", "HELMET", "detector", "v1", Rect(10, 20, 30, 40))
    sha_diff_id = generate_asset_id("sha2", "GUN", "detector", "v1", Rect(10, 20, 30, 40))

    assert base_id == same_id
    assert base_id != rect_diff_id
    assert base_id != ver_diff_id
    assert base_id != cat_diff_id
    assert base_id != sha_diff_id
    assert len(base_id) == 16
