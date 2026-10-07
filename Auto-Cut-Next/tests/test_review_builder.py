"""Unit tests for ReviewQueueBuilder inspecting session state and generating deterministic review items."""

from __future__ import annotations

import pytest

from core.constants import (
    Category,
    Decision,
    DetectionStatus,
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
from review.models import (
    ReviewItem,
    ReviewResolution,
    compute_machine_fingerprint,
    make_classification_review_id,
    make_detection_review_id,
    make_asset_quality_review_id,
    make_ocr_review_id,
    make_uid_review_id,
)
from review.review_builder import ReviewQueueBuilder


def test_classification_review_generation():
    """Classification states correctly map to review items or bypass review."""
    session = AccountSession(account_id="test_acc")

    # Source 1: AUTO_ACCEPT -> NO review
    s1 = SourceImage(id="s1", filename="screen_1.png", path="", sha256="h1", source_index=0)
    session.sources[s1.id] = s1
    session.classifications[s1.id] = ClassificationResult(Category.GUN.value, 0.98, Decision.AUTO_ACCEPT.value)

    # Source 2: REVIEW -> P2 review
    s2 = SourceImage(id="s2", filename="screen_2.png", path="", sha256="h2", source_index=1)
    session.sources[s2.id] = s2
    session.classifications[s2.id] = ClassificationResult(Category.VEHICLE.value, 0.52, Decision.REVIEW.value)

    # Source 3: UNKNOWN -> P1 review
    s3 = SourceImage(id="s3", filename="screen_3.png", path="", sha256="h3", source_index=2)
    session.sources[s3.id] = s3
    session.classifications[s3.id] = ClassificationResult(Category.OTHER.value, 0.0, Decision.UNKNOWN.value)

    # Source 4: ERROR -> P0 review
    s4 = SourceImage(id="s4", filename="screen_4.png", path="", sha256="h4", source_index=3)
    session.sources[s4.id] = s4
    session.classifications[s4.id] = ClassificationResult(Category.OTHER.value, 0.0, Decision.ERROR.value)

    builder = ReviewQueueBuilder()
    items = builder.build_queue(session)

    item_ids = {it.id: it for it in items}
    assert make_classification_review_id("s1") not in item_ids
    assert make_classification_review_id("s2") in item_ids
    assert item_ids[make_classification_review_id("s2")].priority == ReviewPriority.P2.value
    assert make_classification_review_id("s3") in item_ids
    assert item_ids[make_classification_review_id("s3")].priority == ReviewPriority.P1.value
    assert make_classification_review_id("s4") in item_ids
    assert item_ids[make_classification_review_id("s4")].priority == ReviewPriority.P0.value


def test_field_level_ocr_gun_and_counter_semantics():
    """OCR field-level review independently evaluates name, level, and counter badge presence."""
    session = AccountSession(account_id="test_acc")
    s1 = SourceImage(id="s1", filename="screen_1.png", path="", sha256="h1", source_index=0)
    session.sources[s1.id] = s1

    # Case A: High name confidence (.95), low level confidence (.42), badge absent
    # -> MUST ONLY generate review item for 'level'!
    asset_a = DetectedAsset(
        id="asset_a",
        source_id=s1.id,
        category=Category.GUN.value,
        crop_rect=Rect(0, 0, 100, 100),
        gun_metadata=GunMetadata(
            weapon_name="M416",
            name_confidence=0.95,
            level=3,
            level_confidence=0.42,
            counter_present=False,  # Badge absent
            kill_counter=None,
        ),
    )
    session.assets.append(asset_a)

    builder = ReviewQueueBuilder(ocr_accept_threshold=0.80)
    items = builder.build_queue(session)
    item_map = {it.id: it for it in items}

    lvl_id = make_ocr_review_id("asset_a", "level")
    nm_id = make_ocr_review_id("asset_a", "name")
    cnt_id = make_ocr_review_id("asset_a", "counter")

    assert lvl_id in item_map
    assert item_map[lvl_id].field_name == "level"
    assert item_map[lvl_id].subsystem == ReviewSubsystem.OCR_GUN.value

    # Name is high confidence -> NO review item
    assert nm_id not in item_map

    # Badge absent -> counter not required -> NO review item
    assert cnt_id not in item_map

    # Case B: Badge present with weak/missing counter -> MUST generate counter review
    asset_b = DetectedAsset(
        id="asset_b",
        source_id=s1.id,
        category=Category.GUN.value,
        crop_rect=Rect(100, 0, 100, 100),
        gun_metadata=GunMetadata(
            weapon_name="AKM",
            name_confidence=0.90,
            level=7,
            level_confidence=0.92,
            counter_present=True,  # Badge present!
            kill_counter=None,     # Failed OCR
            counter_confidence=0.2,
        ),
    )
    session.assets.append(asset_b)

    items2 = builder.build_queue(session)
    item_map2 = {it.id: it for it in items2}

    cnt_b_id = make_ocr_review_id("asset_b", "counter")
    assert cnt_b_id in item_map2
    assert item_map2[cnt_b_id].field_name == "counter"
    assert item_map2[cnt_b_id].reason == ReviewReason.OCR_COUNTER_UNCERTAIN.value


def test_uid_consensus_review_generation():
    """Conflicting candidate UIDs trigger P1 review while single low confidence triggers P2."""
    session = AccountSession(account_id="test_acc")

    # Conflict across candidate values
    session.uid = "5123456789"
    session.uid_confidence = 0.60
    session.uid_review_required = True
    session.uid_candidates = [
        {"uid": "5123456789", "confidence": 0.60},
        {"uid": "5987654321", "confidence": 0.58},
    ]

    builder = ReviewQueueBuilder()
    items = builder.build_queue(session)
    uid_id = make_uid_review_id("test_acc")
    uid_item = next(it for it in items if it.id == uid_id)

    assert uid_item.priority == ReviewPriority.P1.value
    assert uid_item.reason == ReviewReason.UID_CONFLICT.value
    assert len(uid_item.candidates) == 2


def test_staleness_detection_on_machine_acceptance():
    """Machine value acceptance becomes STALE and re-opens if machine fingerprint materially changes."""
    session = AccountSession(account_id="test_acc")
    s1 = SourceImage(id="s1", filename="screen_1.png", path="", sha256="h1", source_index=0)
    session.sources[s1.id] = s1
    session.classifications[s1.id] = ClassificationResult(Category.GUN.value, 0.55, Decision.REVIEW.value, detector_version="1.0.0")

    builder = ReviewQueueBuilder()
    items = builder.build_queue(session)
    r_id = make_classification_review_id("s1")
    item = next(it for it in items if it.id == r_id)

    # User accepts machine value
    item.status = ReviewStatus.RESOLVED_MANUAL.value
    item.resolution = ReviewResolution(
        action="accept_machine",
        resolved_by="manual",
        value="GUN",
        fingerprint=item.fingerprint,
    )
    session.review_items[r_id] = item

    # Re-running queue with unchanged classification preserves resolution
    items2 = builder.build_queue(session)
    item2 = next(it for it in items2 if it.id == r_id)
    assert item2.status == ReviewStatus.RESOLVED_MANUAL.value

    # Underlying classifier version or confidence changes
    session.classifications[s1.id] = ClassificationResult(Category.GUN.value, 0.40, Decision.REVIEW.value, detector_version="2.0.0")

    # Rebuilding queue detects staleness and reopens item!
    items3 = builder.build_queue(session)
    item3 = next(it for it in items3 if it.id == r_id)
    assert item3.status == ReviewStatus.OPEN.value
    assert "staleness_notice" in item3.metadata
