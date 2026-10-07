"""Comprehensive test suite for Milestone 4 specialized detectors, CategoryRouter, and fallback."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from core.constants import (
    Category,
    GUN_DETECTOR_VERSION,
    VEHICLE_DETECTOR_VERSION,
    OUTFIT_DETECTOR_VERSION,
    EQUIPMENT_DETECTOR_VERSION,
    ACCESSORY_DETECTOR_VERSION,
    INVENTORY_DETECTOR_VERSION,
    ROUTER_VERSION,
    MISC_GRID_VERSION,
)
from core.models import Rect, ClassificationResult, SourceImage
from core.settings import AutoCutSettings
from detectors.detection_context import DetectionContext
from detectors.card_quality import CardQualityEvaluator
from detectors.gun_detector import GunDetector
from detectors.vehicle_detector import VehicleDetector
from detectors.outfit_detector import OutfitDetector
from detectors.equipment_detector import EquipmentDetector
from detectors.accessory_detector import AccessoryDetector
from detectors.inventory_detector import InventoryDetector
from detectors.router import CategoryRouter
from detectors.dedup import AccountDeduplicator, DedupProfile, DEFAULT_CATEGORY_DEDUP_PROFILES, are_visually_identical


def create_blank_bgr(w: int = 1280, h: int = 720, color: tuple[int, int, int] = (20, 20, 20)) -> np.ndarray:
    """Helper creating a solid background BGR image."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


def make_context(bgr: np.ndarray, source_id: str = "src_test") -> DetectionContext:
    """Helper wrapping a BGR image into a DetectionContext."""
    return DetectionContext(
        bgr,
        source_id=source_id,
        source_sha256="testsha256" * 4,
        max_scan_dim=1280,
    )


# ==============================================================================
# GunDetector Tests
# ==============================================================================

def test_gun_detector_workshop_card():
    """Workshop weapon card with orange border contour is detected and metadata ROIs populated."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(15, 15, 15))

    # Place an orange-bordered card in the right workshop region (x >= 0.55 * W)
    card_x, card_y, card_w, card_h = 1200, 300, 480, 240
    # Orange HSV is around H: 5..30, S: 100..255, V: 100..255
    # In BGR: Orange is roughly (30, 140, 240)
    cv2.rectangle(img, (card_x, card_y), (card_x + card_w, card_y + card_h), (30, 140, 240), 8)
    # Fill inside with card content
    cv2.rectangle(img, (card_x + 8, card_y + 8), (card_x + card_w - 8, card_y + card_h - 8), (80, 80, 80), -1)

    ctx = make_context(img)
    detector = GunDetector(inner_trim_px=4)
    res = detector.detect(ctx)

    assert res.detected is True
    assert res.fallback_recommended is False
    assert len(res.candidates) == 1
    assert res.detector_name == "gun_workshop_detector"
    assert res.detector_version == GUN_DETECTOR_VERSION

    cand = res.candidates[0]
    assert cand.geometry_score == 1.0
    assert "level_roi" in res.metadata
    assert "name_roi" in res.metadata
    assert "kill_counter_roi" in res.metadata


def test_gun_detector_fallback_on_blank():
    """Blank screen without weapon workshop card triggers fallback."""
    img = create_blank_bgr(1280, 720, color=(10, 10, 10))
    ctx = make_context(img)
    detector = GunDetector()
    res = detector.detect(ctx)

    assert res.detected is False
    assert res.fallback_recommended is True
    assert len(res.candidates) == 0


# ==============================================================================
# VehicleDetector Tests
# ==============================================================================

def test_vehicle_detector_wide_cards():
    """Vehicle gallery column with aspect 2.1..3.1 cards is detected with border trimming."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(25, 25, 25))

    # Gallery column located around x: 0.64..0.88 * W -> x: 1300..1650
    card_x = 1350
    card_w = 300
    card_h = 115  # Aspect ratio: ~2.60

    # Draw 3 vehicle cards vertically
    for i in range(3):
        card_y = 200 + i * 160
        cv2.rectangle(img, (card_x, card_y), (card_x + card_w, card_y + card_h), (180, 180, 180), 2)
        cv2.rectangle(img, (card_x + 4, card_y + 4), (card_x + card_w - 4, card_y + card_h - 4), (70, 70, 70), -1)

    ctx = make_context(img)
    detector = VehicleDetector(border_trim_px=3)
    res = detector.detect(ctx)

    assert res.detected is True
    assert res.fallback_recommended is False
    assert len(res.candidates) >= 1
    assert res.detector_name == "vehicle_card_detector"
    assert res.detector_version == VEHICLE_DETECTOR_VERSION


