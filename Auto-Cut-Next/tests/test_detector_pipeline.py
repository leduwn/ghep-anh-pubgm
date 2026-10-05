"""Integration tests for pipeline detection orchestrator, category gating, caching, dedup, and persistence."""

import cv2
import numpy as np
import pytest
from pathlib import Path

from core.constants import (
    Category,
    Decision,
    DetectionStatus,
    CLASSIFIER_VERSION,
    MISC_GRID_VERSION,
)
from core.models import ClassificationResult
from core.detection_state import SourceDetectionResult
from core.settings import AutoCutSettings
from core.session import WorkspaceManager
from app.pipeline import AutoCutPipeline


def make_grid_image(rows: int = 2, cols: int = 2, seed: int = 42) -> np.ndarray:
    """Helper to generate a clean synthetic grid image."""
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    img[:, :] = (180, 180, 180)

    card_w, card_h = 100, 100
    start_x, start_y = 200, 150
    step_x, step_y = 130, 130
    rng = np.random.default_rng(seed)

    for r in range(rows):
        cy = start_y + r * step_y
        for c in range(cols):
            cx = start_x + c * step_x
            img[cy:cy + card_h, cx:cx + card_w] = (35, 30, 25)
            noise = rng.integers(60, 200, size=(card_h - 20, card_w - 20, 3), dtype=np.uint8)
            img[cy + 10:cy + card_h - 10, cx + 10:cx + card_w - 10] = noise
            cv2.rectangle(img, (cx, cy), (cx + card_w, cy + card_h), (80, 80, 80), 2)

    return img


@pytest.fixture
def temp_workspace(tmp_path):
    return WorkspaceManager(tmp_path / "workspace")


