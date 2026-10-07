"""Unit tests for review data models, deterministic IDs, and fingerprinting."""

from __future__ import annotations

import pytest

from core.constants import (
    ReviewSubsystem,
    ReviewStatus,
    ReviewPriority,
    ReviewReason,
)
from core.models import AccountSession
from review.models import (
    ReviewItem,
    ReviewResolution,
    ReviewAction,
    make_classification_review_id,
    make_detection_review_id,
    make_asset_quality_review_id,
    make_ocr_review_id,
    make_uid_review_id,
    compute_machine_fingerprint,
)


def test_deterministic_id_generation():
    """Deterministic IDs strictly derive from target entity identifiers."""
    assert make_classification_review_id("src_100") == "review:src_100:classification"
    assert make_detection_review_id("src_100") == "review:src_100:detection"
    assert make_asset_quality_review_id("asset_99", "partial_asset") == "review:asset_99:quality:partial_asset"
    assert make_ocr_review_id("asset_99", "level") == "review:asset_99:ocr:level"
    assert make_ocr_review_id("asset_99", "counter") == "review:asset_99:ocr:counter"
    assert make_uid_review_id("acc_123") == "review:acc_123:uid"


def test_compute_machine_fingerprint():
    """Fingerprints are deterministic hashes sensitive to material state changes."""
    fp1 = compute_machine_fingerprint("1.0.0", "M416", 0.95, "ocr_ok")
    fp2 = compute_machine_fingerprint("1.0.0", "M416", 0.95, "ocr_ok")
    assert fp1 == fp2

    # Material value change
    fp_val = compute_machine_fingerprint("1.0.0", "AKM", 0.95, "ocr_ok")
    assert fp1 != fp_val

    # Material confidence change
    fp_conf = compute_machine_fingerprint("1.0.0", "M416", 0.70, "ocr_ok")
    assert fp1 != fp_conf

    # Subsystem version bump
    fp_ver = compute_machine_fingerprint("2.0.0", "M416", 0.95, "ocr_ok")
    assert fp1 != fp_ver


def test_review_item_lifecycle_and_serialization():
    """Review items serialize and deserialize cleanly with nested resolutions."""
    item = ReviewItem(
        id="review:src_1:classification",
        subsystem=ReviewSubsystem.CLASSIFICATION.value,
        status=ReviewStatus.OPEN.value,
        priority=ReviewPriority.P2.value,
        reason=ReviewReason.CLASSIFICATION_LOW_CONFIDENCE.value,
        message="Test classification review",
        source_id="src_1",
        confidence=0.55,
        machine_value="GUN",
    )
    assert item.is_open
    assert not item.is_resolved

    # Serialize
    d = item.to_dict()
    assert d["id"] == "review:src_1:classification"
    assert d["confidence"] == 0.55

    # Deserialize
    item2 = ReviewItem.from_dict(d)
    assert item2.id == item.id
    assert item2.is_open

    # Resolve
    item2.status = ReviewStatus.RESOLVED_MANUAL.value
    item2.resolution = ReviewResolution(
        action="set_category",
        resolved_by="manual",
        value="VEHICLE",
        notes="Corrected category",
    )
    assert not item2.is_open
    assert item2.is_resolved

    d2 = item2.to_dict()
    item3 = ReviewItem.from_dict(d2)
    assert item3.is_resolved
    assert item3.resolution is not None
    assert item3.resolution.action == "set_category"
    assert item3.resolution.value == "VEHICLE"


def test_review_action_audit_trail_serialization():
    """ReviewAction serializes and deserializes accurately."""
    act = ReviewAction(
        review_item_id="review:src_1:classification",
        action="set_category",
        old_value="GUN",
        new_value="VEHICLE",
        notes="User override",
    )
    d = act.to_dict()
    assert d["action"] == "set_category"
    assert d["old_value"] == "GUN"
    assert d["new_value"] == "VEHICLE"

    act2 = ReviewAction.from_dict(d)
    assert act2.id == act.id
    assert act2.action == "set_category"


def test_account_session_review_integration():
    """AccountSession serializes and loads review_items, review_history, and uid_manual."""
    session = AccountSession(account_id="acc_test")
    session.uid_manual = "5123456789"
    assert session.effective_uid == "5123456789"

    item = ReviewItem(
        id="review:acc_test:uid",
        subsystem=ReviewSubsystem.UID.value,
        field_name="uid",
        machine_value="1111111111",
    )
    session.review_items[item.id] = item
    session.review_history.append(
        ReviewAction(
            review_item_id=item.id,
            action="set_uid",
            old_value="1111111111",
            new_value="5123456789",
        )
    )

    d = session.to_dict()
    session2 = AccountSession.from_dict(d)
    assert session2.uid_manual == "5123456789"
    assert session2.effective_uid == "5123456789"
    assert len(session2.review_items) == 1
    assert session2.review_items[item.id].subsystem == ReviewSubsystem.UID.value
    assert len(session2.review_history) == 1
    assert session2.review_history[0].action == "set_uid"