def test_vehicle_detector_fallback_on_blank():
    """Blank screen triggers fallback for vehicle detector."""
    img = create_blank_bgr(1280, 720)
    ctx = make_context(img)
    detector = VehicleDetector()
    res = detector.detect(ctx)

    assert res.detected is False
    assert res.fallback_recommended is True


# ==============================================================================
# OutfitDetector Tests
# ==============================================================================

def test_outfit_detector_normal_lobby():
    """Normal lobby extracts character bounding crop based on Sobel edge density."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(40, 40, 40))

    # Place a textured vertical object in character region (anchor ~ 0.30 * W)
    char_x = int(0.30 * w)
    cv2.rectangle(img, (char_x - 100, 100), (char_x + 100, 950), (120, 120, 120), -1)
    # Add texture/edges
    for y in range(150, 900, 20):
        cv2.line(img, (char_x - 80, y), (char_x + 80, y), (200, 200, 200), 2)

    ctx = make_context(img)
    detector = OutfitDetector()
    res = detector.detect(ctx)

    assert res.detected is True
    assert res.fallback_recommended is False
    assert len(res.candidates) == 1
    assert res.detector_name == "outfit_character_detector"
    assert res.detector_version == OUTFIT_DETECTOR_VERSION
    assert res.candidates[0].rect_original.w > 0
    assert res.candidates[0].rect_original.h > 0


def test_outfit_detector_wardrobe_inventory_fallback():
    """Wardrobe inventory screens route to generic fallback rather than character extraction."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(30, 30, 30))

    # Place wardrobe inventory cards on the right
    start_x = int(0.65 * w)
    start_y = int(0.20 * h)
    for r in range(2):
        for c in range(2):
            tx = start_x + c * 120
            ty = start_y + r * 120
            cv2.rectangle(img, (tx, ty), (tx + 100, ty + 100), (160, 160, 160), 2)
            cv2.rectangle(img, (tx + 4, ty + 4), (tx + 96, ty + 96), (70, 70, 70), -1)

    ctx = make_context(img)
    detector = OutfitDetector()
    class_res = ClassificationResult(
        category=Category.OUTFIT.value,
        confidence=0.92,
        reasons=["Wardrobe outfit inventory layout without detail popup"],
    )
    res = detector.detect(ctx, classification=class_res)

    assert res.detected is False
    assert res.fallback_recommended is True
    assert "inventory grid" in res.reasons[0].lower()


# ==============================================================================
# Equipment, Accessory, and Inventory Detectors Tests
# ==============================================================================

