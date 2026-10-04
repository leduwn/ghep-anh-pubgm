"""Unit tests for ScreenClassifier evidence accumulation, decisions, and robustness."""

import cv2
import numpy as np
import pytest

from core.constants import Category, Decision, CLASSIFIER_VERSION
from core.models import Rect
from detectors.classification_context import ClassificationContext
from detectors.screen_classifier import ScreenClassifier


def make_wardrobe_base(w: int = 2778, h: int = 1284, subtab_y: float = 200.0) -> np.ndarray:
    """Builds a synthetic wardrobe screenshot with grid rhythm and smooth subtab rail."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = (35, 30, 25)

    scale_x = w / 2778.0
    scale_y = h / 1284.0

    # Main tab indicator in Outfit band (y ~ 200)
    cv2.rectangle(
        img,
        (int(round(2545 * scale_x)), int(round(170 * scale_y))),
        (int(round(2557 * scale_x)), int(round(230 * scale_y))),
        (220, 140, 20),
        -1,
    )

    # Subtab rail: smooth
    cv2.rectangle(
        img,
        (int(round(2390 * scale_x)), 0),
        (int(round(2495 * scale_x)), h),
        (45, 40, 35),
        -1,
    )

    # Subtab indicator at subtab_y
    if subtab_y is not None:
        cv2.rectangle(
            img,
            (int(round(2440 * scale_x)), int(round((subtab_y - 30) * scale_y))),
            (int(round(2452 * scale_x)), int(round((subtab_y + 30) * scale_y))),
            (220, 140, 20),
            -1,
        )

    # 3-row grid boundaries
    for row in range(3):
        top_y = int(round((210 + row * 267) * scale_y))
        bot_y = int(round((210 + row * 267 + 250) * scale_y))
        img[top_y:top_y + 4, int(round(1718 * scale_x)):int(round(2411 * scale_x))] = 180
        img[bot_y - 4:bot_y, int(round(1718 * scale_x)):int(round(2411 * scale_x))] = 180

    return img


def test_gun_lab_vs_normal_gun_tab():
    classifier = ScreenClassifier()

    # 1. Real Gun Lab screen
    w, h = 2778, 1284
    img_gun_lab = np.zeros((h, w, 3), dtype=np.uint8)
    img_gun_lab[180:1100, 50:1650] = 50  # dark workshop
    img_gun_lab[30:110, 2300:2550] = 230  # bright text
    img_gun_lab[90:180, 2120:2300] = (20, 140, 240)  # orange badge

    ctx_lab = ClassificationContext(img_gun_lab)
    res_lab = classifier.classify(ctx_lab)
    assert res_lab.category == Category.GUN.value
    assert res_lab.decision == Decision.AUTO_ACCEPT.value
    assert res_lab.confidence >= 0.85

    # 2. Normal gun inventory tab: main tab indicator at y=380 (300..475)
    img_normal_gun = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.rectangle(img_normal_gun, (2545, 350), (2557, 410), (220, 140, 20), -1)

    ctx_norm = ClassificationContext(img_normal_gun)
    res_norm = classifier.classify(ctx_norm)
    # Must NOT be classified as GUN
    assert res_norm.category != Category.GUN.value
    assert res_norm.category == Category.OTHER.value
    assert "Normal gun inventory tab detected" in res_norm.reasons[0]


def test_vehicle_classification():
    classifier = ScreenClassifier()
    w, h = 2778, 1284
    img_veh = np.zeros((h, w, 3), dtype=np.uint8)
    # Main tab indicator in Vehicle band (y=550 in 475..665)
    cv2.rectangle(img_veh, (2545, 520), (2557, 580), (220, 140, 20), -1)

    ctx = ClassificationContext(img_veh)
    res = classifier.classify(ctx)
    assert res.category == Category.VEHICLE.value
    assert res.decision == Decision.AUTO_ACCEPT.value
    assert res.confidence >= 0.85


def test_backpack_requires_selector_vs_mask():
    classifier = ScreenClassifier()

    # 1. Subtab y=850 (lower subtab) WITH 3-level backpack selector
    img_bp = make_wardrobe_base(subtab_y=850.0)
    for idx, cy in enumerate([150, 240, 330]):
        cv2.rectangle(img_bp, (1140, cy - 25), (1230, cy + 25), (30, 200, 230), -1)
        cv2.putText(img_bp, f"Lv{idx+1}", (1150, cy + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    ctx_bp = ClassificationContext(img_bp)
    res_bp = classifier.classify(ctx_bp)
    assert res_bp.category == Category.BACKPACK.value
    assert res_bp.decision == Decision.AUTO_ACCEPT.value

    # 2. Same subtab y=850 WITHOUT selector -> must not be BACKPACK! Mask wins
    img_no_sel = make_wardrobe_base(subtab_y=850.0)
    ctx_no_sel = ClassificationContext(img_no_sel)
    res_no_sel = classifier.classify(ctx_no_sel)
    assert res_no_sel.category != Category.BACKPACK.value
    assert res_no_sel.category == Category.MASK.value


def test_item_set_requires_popup_frame_vs_outfit():
    classifier = ScreenClassifier()

    # 1. Wardrobe with popup frame -> ITEM_SET
    img_set = make_wardrobe_base(subtab_y=200.0)
    cv2.line(img_set, (1325, 930), (1325, 1240), (220, 220, 220), 4)
    cv2.line(img_set, (1685, 930), (1685, 1240), (220, 220, 220), 4)

    ctx_set = ClassificationContext(img_set)
    res_set = classifier.classify(ctx_set)
    assert res_set.category == Category.ITEM_SET.value
    assert res_set.decision == Decision.AUTO_ACCEPT.value

    # 2. Wardrobe WITHOUT popup frame -> OUTFIT
    img_outfit = make_wardrobe_base(subtab_y=200.0)
    ctx_outfit = ClassificationContext(img_outfit)
    res_outfit = classifier.classify(ctx_outfit)
    assert res_outfit.category == Category.OUTFIT.value
    assert res_outfit.decision == Decision.AUTO_ACCEPT.value


def test_helmet_subtab():
    classifier = ScreenClassifier()
    # Helmet subtab in y: 300..450 (e.g. y=370)
    img_helmet = make_wardrobe_base(subtab_y=370.0)
    ctx = ClassificationContext(img_helmet)
    res = classifier.classify(ctx)
    assert res.category == Category.HELMET.value
    assert res.decision == Decision.AUTO_ACCEPT.value


def test_outfit_false_positive_rejection():
    classifier = ScreenClassifier()
    # Random landscape with right-side variance but NO wardrobe layout and NO outfit lobby features
    rng = np.random.default_rng(123)
    img = rng.integers(20, 200, size=(1080, 1920, 3), dtype=np.uint8)

    ctx = ClassificationContext(img)
    res = classifier.classify(ctx)
    # Must NOT be AUTO_ACCEPT OUTFIT
    assert res.decision != Decision.AUTO_ACCEPT.value or res.category != Category.OUTFIT.value


def test_confidence_and_ambiguity_margin():
    classifier = ScreenClassifier(accept_threshold=0.85, review_threshold=0.55, ambiguity_margin=0.10)

    # 1. Single clear winner -> AUTO_ACCEPT
    w, h = 2778, 1284
    img_veh = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.rectangle(img_veh, (2545, 520), (2557, 580), (220, 140, 20), -1)
    res_veh = classifier.classify(ClassificationContext(img_veh))
    assert res_veh.decision == Decision.AUTO_ACCEPT.value
    assert res_veh.confidence >= 0.85

    # 2. Ambiguity margin: Wardrobe with subtab indicator placed right at the 450 boundary between HELMET and MASK
    # Helmet is 300..450, Mask is >= 450. Centered at 449 gives Helmet and Mask very close scores
    img_ambig = make_wardrobe_base(subtab_y=449.0)
    res_ambig = classifier.classify(ClassificationContext(img_ambig))
    # Even if score is around 0.80, if top2 are within ambiguity margin, decision must be REVIEW
    assert res_ambig.decision == Decision.REVIEW.value

    # 3. Weak evidence -> UNKNOWN
    img_blank = np.zeros((h, w, 3), dtype=np.uint8)
    res_blank = classifier.classify(ClassificationContext(img_blank))
    assert res_blank.decision == Decision.UNKNOWN.value
    assert res_blank.category == Category.OTHER.value


def test_scale_invariance():
    classifier = ScreenClassifier()
    base = make_wardrobe_base(w=2778, h=1284, subtab_y=200.0)

    for scale in (1.0, 0.75, 0.5):
        sw = max(1, round(2778 * scale))
        sh = max(1, round(1284 * scale))
        scaled = cv2.resize(base, (sw, sh), interpolation=cv2.INTER_AREA)

        ctx = ClassificationContext(scaled)
        res = classifier.classify(ctx)
        assert res.category == Category.OUTFIT.value
        assert res.decision == Decision.AUTO_ACCEPT.value


def test_jpeg_and_brightness_robustness():
    classifier = ScreenClassifier()
    base = make_wardrobe_base(w=2778, h=1284, subtab_y=200.0)

    # 1. JPEG quality 95 and 75
    for q in (95, 75):
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), q]
        success, encoded = cv2.imencode(".jpg", base, encode_param)
        assert success
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

        ctx = ClassificationContext(decoded)
        res = classifier.classify(ctx)
        assert res.category == Category.OUTFIT.value
        assert res.decision in {Decision.AUTO_ACCEPT.value, Decision.REVIEW.value}

    # 2. Brightness -15% and +15%
    for factor in (0.85, 1.15):
        adjusted = np.clip(base.astype(np.float32) * factor, 0, 255).astype(np.uint8)
        ctx = ClassificationContext(adjusted)
        res = classifier.classify(ctx)
        assert res.category == Category.OUTFIT.value


def test_aspect_ratio_safety():
    classifier = ScreenClassifier()
    # Test various aspect ratios without crashing
    for w, h in [(2778, 1284), (1920, 1080), (1440, 1080), (1080, 1080)]:
        dummy = np.zeros((h, w, 3), dtype=np.uint8)
        ctx = ClassificationContext(dummy)
        res = classifier.classify(ctx)
        assert res.category in {c.value for c in Category}
        assert res.decision in {d.value for d in Decision}


def test_context_lazy_caching_no_repeated_conversion(monkeypatch):
    dummy = np.zeros((100, 200, 3), dtype=np.uint8)
    ctx = ClassificationContext(dummy)

    cvt_calls = []
    orig_cvt = cv2.cvtColor

    def spy_cvt(*args, **kwargs):
        cvt_calls.append(args[1] if len(args) > 1 else kwargs.get("code"))
        return orig_cvt(*args, **kwargs)

    monkeypatch.setattr(cv2, "cvtColor", spy_cvt)

    # Access gray three times -> cvtColor only called once for GRAY
    _ = ctx.gray
    _ = ctx.gray
    _ = ctx.gray
    gray_calls = [c for c in cvt_calls if c == cv2.COLOR_BGR2GRAY]
    assert len(gray_calls) == 1

    # Access hsv three times -> cvtColor only called once for HSV
    _ = ctx.hsv
    _ = ctx.hsv
    _ = ctx.hsv
    hsv_calls = [c for c in cvt_calls if c == cv2.COLOR_BGR2HSV]
    assert len(hsv_calls) == 1



def test_accessory_subtypes_separation():
    classifier = ScreenClassifier()
    w, h = 2778, 1284

    # 1. Grenade screen: Tab 4 indicator + 3 header separators (1882, 2063, 2246) in y=75..155
    img_grenade = np.zeros((h, w, 3), dtype=np.uint8)
    # Tab 4 indicator (y=750 in 665..900)
    cv2.rectangle(img_grenade, (2545, 720), (2557, 780), (220, 140, 20), -1)
    # 3 header separators
    for sx in (1882, 2063, 2246):
        cv2.line(img_grenade, (sx, 75), (sx, 155), (240, 240, 240), 4)
    # Card grid rows
    for row in range(2):
        cy = 300 + row * 267
        img_grenade[cy:cy + 250, 1718:2411] = 60

    ctx_g = ClassificationContext(img_grenade)
    res_g = classifier.classify(ctx_g)
    assert res_g.category == Category.GRENADE.value
    assert res_g.category != Category.PARACHUTE.value
    assert res_g.category != Category.EMOTE.value

    # 2. Misc tab screen: Tab 5 indicator (y=980 in 900..1150)
    img_misc = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.rectangle(img_misc, (2545, 950), (2557, 1010), (220, 140, 20), -1)
    ctx_m = ClassificationContext(img_misc)
    res_m = classifier.classify(ctx_m)
    assert res_m.category == Category.MISC.value
    assert res_m.decision == Decision.AUTO_ACCEPT.value