def test_pipeline_detect_category_gating_and_deferred(temp_workspace, tmp_path):
    account_id = "test_gating_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    # Create 2 source images: one Gun, one ItemSet
    gun_img = make_grid_image(seed=1)
    gun_file = tmp_path / "gun_screen.png"
    cv2.imwrite(str(gun_file), gun_img)

    item_img = make_grid_image(seed=2)
    item_file = tmp_path / "item_screen.png"
    cv2.imwrite(str(item_file), item_img)

    session = pipeline.ingest_sources(account_id, [gun_file, item_file])
    gun_src_id = next(s_id for s_id, s in session.sources.items() if "gun_screen" in s.filename)
    item_src_id = next(s_id for s_id, s in session.sources.items() if "item_screen" in s.filename)

    # Manually provide classification results
    session.classifications[gun_src_id] = ClassificationResult(
        category=Category.GUN.value,
        confidence=0.98,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    session.classifications[item_src_id] = ClassificationResult(
        category=Category.ITEM_SET.value,
        confidence=0.95,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)

    # Run detection
    pipeline.detect_session(account_id)

    # Verify Gun is routed with GunDetector primary and fallback executed on generic grid
    assert gun_src_id in session.detections
    gun_det = session.detections[gun_src_id]
    assert gun_det.primary_detector == "gun_workshop_detector"
    assert gun_det.fallback_used is True
    assert gun_det.card_count == 4

    # Verify ItemSet is detected with grid
    assert item_src_id in session.detections
    item_det = session.detections[item_src_id]
    assert item_det.status == DetectionStatus.SUCCESS.value
    assert item_det.card_count == 4
    assert item_det.active_count == 4

    # Verify assets in session from both sources
    assert len(session.assets) == 8


def test_pipeline_detect_caching_and_persistence(temp_workspace, tmp_path):
    account_id = "test_cache_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    img = make_grid_image(rows=1, cols=2, seed=10)
    file_path = tmp_path / "screen1.png"
    cv2.imwrite(str(file_path), img)

    session = pipeline.ingest_sources(account_id, [file_path])
    src_id = next(iter(session.sources.keys()))

    session.classifications[src_id] = ClassificationResult(
        category=Category.HELMET.value,
        confidence=0.90,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)

    # First run (computes and caches)
    session_1 = pipeline.detect_session(account_id)
    assert pipeline.metrics.detect_sources_processed == 1
    assert pipeline.metrics.detect_sources_cached == 0

    # Second run without force (hits disk cache)
    pipeline_2 = AutoCutPipeline(workspace=temp_workspace)
    session_2 = pipeline_2.detect_session(account_id, force=False)
    assert pipeline_2.metrics.detect_sources_cached == 1

    # Reload from disk and verify SourceDetectionResult deserialization
    reloaded = temp_workspace.load_session(account_id)
    assert src_id in reloaded.detections
    det_res = reloaded.detections[src_id]
    assert isinstance(det_res, SourceDetectionResult)
    assert det_res.status == DetectionStatus.SUCCESS.value
    assert det_res.card_count == 2


def test_pipeline_detect_cross_source_deduplication(temp_workspace, tmp_path):
    account_id = "test_dedup_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    # Two screenshots sharing duplicate cards
    img1 = make_grid_image(rows=1, cols=2, seed=99)
    img2 = make_grid_image(rows=1, cols=2, seed=99)  # identical tiles

    f1 = tmp_path / "f1.png"
    f2 = tmp_path / "f2.png"
    cv2.imwrite(str(f1), img1)
    cv2.imwrite(str(f2), img2)

    session = pipeline.ingest_sources(account_id, [f1, f2])
    src_ids = list(session.sources.keys())

    for sid in src_ids:
        session.classifications[sid] = ClassificationResult(
            category=Category.BACKPACK.value,
            confidence=0.92,
            decision=Decision.AUTO_ACCEPT.value,
            detector_version=CLASSIFIER_VERSION,
        )
    temp_workspace.save_session(session)

    pipeline.detect_session(account_id)

    # 4 total assets, 2 canonical and 2 duplicates
    assert len(session.assets) == 4
    duplicates = [a for a in session.assets if a.duplicate]
    canonical = [a for a in session.assets if not a.duplicate]

    assert len(duplicates) == 2
    assert len(canonical) == 2
    for dup in duplicates:
        assert dup.duplicate_of is not None


def test_pipeline_detect_review_classification_propagates_review(temp_workspace, tmp_path):
    account_id = "test_review_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    img = make_grid_image(rows=1, cols=2, seed=55)
    f = tmp_path / "review_screen.png"
    cv2.imwrite(str(f), img)

    session = pipeline.ingest_sources(account_id, [f])
    src_id = next(iter(session.sources.keys()))

    # Source classified as REVIEW
    session.classifications[src_id] = ClassificationResult(
        category=Category.MISC.value,
        confidence=0.72,
        decision=Decision.REVIEW.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)

    pipeline.detect_session(account_id)

    # Resulting assets must have review_required=True
    assert len(session.assets) >= 2
    for a in session.assets:
        assert a.review_required is True
        assert any("Source classification requires review" in r for r in a.review_reasons)


def test_pipeline_detect_unknown_classification_skipped(temp_workspace, tmp_path):
    account_id = "test_unknown_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    img = make_grid_image(rows=1, cols=2, seed=66)
    f = tmp_path / "unknown_screen.png"
    cv2.imwrite(str(f), img)

    session = pipeline.ingest_sources(account_id, [f])
    src_id = next(iter(session.sources.keys()))

    session.classifications[src_id] = ClassificationResult(
        category=Category.OTHER.value,
        confidence=0.30,
        decision=Decision.UNKNOWN.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)

    pipeline.detect_session(account_id)

    # Unknown source must not be processed by detector
    assert src_id not in session.detections
    assert len(session.assets) == 0


def test_pipeline_detect_stale_classifier_version(temp_workspace, tmp_path):
    account_id = "test_stale_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    img = make_grid_image(rows=1, cols=2, seed=77)
    f = tmp_path / "stale_screen.png"
    cv2.imwrite(str(f), img)

    session = pipeline.ingest_sources(account_id, [f])
    src_id = next(iter(session.sources.keys()))

    # Classification from older version (1.0.0 vs current 2.0.0)
    session.classifications[src_id] = ClassificationResult(
        category=Category.ITEM_SET.value,
        confidence=0.95,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version="1.0.0",  # Stale
    )
    temp_workspace.save_session(session)

    pipeline.detect_session(account_id)

    assert src_id in session.detections
    det = session.detections[src_id]
    assert det.status == DetectionStatus.ERROR.value
    assert "stale" in det.error_message.lower()
    assert len(session.assets) == 0


def test_pipeline_detect_cache_write_error_handled(temp_workspace, tmp_path, monkeypatch):
    """Confirms cache write failures do not crash detection, log warnings, and increment metrics."""
    account_id = "test_cache_fail_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    img = make_grid_image(rows=1, cols=2, seed=88)
    f = tmp_path / "cache_fail_screen.png"
    cv2.imwrite(str(f), img)

    session = pipeline.ingest_sources(account_id, [f])
    src_id = next(iter(session.sources.keys()))

    session.classifications[src_id] = ClassificationResult(
        category=Category.ITEM_SET.value,
        confidence=0.95,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)

    # Monkeypatch disk_cache.put to raise an exception simulating disk failure
    def mock_put_fail(*args, **kwargs):
        raise OSError("Simulated disk full during cache write")

    monkeypatch.setattr(pipeline.disk_cache, "put", mock_put_fail)

    # Detection must not crash
    session = pipeline.detect_session(account_id)
    assert pipeline.metrics.cache_write_errors >= 1
    assert src_id in session.detections
    assert session.detections[src_id].status == DetectionStatus.SUCCESS.value
    assert len(session.assets) == 2


def test_pipeline_detect_single_source_decode_during_dedup(temp_workspace, tmp_path):
    """Confirms each source image is decoded at most once during session deduplication."""
    account_id = "test_decode_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    # Create 2 screenshots with 4 cards each (8 total assets)
    f1 = tmp_path / "decode_s1.png"
    f2 = tmp_path / "decode_s2.png"
    cv2.imwrite(str(f1), make_grid_image(rows=2, cols=2, seed=101))
    cv2.imwrite(str(f2), make_grid_image(rows=2, cols=2, seed=102))

    session = pipeline.ingest_sources(account_id, [f1, f2])
    for sid in session.sources:
        session.classifications[sid] = ClassificationResult(
            category=Category.HELMET.value,
            confidence=0.95,
            decision=Decision.AUTO_ACCEPT.value,
            detector_version=CLASSIFIER_VERSION,
        )
    temp_workspace.save_session(session)

    pipeline.detect_session(account_id)

    # 8 total assets were cropped, but exactly 2 source decodes must occur during dedup
    assert len(session.assets) == 8
    assert pipeline.metrics.source_decodes == 2


def test_pipeline_detect_low_grid_confidence_review_policy(temp_workspace, tmp_path):
    """Confirms detector_confidence_threshold triggers REVIEW status and review_required on assets."""
    account_id = "test_grid_conf_review_acc"
    # Set threshold very high (0.999) so synthetic grid confidence falls below it
    strict_settings = AutoCutSettings(detector_confidence_threshold=0.999)
    pipeline = AutoCutPipeline(workspace=temp_workspace, settings=strict_settings)

    f = tmp_path / "low_conf_screen.png"
    cv2.imwrite(str(f), make_grid_image(rows=2, cols=2, seed=202))

    session = pipeline.ingest_sources(account_id, [f])
    src_id = next(iter(session.sources.keys()))
    session.classifications[src_id] = ClassificationResult(
        category=Category.ITEM_SET.value,
        confidence=0.95,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)

    pipeline.detect_session(account_id)

    assert src_id in session.detections
    det = session.detections[src_id]
    assert det.status == DetectionStatus.REVIEW.value
    assert any("Grid geometry confidence" in r for r in det.reasons)

    assert len(session.assets) == 4
    for a in session.assets:
        assert a.review_required is True
        assert any("Grid geometry confidence" in r for r in a.review_reasons)