def test_equipment_detector_grid():
    """Equipment detector reconstructs cards within inventory bounds."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(30, 30, 30))

    # Place a 3x3 grid in inventory bounds: x: 0.58..0.89 * W, y: 0.22..0.92 * H
    start_x = int(0.62 * w)
    start_y = int(0.25 * h)
    tile_w, tile_h = 100, 100
    gap = 20

    for r in range(3):
        for c in range(3):
            tx = start_x + c * (tile_w + gap)
            ty = start_y + r * (tile_h + gap)
            cv2.rectangle(img, (tx, ty), (tx + tile_w, ty + tile_h), (160, 160, 160), 2)
            cv2.rectangle(img, (tx + 4, ty + 4), (tx + tile_w - 4, ty + tile_h - 4), (80, 80, 80), -1)

    ctx = make_context(img)
    detector = EquipmentDetector()
    class_res = ClassificationResult(category=Category.HELMET.value, confidence=0.9)
    res = detector.detect(ctx, classification=class_res)

    assert res.detected is True
    assert res.detector_name == "equipment_grid_detector"
    assert res.detector_version == EQUIPMENT_DETECTOR_VERSION
    assert len(res.candidates) == 9


def test_accessory_detector_grenade_tab_exclusion():
    """Accessory detector excludes grenade tabs (y < 0.22 * H)."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(30, 30, 30))

    # Place a tab header tile at y = 0.10 * H (should be excluded)
    tab_x = int(0.65 * w)
    tab_y = int(0.10 * h)
    cv2.rectangle(img, (tab_x, tab_y), (tab_x + 90, tab_y + 90), (200, 200, 200), 2)

    # Place valid grid at y = 0.26 * H
    start_x = int(0.62 * w)
    start_y = int(0.26 * h)
    tile_w, tile_h = 90, 90
    for r in range(2):
        for c in range(2):
            tx = start_x + c * (tile_w + 15)
            ty = start_y + r * (tile_h + 15)
            cv2.rectangle(img, (tx, ty), (tx + tile_w, ty + tile_h), (160, 160, 160), 2)
            cv2.rectangle(img, (tx + 3, ty + 3), (tx + tile_w - 3, ty + tile_h - 3), (75, 75, 75), -1)

    ctx = make_context(img)
    detector = AccessoryDetector()
    class_res = ClassificationResult(category=Category.GRENADE.value, confidence=0.9)
    res = detector.detect(ctx, classification=class_res)

    assert res.detected is True
    assert res.detector_name == "accessory_grid_detector"
    assert res.detector_version == ACCESSORY_DETECTOR_VERSION
    # Tab tile at y=0.10*H should not be in the candidates
    assert all(cand.rect_scan.y >= int(0.20 * ctx.scan_h) for cand in res.candidates)


def test_inventory_detector_bounded():
    """Inventory detector extracts cards in right inventory ROI."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(30, 30, 30))

    start_x = int(0.65 * w)
    start_y = int(0.20 * h)
    for r in range(2):
        for c in range(2):
            tx = start_x + c * 110
            ty = start_y + r * 110
            cv2.rectangle(img, (tx, ty), (tx + 95, ty + 95), (150, 150, 150), 2)
            cv2.rectangle(img, (tx + 3, ty + 3), (tx + 92, ty + 92), (70, 70, 70), -1)

    ctx = make_context(img)
    detector = InventoryDetector()
    class_res = ClassificationResult(category=Category.ITEM_SET.value, confidence=0.9)
    res = detector.detect(ctx, classification=class_res)

    assert res.detected is True
    assert res.detector_name == "inventory_grid_detector"
    assert res.detector_version == INVENTORY_DETECTOR_VERSION
    assert len(res.candidates) == 4


# ==============================================================================
# CategoryRouter & Shared-Context Fallback Tests
# ==============================================================================

def test_category_router_dispatch_mapping():
    """Router correctly resolves detectors for all PUBG Mobile categories."""
    router = CategoryRouter()

    assert router.get_detector_for_category(Category.GUN.value)[1] == "gun_workshop_detector"
    assert router.get_detector_for_category(Category.VEHICLE.value)[1] == "vehicle_card_detector"
    assert router.get_detector_for_category(Category.OUTFIT.value)[1] == "outfit_character_detector"
    assert router.get_detector_for_category(Category.HELMET.value)[1] == "equipment_grid_detector"
    assert router.get_detector_for_category(Category.BACKPACK.value)[1] == "equipment_grid_detector"
    assert router.get_detector_for_category(Category.MASK.value)[1] == "equipment_grid_detector"
    assert router.get_detector_for_category(Category.GRENADE.value)[1] == "accessory_grid_detector"
    assert router.get_detector_for_category(Category.PARACHUTE.value)[1] == "accessory_grid_detector"
    assert router.get_detector_for_category(Category.EMOTE.value)[1] == "accessory_grid_detector"
    assert router.get_detector_for_category(Category.ITEM_SET.value)[1] == "inventory_grid_detector"
    assert router.get_detector_for_category(Category.MISC.value)[1] == "inventory_grid_detector"


def test_category_router_shared_context_fallback():
    """When specialized detector yields no candidates, fallback to GenericGridDetector runs on same context."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(20, 20, 20))

    # Place a regular 2x2 grid that does NOT match gun workshop orange card
    start_x = int(0.20 * w)
    start_y = int(0.20 * h)
    for r in range(2):
        for c in range(2):
            tx = start_x + c * 150
            ty = start_y + r * 150
            cv2.rectangle(img, (tx, ty), (tx + 120, ty + 120), (180, 180, 180), 2)
            cv2.rectangle(img, (tx + 4, ty + 4), (tx + 116, ty + 116), (70, 70, 70), -1)

    ctx = make_context(img)
    router = CategoryRouter()
    # Classified as GUN, but screen has generic grid in left/center
    class_res = ClassificationResult(category=Category.GUN.value, confidence=0.85)

    res = router.route(ctx, classification=class_res)

    # Fallback should have been triggered
    assert res.metadata["fallback_used"] is True
    assert res.metadata["primary_detector"] == "gun_workshop_detector"
    assert res.metadata["fallback_detector"] == "generic_grid_detector"
    assert res.detector_name == "generic_grid_detector"
    assert res.detector_version == MISC_GRID_VERSION
    assert res.detected is True

    # Asset creation preserves full provenance
    assets = router.create_assets_from_result(res, ctx, category=class_res.category)
    assert len(assets) > 0
    for a in assets:
        assert a.metadata["primary_detector"] == "gun_workshop_detector"
        assert a.metadata["fallback_detector"] == "generic_grid_detector"
        assert a.metadata["fallback_used"] is True


