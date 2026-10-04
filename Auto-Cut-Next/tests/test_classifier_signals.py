"""Unit tests for individual feature signals extracted from ClassificationContext."""

import cv2
import numpy as np
import pytest

from core.constants import Category
from core.models import Rect
from detectors.classification_context import ClassificationContext
from detectors.classification_signals import (
    detect_blue_indicator,
    detect_gun_lab_signals,
    detect_wardrobe_signals,
    detect_backpack_selector_signals,
    detect_detail_popup_signals,
    detect_accessory_signals,
    detect_outfit_lobby_signals,
)


def make_blank_context(w: int = 1920, h: int = 1080, color=(30, 30, 30)) -> ClassificationContext:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = color
    return ClassificationContext(img)


def test_blue_indicator_strict_vs_relaxed_and_noise_rejection():
    # Synthetic canvas 2778x1284
    w, h = 2778, 1284
    img = np.zeros((h, w, 3), dtype=np.uint8)

    # 1. Add small blue noise icon (should be rejected because small height / area)
    cv2.rectangle(img, (2540, 200), (2550, 210), (255, 180, 0), -1)  # small 10x10

    # 2. Add true strict vertical blue indicator at y=550 (height=60, width=12)
    # BGR for HSV strict [110, 200, 200] -> Blue: BGR ~ (200, 100, 30)
    cv2.rectangle(img, (2545, 520), (2557, 580), (220, 140, 20), -1)

    ctx = ClassificationContext(img)
    norm_y, sig = detect_blue_indicator(ctx, 2520, 2620)
    assert norm_y is not None
    assert sig.reliability == 1.0  # strict
    assert "strict" in sig.reason
    assert abs(norm_y * 1284.0 - 550.0) < 15.0

    # 3. Test relaxed/faded blue indicator
    img_faded = np.zeros((h, w, 3), dtype=np.uint8)
    # Faded blue: H=110, S=80 (below strict 120), V=160 (above relaxed 75)
    faded_bgr = tuple(int(c) for c in cv2.cvtColor(np.uint8([[[110, 80, 160]]]), cv2.COLOR_HSV2BGR)[0, 0])
    cv2.rectangle(img_faded, (2545, 700), (2557, 760), faded_bgr, -1)
    ctx_faded = ClassificationContext(img_faded)
    norm_faded_y, sig_faded = detect_blue_indicator(ctx_faded, 2520, 2620)
    assert norm_faded_y is not None
    assert sig_faded.reliability <= 0.8  # relaxed has lower reliability
    assert "relaxed" in sig_faded.reason


def test_gun_lab_signals():
    w, h = 2778, 1284
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # Dark workshop center
    img[180:1100, 50:1650] = 50

    # Top-right bright text
    img[30:110, 2300:2550] = 230

    # Orange badge in HSV: [15, 200, 200] -> BGR ~ (20, 140, 240)
    img[90:180, 2120:2300] = (20, 140, 240)

    ctx = ClassificationContext(img)
    signals = detect_gun_lab_signals(ctx)

    assert signals["gun_lab_header"].score > 0.6
    assert signals["gun_lab_orange_badge"].score > 0.6
    assert signals["gun_lab_dark_center"].score > 0.6

    # Test only dark center: other signals zero
    img_dark_only = np.zeros((h, w, 3), dtype=np.uint8)
    img_dark_only[180:1100, 50:1650] = 50
    ctx_dark = ClassificationContext(img_dark_only)
    sigs_dark = detect_gun_lab_signals(ctx_dark)
    assert sigs_dark["gun_lab_header"].score == 0.0
    assert sigs_dark["gun_lab_orange_badge"].score == 0.0
    assert sigs_dark["gun_lab_dark_center"].score > 0.6


def test_wardrobe_signals():
    w, h = 2778, 1284
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # Subtab rail: smooth vertical line
    img[:, 2390:2495] = 40

    # 3-row card grid rhythm
    for top_y in (210, 477, 744):
        img[top_y:top_y + 4, 1718:2411] = 200
        img[top_y + 246:top_y + 250, 1718:2411] = 200

    ctx = ClassificationContext(img)
    signals = detect_wardrobe_signals(ctx)
    assert signals["rail_smoothness"].score > 0.4
    assert signals["inventory_grid_rhythm"].score > 0.4


def test_backpack_selector_signals():
    w, h = 2778, 1284
    img = np.zeros((h, w, 3), dtype=np.uint8)

    # Place 3 selector buttons with yellow/gray in (1110, 60, 1260, 560)
    for idx, cy in enumerate([150, 240, 330]):
        cv2.rectangle(img, (1140, cy - 25), (1230, cy + 25), (30, 200, 230), -1)  # yellow badge
        cv2.putText(img, f"Lv{idx+1}", (1150, cy + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    ctx = ClassificationContext(img)
    sig = detect_backpack_selector_signals(ctx)
    assert sig.score >= 0.8
    assert "backpack selector confirmed" in sig.reason.lower()


def test_detail_popup_signals():
    w, h = 2778, 1284
    img = np.zeros((h, w, 3), dtype=np.uint8)

    # Frame edges at x=1325 and x=1685 for y=930..1240
    cv2.line(img, (1325, 930), (1325, 1240), (220, 220, 220), 4)
    cv2.line(img, (1685, 930), (1685, 1240), (220, 220, 220), 4)

    ctx = ClassificationContext(img)
    sig = detect_detail_popup_signals(ctx)
    assert sig.score >= 0.7
    assert "item detail frame" in sig.reason.lower()
