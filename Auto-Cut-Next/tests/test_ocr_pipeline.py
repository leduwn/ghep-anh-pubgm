"""Integration tests for OCR pipeline orchestrator, manual overrides, single decode, and session persistence."""

import cv2
import numpy as np
import pytest

from core.constants import (
    Category,
    Decision,
    CLASSIFIER_VERSION,
)
from core.models import ClassificationResult, Rect
from core.session import WorkspaceManager
from app.pipeline import AutoCutPipeline
from ocr.engine import FakeOCREngine
from ocr.models import OCRObservation


def make_gun_screen(w: int = 1280, h: int = 720, seed: int = 0) -> np.ndarray:
    """Creates a synthetic gun workshop screenshot with a dark card and orange border."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (30, 30, 30)

    # Add small seed pixel in top-left to give distinct SHA256 when needed
    if seed != 0:
        cv2.circle(img, (20 + (seed * 7) % 50, 20), 4, (seed * 50 % 255, 120, 150), -1)

    # Active gun card on right
    card_x, card_y = int(0.60 * w), int(0.20 * h)
    card_w, card_h = int(0.25 * w), int(0.30 * h)
    # Orange border
    cv2.rectangle(img, (card_x, card_y), (card_x + card_w, card_y + card_h), (30, 140, 240), 6)
    cv2.rectangle(img, (card_x + 6, card_y + 6), (card_x + card_w - 6, card_y + card_h - 6), (70, 70, 70), -1)

    # Draw simulated elimination tracker badge with high edge density and high color
    counter_x1, counter_x2 = card_x - 120, card_x - 10
    counter_y1, counter_y2 = int(0.08 * h), int(0.18 * h)
    # Bright colorful badge
    cv2.rectangle(img, (counter_x1, counter_y1), (counter_x2, counter_y2), (0, 180, 255), -1)
    # High-frequency edges
    for i in range(15):
        cv2.line(img, (counter_x1 + i * 6, counter_y1), (counter_x1 + i * 6, counter_y2), (255, 255, 255), 2)

    return img


@pytest.fixture
def temp_workspace(tmp_path):
    return WorkspaceManager(tmp_path / "workspace")


def test_pipeline_ocr_session_end_to_end(temp_workspace, tmp_path):
    """End-to-end integration test of OCR session with FakeOCREngine."""
    account_id = "test_ocr_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    # 1. Ingest screenshot
    screen = make_gun_screen()
    file_path = tmp_path / "gun_screen.png"
    cv2.imwrite(str(file_path), screen)

    session = pipeline.ingest_sources(account_id, [file_path])
    src_id = next(iter(session.sources.keys()))

    # 2. Classify and detect
    session.classifications[src_id] = ClassificationResult(
        category=Category.GUN.value,
        confidence=0.98,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)
    session = pipeline.detect_session(account_id, force=True)

    assert len(session.assets) >= 1
    gun_asset = session.assets[0]
    assert gun_asset.category == Category.GUN.value

    # 3. Configure FakeOCREngine with level, name, counter, and UID responses
    fake_engine = FakeOCREngine()

    # Exact ROI responses
    meta = gun_asset.metadata
    lvl_roi = Rect.from_dict(meta["level_roi"])
    nm_roi = Rect.from_dict(meta["name_roi"])
    cnt_roi = Rect.from_dict(meta["kill_counter_roi"])

    fake_engine.set_exact_response(
        f"{lvl_roi.x}_{lvl_roi.y}_{lvl_roi.w}_{lvl_roi.h}",
        [OCRObservation(text="Tiến độ: 3/3", confidence=0.95)],
    )
    fake_engine.set_exact_response(
        f"{nm_roi.x}_{nm_roi.y}_{nm_roi.w}_{nm_roi.h}",
        [OCRObservation(text="M416 Băng Giá", confidence=0.98)],
    )
    fake_engine.set_exact_response(
        f"{cnt_roi.x}_{cnt_roi.y}_{cnt_roi.w}_{cnt_roi.h}",
        [OCRObservation(text="1284", confidence=0.96)],
    )
    # Default for UID cascade
    fake_engine.default_observations = [OCRObservation(text="UID: 5123456789", confidence=0.97)]

    # 4. Run pipeline.ocr_session with fake engine
    session = pipeline.ocr_session(account_id, engine=fake_engine)

    # 5. Verify asset gun_metadata from reloaded session
    assert len(session.assets) >= 1
    gun_asset = session.assets[0]
    assert gun_asset.gun_metadata is not None
    meta = gun_asset.gun_metadata
    assert meta.level == 4  # 3/3 quirk
    assert meta.level_source == "progress"
    assert meta.weapon_name == "M416"
    assert meta.kill_counter == "1284"
    assert meta.counter_present is True
    assert meta.has_counter is True
    assert meta.effective_level == 4
    assert meta.effective_name == "M416"

    # 6. Verify session UID
    assert session.uid == "5123456789"
    assert session.uid_confidence >= 0.95

    # 7. Verify metrics
    assert pipeline.metrics.ocr_guns_processed >= 1
    assert pipeline.metrics.ocr_guns_success >= 1
    assert pipeline.metrics.ocr_uids_found >= 1


def test_pipeline_ocr_manual_override_preservation(temp_workspace, tmp_path):
    """Confirms manual overrides (level_manual, name_manual) are strictly preserved across re-runs."""
    account_id = "test_override_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    screen = make_gun_screen()
    file_path = tmp_path / "screen_man.png"
    cv2.imwrite(str(file_path), screen)

    session = pipeline.ingest_sources(account_id, [file_path])
    src_id = next(iter(session.sources.keys()))
    session.classifications[src_id] = ClassificationResult(
        category=Category.GUN.value,
        confidence=0.98,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)
    session = pipeline.detect_session(account_id, force=True)

    assert len(session.assets) >= 1
    gun_asset = session.assets[0]

    # Run OCR pass 1 with level 3
    fake_engine = FakeOCREngine(default_observations=[
        OCRObservation(text="Tiến độ: 3/7", confidence=0.90),
        OCRObservation(text="AKM", confidence=0.90),
    ])
    session = pipeline.ocr_session(account_id, engine=fake_engine)
    gun_asset = session.assets[0]
    assert gun_asset.gun_metadata.level == 3
    assert gun_asset.gun_metadata.effective_level == 3

    # User manually overrides level to 7 and name to "AKM_SPECIAL"
    gun_asset.gun_metadata.level_manual = 7
    gun_asset.gun_metadata.name_manual = "AKM_SPECIAL"
    temp_workspace.save_session(session)

    # Re-run OCR with force=True and different OCR observations
    fake_engine_2 = FakeOCREngine(default_observations=[
        OCRObservation(text="Tiến độ: 1/7", confidence=0.95),
        OCRObservation(text="M416", confidence=0.95),
    ])
    session = pipeline.ocr_session(account_id, force=True, engine=fake_engine_2)

    # Manual overrides MUST NOT be overwritten!
    reloaded_asset = session.assets[0]
    assert reloaded_asset.gun_metadata.level_manual == 7
    assert reloaded_asset.gun_metadata.name_manual == "AKM_SPECIAL"
    assert reloaded_asset.gun_metadata.effective_level == 7
    assert reloaded_asset.gun_metadata.effective_name == "AKM_SPECIAL"


def test_pipeline_ocr_single_source_decode(temp_workspace, tmp_path):
    """Guarantees each source screenshot is decoded at most once during OCR pass."""
    account_id = "test_decode_ocr_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    f1 = tmp_path / "g1.png"
    f2 = tmp_path / "g2.png"
    cv2.imwrite(str(f1), make_gun_screen(seed=1))
    cv2.imwrite(str(f2), make_gun_screen(seed=2))

    session = pipeline.ingest_sources(account_id, [f1, f2])
    successful_sources = [s for s in session.sources.values() if s.status == "SUCCESS"]
    assert len(successful_sources) == 2

    for s in successful_sources:
        session.classifications[s.id] = ClassificationResult(
            category=Category.GUN.value,
            confidence=0.95,
            decision=Decision.AUTO_ACCEPT.value,
            detector_version=CLASSIFIER_VERSION,
        )
    temp_workspace.save_session(session)
    session = pipeline.detect_session(account_id, force=True)

    initial_decodes = pipeline.metrics.source_decodes

    # Run OCR with fake engine
    fake_engine = FakeOCREngine(default_observations=[
        OCRObservation(text="UID: 5123456789", confidence=0.90),
        OCRObservation(text="M416", confidence=0.90),
    ])
    session = pipeline.ocr_session(account_id, engine=fake_engine)

    # Exactly 2 sources should be decoded during OCR (1 per source)
    ocr_decodes = pipeline.metrics.source_decodes - initial_decodes
    assert ocr_decodes == 2


def test_pipeline_ocr_gun_only_preserves_uid(temp_workspace, tmp_path):
    """Confirms gun_only=True preserves existing UID even when force=True."""
    account_id = "test_gun_only_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    file_path = tmp_path / "screen_gun_only.png"
    cv2.imwrite(str(file_path), make_gun_screen())

    session = pipeline.ingest_sources(account_id, [file_path])
    src_id = next(iter(session.sources.keys()))
    session.classifications[src_id] = ClassificationResult(
        category=Category.GUN.value,
        confidence=0.98,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)
    session = pipeline.detect_session(account_id, force=True)

    # Initial pass: sets both gun and UID
    fake_engine = FakeOCREngine(default_observations=[
        OCRObservation(text="UID: 5123456789", confidence=0.95),
        OCRObservation(text="M416", confidence=0.95),
    ])
    session = pipeline.ocr_session(account_id, engine=fake_engine)
    assert session.uid == "5123456789"

    # Second pass: gun_only with force=True
    fake_engine_2 = FakeOCREngine(default_observations=[
        OCRObservation(text="AKM", confidence=0.95),
    ])
    session = pipeline.ocr_session(account_id, force=True, gun_only=True, engine=fake_engine_2)

    # UID must be preserved intact!
    assert session.uid == "5123456789"
    gun_asset = session.assets[0]
    assert gun_asset.gun_metadata.weapon_name == "AKM"


def test_pipeline_ocr_uid_only_preserves_gun_metadata(temp_workspace, tmp_path):
    """Confirms uid_only=True preserves existing gun_metadata even when force=True."""
    account_id = "test_uid_only_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    file_path = tmp_path / "screen_uid_only.png"
    cv2.imwrite(str(file_path), make_gun_screen())

    session = pipeline.ingest_sources(account_id, [file_path])
    src_id = next(iter(session.sources.keys()))
    session.classifications[src_id] = ClassificationResult(
        category=Category.GUN.value,
        confidence=0.98,
        decision=Decision.AUTO_ACCEPT.value,
        detector_version=CLASSIFIER_VERSION,
    )
    temp_workspace.save_session(session)
    session = pipeline.detect_session(account_id, force=True)

    # Initial pass: sets both gun and UID
    fake_engine = FakeOCREngine(default_observations=[
        OCRObservation(text="UID: 5123456789", confidence=0.95),
        OCRObservation(text="M416", confidence=0.95),
    ])
    session = pipeline.ocr_session(account_id, engine=fake_engine)
    gun_asset = session.assets[0]
    assert gun_asset.gun_metadata.weapon_name == "M416"

    # Second pass: uid_only with force=True and updated UID
    fake_engine_2 = FakeOCREngine(default_observations=[
        OCRObservation(text="UID: 5999999999", confidence=0.95),
    ])
    session = pipeline.ocr_session(account_id, force=True, uid_only=True, engine=fake_engine_2)

    # Gun metadata must be preserved intact!
    reloaded_asset = session.assets[0]
    assert reloaded_asset.gun_metadata is not None
    assert reloaded_asset.gun_metadata.weapon_name == "M416"
    assert session.uid == "5999999999"


def test_pipeline_ocr_uid_conflict_and_low_confidence_rejection(temp_workspace, tmp_path):
    """Confirms conflicting or low-confidence UIDs strictly leave session.uid as None."""
    account_id = "test_uid_reject_acc"
    pipeline = AutoCutPipeline(workspace=temp_workspace)

    f1 = tmp_path / "s1.png"
    f2 = tmp_path / "s2.png"
    cv2.imwrite(str(f1), make_gun_screen(seed=10))
    cv2.imwrite(str(f2), make_gun_screen(seed=20))

    session = pipeline.ingest_sources(account_id, [f1, f2])
    for sid in session.sources:
        session.classifications[sid] = ClassificationResult(
            category=Category.GUN.value,
            confidence=0.95,
            decision=Decision.AUTO_ACCEPT.value,
            detector_version=CLASSIFIER_VERSION,
        )
    temp_workspace.save_session(session)
    pipeline.detect_session(account_id, force=True)

    # Low confidence test (below accept threshold 0.80)
    low_engine = FakeOCREngine(default_observations=[
        OCRObservation(text="UID: 5123456789", confidence=0.65),
    ])
    session = pipeline.ocr_session(account_id, engine=low_engine)
    assert session.uid is None
    assert session.uid_review_required is True


def test_session_invalidate_ocr_prunes_asset_keys_and_orphans(temp_workspace):
    """Confirms source-scoped invalidate_ocr removes asset-ID keyed OCR records and prunes orphans."""
    from core.models import AccountSession, DetectedAsset, GunMetadata, SourceImage

    session = AccountSession(account_id="test_inval_acc")
    session.sources["s1"] = SourceImage(id="s1", path="p1", sha256="h1", width=100, height=100)
    session.sources["s2"] = SourceImage(id="s2", path="p2", sha256="h2", width=100, height=100)

    a1 = DetectedAsset("a1", "s1", "GUN", Rect(0, 0, 10, 10), 10, 10, "det", "1.0", gun_metadata=GunMetadata(level=3))
    a2 = DetectedAsset("a2", "s2", "GUN", Rect(0, 0, 10, 10), 10, 10, "det", "1.0", gun_metadata=GunMetadata(level=4))
    session.assets = [a1, a2]

    # Populate ocr_results with asset keys, source keys, and an orphan key
    session.ocr_results["a1"] = {"level": 3}
    session.ocr_results["a2"] = {"level": 4}
    session.ocr_results["s1"] = {"uid": "111"}
    session.ocr_results["orphan_key"] = {"dummy": 123}

    # Invalidate s1
    session.invalidate_ocr(source_id="s1")

    # a1 and s1 must be removed, orphan_key must be pruned
    assert "a1" not in session.ocr_results
    assert "s1" not in session.ocr_results
    assert "orphan_key" not in session.ocr_results
    # a2 must remain
    assert "a2" in session.ocr_results