def test_category_router_success_provenance():
    """Successful specialized detection records primary_detector and fallback_used=False."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(15, 15, 15))

    card_x, card_y, card_w, card_h = 1200, 300, 480, 240
    cv2.rectangle(img, (card_x, card_y), (card_x + card_w, card_y + card_h), (30, 140, 240), 8)
    cv2.rectangle(img, (card_x + 8, card_y + 8), (card_x + card_w - 8, card_y + card_h - 8), (80, 80, 80), -1)

    ctx = make_context(img)
    router = CategoryRouter()
    class_res = ClassificationResult(category=Category.GUN.value, confidence=0.95)

    res = router.route(ctx, classification=class_res)

    assert res.detected is True
    assert res.metadata["primary_detector"] == "gun_workshop_detector"
    assert res.metadata["fallback_detector"] is None
    assert res.metadata["fallback_used"] is False
    assert res.detector_name == "gun_workshop_detector"

    assets = router.create_assets_from_result(res, ctx, category=class_res.category)
    assert len(assets) == 1
    assert assets[0].metadata["primary_detector"] == "gun_workshop_detector"
    assert assets[0].metadata["fallback_used"] is False


# ==============================================================================
# Category Dedup Profiles Tests
# ==============================================================================

def test_dedup_category_profiles_structure():
    """Category-specific dedup profiles exist with distinct thresholds."""
    assert "GUN" in DEFAULT_CATEGORY_DEDUP_PROFILES
    assert "VEHICLE" in DEFAULT_CATEGORY_DEDUP_PROFILES
    assert "OUTFIT" in DEFAULT_CATEGORY_DEDUP_PROFILES

    gun_prof = DEFAULT_CATEGORY_DEDUP_PROFILES["GUN"]
    assert gun_prof.phash_threshold == 4
    assert gun_prof.diff_threshold == 6.0

    veh_prof = DEFAULT_CATEGORY_DEDUP_PROFILES["VEHICLE"]
    assert veh_prof.phash_threshold == 8
    assert veh_prof.diff_threshold == 10.0


def test_dedup_evaluates_with_category_profile():
    """AccountDeduplicator applies category-specific diff and phash thresholds."""
    tile1 = np.zeros((100, 100, 3), dtype=np.uint8)
    tile1[:, :] = (35, 30, 25)
    cv2.circle(tile1, (50, 50), 30, (180, 180, 180), -1)

    tile2 = tile1.copy()
    cv2.rectangle(tile2, (38, 38), (62, 62), (250, 250, 250), -1)

    _, mae, dist = are_visually_identical(tile1, tile2, diff_threshold=999.0, phash_threshold=64)
    assert mae > 0.5

    custom_profiles = {
        "GUN": DedupProfile(name="GUN", diff_threshold=mae * 0.7, phash_threshold=max(dist + 2, 10)),
        "VEHICLE": DedupProfile(name="VEHICLE", diff_threshold=mae * 1.4, phash_threshold=max(dist + 2, 10)),
    }
    dedup = AccountDeduplicator(category_profiles=custom_profiles)

    # For GUN (strict threshold), MAE > threshold -> NOT identical
    is_gun_dup, *_ = dedup.are_visually_identical(tile1, tile2, category="GUN")
    assert is_gun_dup is False

    # For VEHICLE (relaxed threshold), MAE < threshold -> IS identical
    is_veh_dup, *_ = dedup.are_visually_identical(tile1, tile2, category="VEHICLE")
    assert is_veh_dup is True


# ==============================================================================
# Milestone 4.1 Regression Tests (Tri-State Fallback, Provenance, Invalidation)
# ==============================================================================

def test_category_router_case_a_direct_specialized():
    """Case A: Strong specialized detection bypasses generic fallback entirely."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(15, 15, 15))

    card_x, card_y, card_w, card_h = 1200, 300, 480, 240
    cv2.rectangle(img, (card_x, card_y), (card_x + card_w, card_y + card_h), (30, 140, 240), 8)
    cv2.rectangle(img, (card_x + 8, card_y + 8), (card_x + card_w - 8, card_y + card_h - 8), (80, 80, 80), -1)

    ctx = make_context(img)
    router = CategoryRouter()
    class_res = ClassificationResult(category=Category.GUN.value, confidence=0.95)

    res = router.route(ctx, classification=class_res)

    assert res.detected is True
    assert res.metadata["primary_detector"] == "gun_workshop_detector"
    assert res.metadata["fallback_detector"] is None
    assert res.metadata["fallback_attempted"] is False
    assert res.metadata["fallback_used"] is False
    assert res.metadata["specialized_attempted"] is True
    assert res.metadata["specialized_success"] is True
    assert res.metadata["fallback_success"] is False
    assert res.detector_name == "gun_workshop_detector"


