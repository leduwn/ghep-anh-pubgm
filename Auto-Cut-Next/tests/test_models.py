"""Unit tests for core models, geometries, and serialization."""

import pytest
from core.constants import Category, SourceStatus, SESSION_SCHEMA_VERSION
from core.exceptions import SessionCorruptError
from core.models import (
    Rect,
    SourceImage,
    ClassificationResult,
    GunMetadata,
    VehicleMetadata,
    OutfitMetadata,
    DetectedAsset,
    AccountSession,
)


def test_rect_properties_and_math():
    r = Rect(10, 20, 100, 50)
    assert r.x == 10
    assert r.y == 20
    assert r.w == 100
    assert r.h == 50
    assert r.right == 110
    assert r.bottom == 70
    assert r.area == 5000
    assert r.aspect_ratio == 2.0


def test_rect_validation():
    with pytest.raises(ValueError):
        Rect(0, 0, -1, 10)
    with pytest.raises(ValueError):
        Rect(0, 0, 10, -5)


def test_rect_intersection_and_iou():
    r1 = Rect(0, 0, 100, 100)
    r2 = Rect(50, 50, 100, 100)
    inter = r1.intersection(r2)
    assert inter == Rect(50, 50, 50, 50)
    assert inter.area == 2500

    # IoU: inter=2500, union=10000+10000-2500=17500 -> 2500/17500 = 1/7
    assert pytest.approx(r1.iou(r2), 0.001) == 2500.0 / 17500.0

    # Disjoint rects
    r3 = Rect(200, 200, 10, 10)
    assert r1.intersection(r3) is None
    assert r1.iou(r3) == 0.0


def test_rect_scale():
    r = Rect(10, 20, 100, 50)
    scaled = r.scale(0.5, 2.0)
    assert scaled == Rect(5, 40, 50, 100)


def test_rect_serialization():
    r = Rect(15, 25, 300, 150)
    d = r.to_dict()
    assert d == {"x": 15, "y": 25, "w": 300, "h": 150}
    rebuilt = Rect.from_dict(d)
    assert rebuilt == r


def test_source_image_serialization():
    src = SourceImage(
        id="src_001",
        path="C:/photos/pubg1.png",
        sha256="abc123def456",
        filename="pubg1.png",
        width=1920,
        height=1080,
        mtime=1700000000.0,
        source_index=1,
    )
    d = src.to_dict()
    assert d["sha256"] == "abc123def456"
    rebuilt = SourceImage.from_dict(d)
    assert rebuilt.id == src.id
    assert rebuilt.filename == src.filename
    assert rebuilt.width == 1920


def test_classification_result_serialization():
    cr = ClassificationResult(
        category=Category.GUN.value,
        confidence=0.96,
        reasons=["title anchor matched", "kill counter detected"],
    )
    d = cr.to_dict()
    rebuilt = ClassificationResult.from_dict(d)
    assert rebuilt.category == Category.GUN.value
    assert rebuilt.confidence == 0.96
    assert len(rebuilt.reasons) == 2


def test_gun_metadata_manual_override():
    meta = GunMetadata(
        level=4,
        weapon_name="M416 Băng Tộc",
        weapon_family="M416",
        kill_counter="0123",
        ocr_confidence=0.88,
    )
    assert meta.effective_level == 4
    assert meta.effective_name == "M416 Băng Tộc"

    # Manual overrides take precedence
    meta.level_manual = 7
    meta.name_manual = "M416 Băng Tộc Max"
    assert meta.effective_level == 7
    assert meta.effective_name == "M416 Băng Tộc Max"

    d = meta.to_dict()
    rebuilt = GunMetadata.from_dict(d)
    assert rebuilt.effective_level == 7
    assert rebuilt.effective_name == "M416 Băng Tộc Max"


def test_detected_asset_serialization():
    crop = Rect(50, 100, 365, 177)
    asset = DetectedAsset(
        id="asset_01",
        source_id="src_001",
        category=Category.GUN.value,
        crop_rect=crop,
        native_width=365,
        native_height=177,
        detector="gun_detector",
        detector_version="1.0.0",
        confidence=0.95,
        metadata={"level": 7, "weapon_name": "M416"},
    )
    d = asset.to_dict()
    assert d["crop_rect"] == {"x": 50, "y": 100, "w": 365, "h": 177}
    rebuilt = DetectedAsset.from_dict(d)
    assert rebuilt.id == asset.id
    assert rebuilt.crop_rect == crop
    assert rebuilt.metadata["level"] == 7


def test_account_session_lifecycle_and_dedup():
    session = AccountSession(account_id="ACC999")
    assert session.version == SESSION_SCHEMA_VERSION

    src1 = SourceImage("s1", "p1.png", "hash_aaa", "p1.png", 1920, 1080, 1.0, 1)
    src2_dup = SourceImage("s2", "p2.png", "hash_aaa", "p2.png", 1920, 1080, 2.0, 2)
    src3_new = SourceImage("s3", "p3.png", "hash_bbb", "p3.png", 1920, 1080, 3.0, 3)

    assert session.add_source(src1) is True
    # Duplicate sha256 must be rejected
    assert session.add_source(src2_dup) is False
    assert len(session.sources) == 1

    assert session.add_source(src3_new) is True
    assert len(session.sources) == 2

    # Query source by sha256
    found = session.get_source_by_sha256("hash_aaa")
    assert found is not None
    assert found.id == "s1"
    assert session.get_source_by_sha256("nonexistent") is None

    # Assets & Category filtering
    a1 = DetectedAsset("a1", "s1", Category.GUN.value, Rect(0, 0, 10, 10), 10, 10, "det", "1.0")
    a2 = DetectedAsset("a2", "s1", Category.GUN.value, Rect(0, 0, 10, 10), 10, 10, "det", "1.0", locked=True)
    a3 = DetectedAsset("a3", "s3", Category.VEHICLE.value, Rect(0, 0, 10, 10), 10, 10, "det", "1.0")

    session.add_asset(a1)
    session.add_asset(a2)
    session.add_asset(a3)

    # get_assets_by_category filters out locked/empty/partial items
    guns = session.get_assets_by_category("GUN")
    assert len(guns) == 1
    assert guns[0].id == "a1"

    # Manual change logging
    session.record_manual_change("SET_LEVEL", {"asset_id": "a1", "level": 7})
    assert len(session.manual_changes) == 1
    assert session.manual_changes[0]["action"] == "SET_LEVEL"

    # Roundtrip serialization
    d = session.to_dict()
    rebuilt = AccountSession.from_dict(d)
    assert rebuilt.account_id == "ACC999"
    assert len(rebuilt.sources) == 2
    assert len(rebuilt.assets) == 3
    assert len(rebuilt.manual_changes) == 1


def test_account_session_corrupt_data():
    with pytest.raises(SessionCorruptError):
        AccountSession.from_dict({"not_account_id": 123})
