"""Unit and integration tests for ReviewService manual resolutions and downstream invalidation."""

from __future__ import annotations

import tempfile
import pytest

from core.constants import (
    Category,
    Decision,
    ReviewSubsystem,
    ReviewStatus,
    ReviewPriority,
    ReviewReason,
)
from core.models import (
    AccountSession,
    SourceImage,
    ClassificationResult,
    SourceDetectionResult,
    DetectedAsset,
    Rect,
    GunMetadata,
)
from core.session import WorkspaceManager
from review.models import (
    make_classification_review_id,
    make_ocr_review_id,
    make_uid_review_id,
)
from review.review_service import ReviewService


@pytest.fixture
def test_env():
    with tempfile.TemporaryDirectory() as td:
        ws = WorkspaceManager(td)
        session = AccountSession(account_id="test_resolution_acc")
        yield ws, session


def test_category_override_and_downstream_invalidation(test_env):
    """Overriding category invalidates source detection, assets, orphan OCR, and records audit trail."""
    ws, session = test_env
    s1 = SourceImage(id="s1", filename="screen_1.png", path="", sha256="h1", source_index=0)
    session.sources[s1.id] = s1
    session.classifications[s1.id] = ClassificationResult(Category.GUN.value, 0.50, Decision.REVIEW.value)

    # Add detection and assets for s1
    session.detections[s1.id] = SourceDetectionResult(source_id=s1.id, status="SUCCESS", detector="gun_detector")
    asset = DetectedAsset(
        id="asset_gun_1",
        source_id=s1.id,
        category=Category.GUN.value,
        crop_rect=Rect(0, 0, 100, 100),
        gun_metadata=GunMetadata(weapon_name="M416", level=1),
    )
    session.assets.append(asset)
    session.ocr_results[asset.id] = {"weapon_name": "M416", "level": 1}

    # Save session
    ws.save_session(session)

    service = ReviewService(session=session, workspace=ws)
    # Perform manual category override
    item = service.set_category(source_id="s1", category="VEHICLE", notes="Manual correction to VEHICLE")

    assert item.status == ReviewStatus.RESOLVED_MANUAL.value
    assert item.category == "VEHICLE"
    assert session.classifications["s1"].category == "VEHICLE"

    # Downstream invalidation verified!
    assert "s1" not in session.detections
    assert len(session.assets) == 0
    assert asset.id not in session.ocr_results

    # Audit trail recorded
    assert len(session.review_history) == 1
    action = session.review_history[0]
    assert action.action == "set_category"
    assert action.old_value == "GUN"
    assert action.new_value == "VEHICLE"

    # Check persistence
    loaded = ws.load_session("test_resolution_acc")
    assert loaded.classifications["s1"].category == "VEHICLE"
    assert len(loaded.assets) == 0


def test_invalid_category_rejected(test_env):
    """Unknown category strings are rejected before any mutations occur."""
    ws, session = test_env
    s1 = SourceImage(id="s1", filename="screen_1.png", path="", sha256="h1", source_index=0)
    session.sources[s1.id] = s1
    session.classifications[s1.id] = ClassificationResult(Category.OTHER.value, 0.0, Decision.UNKNOWN.value)

    service = ReviewService(session=session, workspace=ws)
    with pytest.raises(ValueError, match="Invalid category"):
        service.set_category("s1", "NON_EXISTENT_CATEGORY")


def test_field_level_ocr_gun_resolutions(test_env):
    """Field-level OCR manual updates (level, name, counter, clear) update models and resolve review items."""
    ws, session = test_env
    s1 = SourceImage(id="s1", filename="screen_1.png", path="", sha256="h1", source_index=0)
    session.sources[s1.id] = s1
    session.classifications[s1.id] = ClassificationResult(Category.GUN.value, 0.95, Decision.AUTO_ACCEPT.value)

    asset = DetectedAsset(
        id="gun_card_1",
        source_id=s1.id,
        category=Category.GUN.value,
        crop_rect=Rect(0, 0, 100, 100),
        gun_metadata=GunMetadata(
            weapon_name="",
            name_confidence=0.0,
            level=None,
            level_confidence=0.0,
            counter_present=True,
            kill_counter="",
        ),
    )
    session.assets.append(asset)
    ws.save_session(session)

    service = ReviewService(session=session, workspace=ws)

    # 1. Set Level
    res_lvl = service.set_level("gun_card_1", 7, notes="Verified level 7")
    assert res_lvl.status == ReviewStatus.RESOLVED_MANUAL.value
    assert asset.gun_metadata.level_manual == 7
    assert asset.gun_metadata.effective_level == 7

    # 2. Set Name
    res_name = service.set_name("gun_card_1", "M416 Băng Giá", notes="Verified M416")
    assert res_name.status == ReviewStatus.RESOLVED_MANUAL.value
    assert asset.gun_metadata.name_manual == "M416 Băng Giá"
    assert asset.gun_metadata.effective_name == "M416 Băng Giá"

    # 3. Set Counter
    res_cnt = service.set_counter("gun_card_1", 1234, notes="Badge present with 1234")
    assert res_cnt.status == ReviewStatus.RESOLVED_MANUAL.value
    assert asset.gun_metadata.counter_manual == "1234"
    assert asset.gun_metadata.counter_present is True
    assert asset.gun_metadata.effective_counter == "1234"

    # 4. Clear Counter
    res_clr = service.clear_counter("gun_card_1", notes="Badge actually absent")
    assert res_clr.status == ReviewStatus.RESOLVED_MANUAL.value
    assert asset.gun_metadata.counter_manual is None
    assert asset.gun_metadata.counter_present is False
    assert asset.gun_metadata.effective_counter is None

    # Audit trail recorded all actions
    assert len(session.review_history) == 4
    assert [a.action for a in session.review_history] == ["set_level", "set_name", "set_counter", "clear_counter"]


def test_uid_validation_and_manual_override(test_env):
    """UID override strictly requires 8-14 digits and records audit action."""
    ws, session = test_env
    session.uid = "12345678"
    session.uid_confidence = 0.50
    session.uid_review_required = True

    service = ReviewService(session=session, workspace=ws)

    # Invalid UIDs rejected
    with pytest.raises(ValueError, match="8-14 digits"):
        service.set_uid("123")  # too short
    with pytest.raises(ValueError, match="8-14 digits"):
        service.set_uid("12345678901234567")  # too long
    with pytest.raises(ValueError, match="8-14 digits"):
        service.set_uid("5123abc456")  # non-digits

    # Valid UID accepted
    item = service.set_uid("5123456789", notes="Player ID confirmed")
    assert item.status == ReviewStatus.RESOLVED_MANUAL.value
    assert session.uid_manual == "5123456789"
    assert session.effective_uid == "5123456789"
    assert len(session.review_history) == 1
    assert session.review_history[0].action == "set_uid"


def test_reject_and_skip_item(test_env):
    """Rejecting and skipping items updates status and records audit history."""
    ws, session = test_env
    item = ReviewItem(
        id="review:src_1:detection",
        subsystem=ReviewSubsystem.DETECTION.value,
        machine_value="generic_grid_detector",
    )
    session.review_items[item.id] = item
    ws.save_session(session)

    service = ReviewService(session=session, workspace=ws)

    # Skip
    service.skip_item(item.id, notes="Skip for now")
    assert item.status == ReviewStatus.SKIPPED.value

    # Reject
    service.reject_item(item.id, notes="False detection")
    assert item.status == ReviewStatus.REJECTED.value
    assert len(session.review_history) == 2