def test_category_router_case_b_specialized_failed_generic_succeeds():
    """Case B: When specialized fails, generic fallback is executed and selected."""
    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(20, 20, 20))

    start_x = int(0.20 * w)
    start_y = int(0.20 * h)
    for r in range(2):
        for c in range(2):
            tx = start_x + c * 150
            ty = start_y + r * 150
            cv2.rectangle(img, (tx, ty), (tx + 120, ty + 120), (180, 180, 180), 2)
            cv2.rectangle(img, (tx + 4, ty + 4), (tx + 116, ty + 116), (70, 70, 70), -1)

    ctx = make_context(img)
    router = CategoryRouter()
    class_res = ClassificationResult(category=Category.GUN.value, confidence=0.85)

    res = router.route(ctx, classification=class_res)

    assert res.detected is True
    assert res.metadata["primary_detector"] == "gun_workshop_detector"
    assert res.metadata["fallback_detector"] == "generic_grid_detector"
    assert res.metadata["fallback_attempted"] is True
    assert res.metadata["fallback_used"] is True
    assert res.metadata["specialized_attempted"] is True
    assert res.metadata["specialized_success"] is False
    assert res.metadata["fallback_success"] is True
    assert res.detector_name == "generic_grid_detector"


def test_category_router_case_b_both_fail():
    """Case B: When both specialized and generic fallback fail on blank image."""
    img = create_blank_bgr(1280, 720, color=(10, 10, 10))
    ctx = make_context(img)
    router = CategoryRouter()
    class_res = ClassificationResult(category=Category.GUN.value, confidence=0.85)

    res = router.route(ctx, classification=class_res)

    assert res.detected is False
    assert res.metadata["fallback_attempted"] is True
    assert res.metadata["fallback_used"] is False
    assert res.metadata["specialized_attempted"] is True
    assert res.metadata["specialized_success"] is False
    assert res.metadata["fallback_success"] is False


