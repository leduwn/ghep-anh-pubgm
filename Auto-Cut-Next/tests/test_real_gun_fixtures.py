"""Tests for GunDetector against real PUBG Gun Lab screenshots in Cắt/input.

READ-ONLY on Cắt/input. Skips cleanly if Cắt/input is absent.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

# Ensure Auto-Cut-Next root is on sys.path
TESTS_DIR = Path(__file__).resolve().parent
NEXT_ROOT = TESTS_DIR.parent
if str(NEXT_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXT_ROOT))

from core.constants import Category, GUN_DETECTOR_VERSION
from core.ingest import read_image_cv2
from core.models import Rect
from core.session import WorkspaceManager
from app.pipeline import AutoCutPipeline
from detectors.detection_context import DetectionContext
from detectors.gun_detector import GunDetector
from detectors.router import CategoryRouter
from ocr.gun_ocr import resolve_gun_rois

REPO_ROOT = NEXT_ROOT.parent
REAL_INPUT_DIR = REPO_ROOT / "Cắt" / "input"


@pytest.fixture(scope="module")
def real_gun_files(tmp_path_factory):
    """Discovers real Gun Lab screenshots in Cắt/input via production AutoCutPipeline."""
    if not REAL_INPUT_DIR.is_dir():
        pytest.skip(f"No real Gun Lab screenshots found in {REAL_INPUT_DIR}")

    extensions = {".png", ".jpg", ".jpeg"}
    all_images = [
        f for f in sorted(REAL_INPUT_DIR.iterdir(), key=lambda p: p.name)
        if f.is_file() and f.suffix.lower() in extensions
    ]
    if not all_images:
        pytest.skip(f"No supported images found in {REAL_INPUT_DIR}")

    temp_ws_dir = tmp_path_factory.mktemp("gun_fixture_ws")
    ws = WorkspaceManager(temp_ws_dir)
    pipeline = AutoCutPipeline(workspace=ws)
    account_id = "real_gun_fixture_test"

    session = pipeline.ingest_sources(account_id, all_images)
    session = pipeline.classify_session(account_id)

    gun_files: list[Path] = []
    for s_id, src in sorted(session.sources.items(), key=lambda item: item[1].filename):
        cl = session.classifications.get(s_id)
        if cl and cl.category == Category.GUN.value:
            gun_files.append(Path(src.path))

    if not gun_files:
        pytest.skip(f"No GUN classified screenshots found in {REAL_INPUT_DIR}")

    return gun_files


def test_real_gun_fixtures_detection_coverage(real_gun_files):
    """Verifies that GunDetector achieves >= 90% specialized detection on real Gun Lab screenshots."""
    detector = GunDetector()
    router = CategoryRouter()
    detected_count = 0
    total_count = len(real_gun_files)

    assert total_count == 23, f"Expected exactly 23 real GUN screenshots, found {total_count}"

    for img_path in real_gun_files:
        img_bgr = read_image_cv2(img_path)
        assert img_bgr is not None, f"Failed to read {img_path.name}"
        orig_h, orig_w = img_bgr.shape[:2]

        ctx = DetectionContext(img_bgr, source_id=img_path.stem)
        res = detector.detect(ctx)

        if res.detected:
            detected_count += 1
            assert res.detector_name == "gun_workshop_detector"
            assert res.detector_version == GUN_DETECTOR_VERSION

            # Must enforce exactly 1 valid logical Gun asset
            assert len(res.candidates) == 1, f"{img_path.name}: expected 1 candidate, got {len(res.candidates)}"
            assert len(res.accepted) == 1, f"{img_path.name}: expected 1 accepted candidate"
            assert len(res.rejected) == 0, f"{img_path.name}: expected 0 rejected candidates"

            cand = res.candidates[0]
            assert cand.geometry_score >= 0.8
            assert cand.content_score >= 0.20
            assert not cand.empty
            assert not cand.locked
            assert not cand.partial

            # Crop rect must be well-formed and inside native bounds
            content_rect = cand.content_rect_original
            assert 0 <= content_rect.x < orig_w
            assert 0 <= content_rect.y < orig_h
            assert content_rect.right <= orig_w
            assert content_rect.bottom <= orig_h
            assert content_rect.w >= int(round(orig_w * 0.10))
            assert content_rect.h >= int(round(orig_h * 0.08))

            # Transform into canonical DetectedAsset and verify properties
            assets = router.create_assets_from_result(res, ctx, category=Category.GUN.value)
            assert len(assets) == 1, f"{img_path.name}: expected 1 detected asset"
            asset = assets[0]
            assert asset.category == Category.GUN.value
            assert asset.detector == "gun_workshop_detector"
            assert asset.detector_version == GUN_DETECTOR_VERSION
            assert not asset.empty
            assert not asset.locked
            assert not asset.partial
            assert not asset.duplicate

            # Metadata ROIs must be non-empty and inside image bounds
            assert "level_roi" in res.metadata
            assert "name_roi" in res.metadata
            assert "kill_counter_roi" in res.metadata

            lvl_roi, nm_roi, cnt_roi = resolve_gun_rois(asset, (orig_h, orig_w))

            assert 0 <= lvl_roi.x and lvl_roi.right <= orig_w
            assert 0 <= lvl_roi.y and lvl_roi.bottom <= orig_h
            assert lvl_roi.w > 0 and lvl_roi.h > 0

            assert 0 <= nm_roi.x and nm_roi.right <= orig_w
            assert 0 <= nm_roi.y and nm_roi.bottom <= orig_h
            assert nm_roi.w > 0 and nm_roi.h > 0

            assert 0 <= cnt_roi.x and cnt_roi.right <= orig_w
            assert 0 <= cnt_roi.y and cnt_roi.bottom <= orig_h
            assert cnt_roi.w > 0 and cnt_roi.h > 0

        ctx.close()

    coverage = float(detected_count) / float(total_count)
    assert coverage >= 0.90, f"Detection coverage {coverage:.1%} ({detected_count}/{total_count}) is below 90%"


def test_real_gun_fixtures_detector_metadata(real_gun_files):
    """Verifies detector metadata and version contracts."""
    detector = GunDetector()
    first_file = real_gun_files[0]
    img = read_image_cv2(first_file)
    ctx = DetectionContext(img, source_id=first_file.stem)
    res = detector.detect(ctx)
    ctx.close()

    assert res.detector_name == "gun_workshop_detector"
    assert res.detector_version == GUN_DETECTOR_VERSION
