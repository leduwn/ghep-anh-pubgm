"""Integration tests for pipeline classification, caching, persistence, and real fixtures."""

import cv2
import numpy as np
import pytest
from pathlib import Path

from core.constants import Category, Decision, CLASSIFIER_VERSION, SourceStatus
from core.models import ClassificationResult, SourceImage
from core.session import WorkspaceManager
from core.settings import AutoCutSettings
from app.pipeline import AutoCutPipeline
from detectors import ClassificationContext, ScreenClassifier


@pytest.fixture
def temp_workspace(tmp_path):
    ws = WorkspaceManager(tmp_path / "workspace")
    return ws


def test_pipeline_classify_session_and_persistence(temp_workspace, tmp_path):
    account_id = "test_classify_acc"
    dirs = temp_workspace.init_account_workspace(account_id)

    # Create dummy source image (Vehicle screen)
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    scale_x = 1920 / 2778.0
    scale_y = 1080 / 1284.0
    # Vehicle tab blue indicator
    cv2.rectangle(
        img,
        (int(round(2545 * scale_x)), int(round(520 * scale_y))),
        (int(round(2557 * scale_x)), int(round(580 * scale_y))),
        (220, 140, 20),
        -1,
    )
    src_file = tmp_path / "vehicle.png"
    encode_ok, buf = cv2.imencode(".png", img)
    assert encode_ok
    src_file.write_bytes(buf.tobytes())

    pipeline = AutoCutPipeline(workspace=temp_workspace)
    session = pipeline.ingest_sources(account_id, [src_file])
    assert len(session.sources) == 1
    src_id = next(iter(session.sources.keys()))

    # Run classify
    session_after = pipeline.classify_session(account_id)
    assert src_id in session_after.classifications
    res = session_after.classifications[src_id]
    assert res.category == Category.VEHICLE.value
    assert res.decision == Decision.AUTO_ACCEPT.value
    assert res.detector_version == ScreenClassifier.VERSION

    # Persistence verification: reload from disk
    reloaded = temp_workspace.load_session(account_id)
    assert src_id in reloaded.classifications
    res_reloaded = reloaded.classifications[src_id]
    assert res_reloaded.category == Category.VEHICLE.value
    assert res_reloaded.confidence == res.confidence
    assert res_reloaded.decision == res.decision


def test_classify_cache_and_version_invalidation(temp_workspace, tmp_path):
    account_id = "test_cache_acc"
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    src_file = tmp_path / "img1.png"
    encode_ok, buf = cv2.imencode(".png", img)
    assert encode_ok
    src_file.write_bytes(buf.tobytes())

    pipeline = AutoCutPipeline(workspace=temp_workspace)
    pipeline.ingest_sources(account_id, [src_file])

    # 1. First classification -> processed
    pipeline.classify_session(account_id)
    assert pipeline.metrics.classify_processed == 1
    assert pipeline.metrics.classify_cached == 0

    # 2. Second classification -> cached
    pipeline.classify_session(account_id)
    assert pipeline.metrics.classify_cached == 1

    # 3. Simulate stale classifier version -> reclassified
    session = temp_workspace.load_session(account_id)
    src_id = next(iter(session.sources.keys()))
    old_res = session.classifications[src_id]
    stale_res = ClassificationResult(
        category=old_res.category,
        confidence=old_res.confidence,
        decision=old_res.decision,
        detector=old_res.detector,
        detector_version="0.9.0",  # outdated version
    )
    session.classifications[src_id] = stale_res
    temp_workspace.save_session(session)

    pipeline2 = AutoCutPipeline(workspace=temp_workspace)


def test_missing_source_file_handled_gracefully(temp_workspace, tmp_path):
    account_id = "test_missing_file_acc"
    src_file = tmp_path / "temporary.png"
    src_file.write_bytes(cv2.imencode(".png", np.zeros((100, 100, 3), dtype=np.uint8))[1].tobytes())

    pipeline = AutoCutPipeline(workspace=temp_workspace)
    pipeline.ingest_sources(account_id, [src_file])

    # Delete the source file
    src_file.unlink()

    # Classification must not crash
    session = pipeline.classify_session(account_id)
    src_id = next(iter(session.sources.keys()))
    res = session.classifications[src_id]
    assert res.decision == Decision.ERROR.value
    assert pipeline.metrics.classify_errors == 1


def test_corrupt_source_image_handled_gracefully(temp_workspace, tmp_path):
    account_id = "test_corrupt_acc"
    src_file = tmp_path / "corrupt.png"
    src_file.write_bytes(b"NOT_A_VALID_IMAGE_DATA")

    from core.models import AccountSession
    session = AccountSession(account_id=account_id)
    src = SourceImage(
        id="corrupt_src",
        path=str(src_file),
        sha256="fake_sha",
        filename="corrupt.png",
        width=100,
        height=100,
        mtime=0.0,
        source_index=1,
    )
    session.sources["corrupt_src"] = src
    temp_workspace.save_session(session)

    pipeline = AutoCutPipeline(workspace=temp_workspace)
    session_res = pipeline.classify_session(account_id)
    res = session_res.classifications["corrupt_src"]
    assert res.decision == Decision.ERROR.value
    assert pipeline.metrics.classify_errors == 1


def test_real_fixtures_read_only():
    """Reads available real test fixtures from legacy tool read-only to ensure stability."""
    repo_root = Path(__file__).resolve().parents[2]
    candidate_dirs = [
        repo_root / "Cắt" / "input",
        repo_root / "Cắt" / "tool" / "Cắt Trang Phục" / "input" / "783",
    ]

    images_found = 0
    classifier = ScreenClassifier()

    for d in candidate_dirs:
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                data = p.read_bytes()
                arr = np.frombuffer(data, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None or img.size == 0:
                    continue
                images_found += 1
                ctx = ClassificationContext(img)
                res = classifier.classify(ctx)
                ctx.close()
                assert res.category in {c.value for c in Category}
                assert res.decision in {d.value for d in Decision}
                assert res.confidence >= 0.0

    assert images_found >= 1, "Expected to find real images in legacy folders"