def test_category_router_case_c_comparison(monkeypatch):
    """Case C: When specialized is weak, compare with generic fallback."""
    from detectors.detector_models import CardCandidate, SpecializedDetectionResult, GridDetectionResult

    w, h = 1920, 1080
    img = create_blank_bgr(w, h, color=(20, 20, 20))
    ctx = make_context(img)
    router = CategoryRouter(detector_confidence_threshold=0.60)
    class_res = ClassificationResult(category=Category.GUN.value, confidence=0.85)

    # Sub-case 1: Generic is clearly better (fallback_conf > specialized_conf)
    dummy_cand = CardCandidate(
        rect_scan=Rect(10, 10, 50, 50),
        rect_original=Rect(10, 10, 50, 50),
        content_rect_original=Rect(10, 10, 50, 50),
        confidence=0.40,
    )
    weak_spec = SpecializedDetectionResult(
        detected=True,
        confidence=0.40,
        candidates=[dummy_cand],
        accepted=[dummy_cand],
        detector_name="gun_workshop_detector",
        detector_version="1.0.0",
    )
    monkeypatch.setattr(router.gun_detector, "detect", lambda *args, **kwargs: weak_spec)

    # Mock generic detector to return strong result (conf = 0.85)
    strong_cand = CardCandidate(
        rect_scan=Rect(20, 20, 60, 60),
        rect_original=Rect(20, 20, 60, 60),
        content_rect_original=Rect(20, 20, 60, 60),
        confidence=0.85,
    )
    strong_generic = GridDetectionResult(
        detected=True,
        grid_confidence=0.85,
        candidates=[strong_cand],
        accepted=[strong_cand],
    )
    monkeypatch.setattr(router.generic_grid_detector, "detect", lambda *args, **kwargs: strong_generic)

    res1 = router.route(ctx, classification=class_res)
    assert res1.metadata["fallback_attempted"] is True
    assert res1.metadata["fallback_used"] is True
    assert res1.metadata["fallback_success"] is True
    assert res1.detector_name == "generic_grid_detector"

    # Sub-case 2: Specialized is better than generic fallback (specialized_conf >= fallback_conf)
    weak_generic = GridDetectionResult(
        detected=True,
        grid_confidence=0.30,
        candidates=[strong_cand],
        accepted=[strong_cand],
    )
    monkeypatch.setattr(router.generic_grid_detector, "detect", lambda *args, **kwargs: weak_generic)

    res2 = router.route(ctx, classification=class_res)
    assert res2.metadata["fallback_attempted"] is True
    assert res2.metadata["fallback_used"] is False
    assert res2.metadata["specialized_success"] is True
    assert res2.detector_name == "gun_workshop_detector"
    assert res2.metadata["review_required"] is True
    assert all(c.review_required for c in res2.candidates)


def test_semantic_fallback_review_policy_case1_generic_fails():
    """Case 1: Semantic fallback attempted but generic fails -> attempted=True, used=False."""
    w, h = 1280, 720
    img = create_blank_bgr(w, h, color=(20, 20, 20))
    ctx = make_context(img)
    router = CategoryRouter()

    for semantic_cat in [Category.GUN.value, Category.VEHICLE.value, Category.OUTFIT.value]:
        class_res = ClassificationResult(category=semantic_cat, confidence=0.85)
        res = router.route(ctx, classification=class_res)
        assert res.metadata["fallback_attempted"] is True
        assert res.metadata["fallback_used"] is False
        assert res.detected is False


def test_semantic_fallback_review_policy_case2_generic_succeeds(monkeypatch):
    """Case 2: Generic grid succeeds for semantic category -> fallback_attempted=True, fallback_used=True, review_required=True."""
    from detectors.detector_models import CardCandidate, GridDetectionResult

    w, h = 1280, 720
    img = create_blank_bgr(w, h, color=(20, 20, 20))
    ctx = make_context(img)
    router = CategoryRouter()

    cand = CardCandidate(
        rect_scan=Rect(100, 100, 80, 80),
        rect_original=Rect(100, 100, 80, 80),
        content_rect_original=Rect(100, 100, 80, 80),
        confidence=0.90,
    )
    fake_grid_res = GridDetectionResult(
        detected=True,
        grid_confidence=0.88,
        candidates=[cand],
        accepted=[cand],
    )
    monkeypatch.setattr(router.generic_grid_detector, "detect", lambda c: fake_grid_res)

    for semantic_cat in [Category.GUN.value, Category.VEHICLE.value, Category.OUTFIT.value]:
        class_res = ClassificationResult(category=semantic_cat, confidence=0.85)
        res = router.route(ctx, classification=class_res)
        assert res.metadata["fallback_attempted"] is True
        assert res.metadata["fallback_used"] is True
        assert res.detected is True

        assets = router.create_assets_from_result(res, ctx, category=semantic_cat)
        assert len(assets) > 0
        for a in assets:
            assert a.review_required is True
            assert any("Semantic fallback" in reason for reason in a.review_reasons)


def test_session_invalidate_detection_assets_preserves_manual():
    """AccountSession.invalidate_detection_assets_for_source purges M4 assets but keeps manual_override."""
    from core.models import AccountSession, DetectedAsset

    session = AccountSession(account_id="acc_test")

    # Add M4 detected assets for source "src_1"
    a1 = DetectedAsset(
        id="asset_gun_1",
        source_id="src_1",
        category="GUN",
        crop_rect=Rect(10, 10, 50, 50),
        native_width=50,
        native_height=50,
        detector="gun_workshop_detector",
        detector_version="1.0.0",
        manual_override=False,
    )
    a2 = DetectedAsset(
        id="asset_gen_1",
        source_id="src_1",
        category="GUN",
        crop_rect=Rect(70, 70, 50, 50),
        native_width=50,
        native_height=50,
        detector="generic_grid_detector",
        detector_version="2.1.0",
        manual_override=False,
    )
    # Add manual asset for "src_1"
    a_manual = DetectedAsset(
        id="asset_manual_1",
        source_id="src_1",
        category="GUN",
        crop_rect=Rect(130, 130, 50, 50),
        native_width=50,
        native_height=50,
        detector="manual",
        detector_version="1.0.0",
        manual_override=True,
    )
    # Add asset for another source "src_2"
    a_other = DetectedAsset(
        id="asset_src2_1",
        source_id="src_2",
        category="GUN",
        crop_rect=Rect(10, 10, 50, 50),
        native_width=50,
        native_height=50,
        detector="gun_workshop_detector",
        detector_version="1.0.0",
        manual_override=False,
    )

    session.add_asset(a1)
    session.add_asset(a2)
    session.add_asset(a_manual)
    session.add_asset(a_other)
    session.record_manual_change("test_manual_edit", {"asset_id": "asset_manual_1"})

    assert len(session.assets) == 4
    assert len(session.manual_changes) == 1

    # Invalidate detection assets for "src_1"
    removed = session.invalidate_detection_assets_for_source("src_1")
    assert removed == 2
    assert len(session.assets) == 2

    remaining_ids = {a.id for a in session.assets}
    assert "asset_manual_1" in remaining_ids
    assert "asset_src2_1" in remaining_ids
    assert "asset_gun_1" not in remaining_ids
    assert "asset_gen_1" not in remaining_ids
    assert len(session.manual_changes) == 1


def test_composite_cache_key_invalidation():
    """Cache key changes whenever ROUTER_VERSION, primary detector version, MISC_GRID_VERSION, or thresholds change."""
    from core.cache import CacheKeyGenerator

    sha = "testsha256" * 4

    def gen(router_v, prim_v, misc_v, conf_t, lock_t, empty_t):
        token = (
            f"router:{router_v}:"
            f"primary:gun_workshop@{prim_v}:"
            f"fallback:generic_grid@{misc_v}:"
            f"cat:GUN:"
            f"conf{conf_t:.2f}:"
            f"l{lock_t:.2f}:"
            f"e{empty_t:.2f}"
        )
        return CacheKeyGenerator.generate(
            image_sha256=sha,
            crop_rect=None,
            subsystem_version=router_v,
            route=token,
        )

    base_k = gen("1.1.0", "1.0.0", "2.1.0", 0.60, 0.50, 0.35)

    assert base_k != gen("1.2.0", "1.0.0", "2.1.0", 0.60, 0.50, 0.35)  # router bump
    assert base_k != gen("1.1.0", "1.1.0", "2.1.0", 0.60, 0.50, 0.35)  # primary bump
    assert base_k != gen("1.1.0", "1.0.0", "2.2.0", 0.60, 0.50, 0.35)  # misc grid bump
    assert base_k != gen("1.1.0", "1.0.0", "2.1.0", 0.70, 0.50, 0.35)  # conf threshold change
    assert base_k != gen("1.1.0", "1.0.0", "2.1.0", 0.60, 0.55, 0.35)  # lock threshold change
    assert base_k != gen("1.1.0", "1.0.0", "2.1.0", 0.60, 0.50, 0.40)  # empty threshold change

