"""Atomic measurable feature signals extracted from ClassificationContext."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

import cv2
import numpy as np

from .classification_context import ClassificationContext
from core.models import Rect

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "classifier"


@dataclass
class SignalResult:
    """Individual measurable visual signal with score, reliability, and human-readable reason."""
    name: str
    score: float  # 0.0 to 1.0
    reliability: float = 1.0
    reason: str = ""
    raw_value: Any = None


def detect_blue_indicator(
    context: ClassificationContext,
    x1_ref: float,
    x2_ref: float,
) -> Tuple[Optional[float], SignalResult]:
    """Detects vertical selected blue tab indicator in specified reference horizontal band."""
    rect = context.ref_rect(x1_ref, 0, x2_ref, ClassificationContext.REF_HEIGHT)
    sx1 = max(0, min(context.scan_w - 1, rect.x))
    sx2 = max(sx1 + 1, min(context.scan_w, rect.right))

    min_height = max(14, int(round(35 * context.scale_y)))
    min_area = max(20, int(round(50 * context.scale_x * context.scale_y)))

    for mask, is_strict in [(context.strict_blue_mask, True), (context.relaxed_blue_mask, False)]:
        strip = (mask[:, sx1:sx2] > 0).astype(np.uint8)
        if strip.size == 0 or int(np.sum(strip)) == 0:
            continue

        count, _, stats, centers = cv2.connectedComponentsWithStats(strip, connectivity=8)
        candidates = []

        for idx in range(1, count):
            _, _, comp_w, comp_h, area = stats[idx]
            if comp_h < min_height or area < min_area:
                continue

            slender_bonus = comp_h / max(1.0, float(comp_w))
            score = float(area) * min(8.0, slender_bonus) * float(comp_h)
            candidates.append((score, float(centers[idx][1])))

        if candidates:
            best_score, best_y = max(candidates, key=lambda item: item[0])
            norm_y = best_y / float(context.scan_h)
            rel = 1.0 if is_strict else 0.75
            kind = "strict" if is_strict else "relaxed"
            return norm_y, SignalResult(
                name="blue_indicator",
                score=min(1.0, best_score / 40000.0),
                reliability=rel,
                reason=f"Found {kind} blue indicator at y={norm_y:.3f} (center={best_y:.1f}px)",
                raw_value={"center_y_norm": norm_y, "strict": is_strict, "raw_score": best_score},
            )

    return None, SignalResult(
        name="blue_indicator",
        score=0.0,
        reliability=0.0,
        reason=f"No blue indicator found in x-band [{x1_ref:.0f}..{x2_ref:.0f}]",
        raw_value=None,
    )


def detect_gun_lab_signals(context: ClassificationContext) -> dict[str, SignalResult]:
    """Measures the three distinct Gun Lab visual anchors."""
    signals = {}

    # 1. Top-right text
    top_right_rect = context.ref_rect(2300, 30, 2550, 110)
    top_right_gray = context.roi_gray(top_right_rect)
    bright_pixels = int(np.sum(top_right_gray > 200)) if top_right_gray.size > 0 else 0
    needed_bright = int(600 * context.scale_x * context.scale_y)
    score_bright = min(1.0, float(bright_pixels) / float(max(1, needed_bright)))
    signals["gun_lab_header"] = SignalResult(
        name="gun_lab_header",
        score=score_bright,
        reason=f"Top-right bright header text: {bright_pixels}/{needed_bright} px",
        raw_value=bright_pixels,
    )

    # 2. Orange badge
    daco_rect = context.ref_rect(2120, 90, 2300, 180)
    daco_hsv = context.roi_hsv(daco_rect)
    orange_pixels = 0
    if daco_hsv.size > 0:
        orange_mask = cv2.inRange(daco_hsv, np.array([5, 120, 100]), np.array([30, 255, 255]))
        orange_pixels = int(np.sum(orange_mask > 0))
    needed_orange = int(120 * context.scale_x * context.scale_y)
    score_orange = min(1.0, float(orange_pixels) / float(max(1, needed_orange)))
    signals["gun_lab_orange_badge"] = SignalResult(
        name="gun_lab_orange_badge",
        score=score_orange,
        reason=f"Orange ownership badge: {orange_pixels}/{needed_orange} px",
        raw_value=orange_pixels,
    )

    # 3. Dark workshop center
    center_rect = context.ref_rect(50, 180, 1650, 1100)
    center_gray = context.roi_gray(center_rect)
    mean_val = float(np.mean(center_gray)) if center_gray.size > 0 else 255.0
    score_dark = min(1.0, max(0.0, (92.0 - mean_val) / 25.0 + 0.5)) if mean_val < 92.0 else 0.0
    signals["gun_lab_dark_center"] = SignalResult(
        name="gun_lab_dark_center",
        score=score_dark,
        reason=f"Dark workshop background mean brightness: {mean_val:.1f} (target < 92)",
        raw_value=mean_val,
    )

    return signals


def detect_wardrobe_signals(context: ClassificationContext) -> dict[str, SignalResult]:
    """Extracts wardrobe subtab rail smoothness and 3-row grid rhythm."""
    signals = {}

    # 1. Rail smoothness
    rail_rect = context.ref_rect(2390, 0, 2495, 1284)
    rail_gray = context.roi_gray(rail_rect).astype(np.float32)
    if rail_gray.shape[0] >= 2 and rail_gray.shape[1] >= 2:
        row_diff = np.mean(np.abs(np.diff(rail_gray, axis=0)), axis=1)
        p95 = float(np.percentile(row_diff, 95))
        rail_limit = 14.0 + max(0.0, min(6.0, (1.0 / max(context.scale_y, 0.25) - 1.0) * 4.0))
        # Lower percentile = smoother rail = higher score
        score_smooth = min(1.0, max(0.0, (rail_limit * 1.5 - p95) / (rail_limit * 0.5))) if p95 <= rail_limit else 0.0
    else:
        p95 = 999.0
        score_smooth = 0.0

    signals["rail_smoothness"] = SignalResult(
        name="rail_smoothness",
        score=score_smooth,
        reason=f"Subtab rail p95 row-diff: {p95:.1f} (limit {rail_limit:.1f})",
        raw_value=p95,
    )

    # 2. Fast inventory grid score
    grid_rect = context.ref_rect(1718, 0, 2411, 1284)
    grid_gray = context.roi_gray(grid_rect)
    if grid_gray.size > 0 and grid_gray.shape[0] > 10 and grid_gray.shape[1] > 10:
        small = cv2.resize(grid_gray, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA).astype(np.float32)
        row_change = np.mean(np.abs(np.diff(small, axis=0)), axis=1)
        slot_h = max(10, int(round(250 * context.scale_y * 0.25)))
        step_y = max(slot_h + 1, int(round(267 * context.scale_y * 0.25)))
        min_y = int(round(190 * context.scale_y * 0.25))
        bottom_limit = small.shape[0] - 2

        best_score = 0.0
        for phase in range(min(step_y, small.shape[0])):
            rows = [y for y in range(phase, small.shape[0], step_y) if y >= min_y and y + slot_h <= bottom_limit]
            if len(rows) < 2:
                continue
            boundary_scores = []
            for top_y in rows:
                top_b = row_change[max(0, top_y - 1):min(len(row_change), top_y + 2)]
                bot_b = row_change[max(0, top_y + slot_h - 1):min(len(row_change), top_y + slot_h + 2)]
                if top_b.size and bot_b.size:
                    boundary_scores.append(float(np.max(top_b) + np.max(bot_b)))
            if len(boundary_scores) >= 2:
                score = float(np.median(boundary_scores) + 0.25 * np.mean(boundary_scores))
                best_score = max(best_score, score)
        grid_score = min(1.0, best_score / 60.0)
    else:
        grid_score = 0.0
        best_score = 0.0

    signals["inventory_grid_rhythm"] = SignalResult(
        name="inventory_grid_rhythm",
        score=grid_score,
        reason=f"3-row grid boundary rhythm score: {best_score:.1f} (target >= 45)",
        raw_value=best_score,
    )

    return signals


def detect_backpack_selector_signals(context: ClassificationContext) -> SignalResult:
    """Detects 3-level backpack selector buttons at the left of inventory grid."""
    rect = context.ref_rect(1110, 60, 1260, 560)
    selector_bgr = context.roi_bgr(rect)
    if selector_bgr.size == 0 or selector_bgr.shape[0] < 10 or selector_bgr.shape[1] < 10:
        return SignalResult("backpack_selector", 0.0, 0.0, "Area too small")

    selector_gray = cv2.cvtColor(selector_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    std_val = float(np.std(selector_bgr))
    row_change = np.mean(np.abs(np.diff(selector_gray, axis=0)), axis=1) if selector_gray.shape[0] >= 2 else np.array([0.0])
    max_rc = float(np.max(row_change)) if len(row_change) else 0.0
    p95_rc = float(np.percentile(row_change, 95)) if len(row_change) else 0.0

    # Reference rules: std >= 32.0, max(row_change) >= 42.0, p95(row_change) >= 5.5
    matches_reference = (std_val >= 32.0 and max_rc >= 42.0 and p95_rc >= 5.5)

    # Also test button layout spacing if available
    hsv = context.roi_hsv(rect)
    yellow_mask = cv2.inRange(hsv, np.array([15, 90, 110], dtype=np.uint8), np.array([35, 255, 255], dtype=np.uint8))
    gray_mask = cv2.inRange(hsv, np.array([0, 0, 75], dtype=np.uint8), np.array([180, 50, 180], dtype=np.uint8))
    combo = ((yellow_mask | gray_mask) > 0).astype(np.uint8)

    count, _, stats, centers = cv2.connectedComponentsWithStats(combo, 8)
    min_dim = max(10, int(round(25 * context.scale_y)))
    max_dim = max(min_dim + 1, int(round(125 * context.scale_y)))

    valid_centers = []
    for idx in range(1, count):
        _, _, comp_w, comp_h, area = stats[idx]
        if comp_h < min_dim or comp_w < min_dim or comp_h > max_dim or comp_w > max_dim:
            continue
        valid_centers.append(float(centers[idx][1]))

    pattern_matched = False
    if len(valid_centers) >= 3:
        valid_centers.sort()
        diffs = [valid_centers[i + 1] - valid_centers[i] for i in range(len(valid_centers) - 1)]
        expected_step = 90.0 * context.scale_y
        for i in range(len(diffs) - 1):
            d1, d2 = diffs[i], diffs[i + 1]
            if 0.5 * expected_step <= d1 <= 1.8 * expected_step and 0.5 * expected_step <= d2 <= 1.8 * expected_step:
                pattern_matched = True
                break

    if matches_reference or pattern_matched:
        return SignalResult(
            "backpack_selector",
            1.0,
            1.0,
            f"3-level backpack selector confirmed (std={std_val:.1f}, max_diff={max_rc:.1f}, p95={p95_rc:.1f})",
            raw_value={"std": std_val, "max_rc": max_rc, "p95_rc": p95_rc, "pattern": pattern_matched},
        )

    score = 0.0
    if std_val >= 25.0 and max_rc >= 30.0:
        score = 0.4
    return SignalResult("backpack_selector", score, 0.5, f"Weak backpack selector features (std={std_val:.1f})", raw_value=std_val)


def detect_detail_popup_signals(context: ClassificationContext) -> SignalResult:
    """Detects 2 vertical frame boundaries of the item detail popup frame below y=930."""
    gray = context.gray.astype(np.float32)
    y1 = max(0, int(round(930 * context.scale_y)))
    y2 = min(context.scan_h, int(round(1240 * context.scale_y)))
    radius = max(2, int(round(5 * context.scale_x)))

    if y2 <= y1 or context.scan_w < 10:
        return SignalResult("detail_popup_frame", 0.0, 0.0, "Scan area invalid")

    frame_edge_scores = []
    for base_x in (1325, 1685):
        x = int(round(base_x * context.scale_x))
        band_x1 = max(0, x - radius)
        band_x2 = min(context.scan_w, x + radius + 1)
        edge_band = gray[y1:y2, band_x1:band_x2]
        if edge_band.shape[0] < 2 or edge_band.shape[1] < 2:
            return SignalResult("detail_popup_frame", 0.0, 0.0, "Edge band missing")
        diff_val = float(np.mean(np.abs(np.diff(edge_band, axis=1))))
        frame_edge_scores.append(diff_val)

    resolution_factor = max(1.0, max(context.scale_y, 0.25) ** -0.80)
    edge_threshold = 2.82 * resolution_factor
    min_score = min(frame_edge_scores) if frame_edge_scores else 0.0
    score = min(1.0, min_score / (edge_threshold * 1.5)) if min_score >= edge_threshold else 0.0

    return SignalResult(
        "detail_popup_frame",
        score,
        1.0 if score > 0.6 else 0.5,
        f"Item detail frame edge score: {min_score:.2f} (target >= {edge_threshold:.2f})",
        raw_value=min_score,
    )



def detect_accessory_signals(context: ClassificationContext) -> dict[str, SignalResult]:
    """Measures structural properties of accessory / tab 4 screens (emote, grenade, parachute)."""
    signals = {}

    # 1. Grenade header: 3 separators in header y: 75..155 at x: 1882, 2063, 2246
    header_rect = context.ref_rect(0, 75, 2778, 155)
    header_gray = context.roi_gray(header_rect).astype(np.float32)
    if header_gray.shape[0] >= 2 and header_gray.shape[1] >= 10:
        col_diff = np.mean(np.abs(np.diff(header_gray, axis=1)), axis=0)
        radius = max(2, int(round(5 * context.scale_x)))
        separator_scores = []
        for base_x in (1882, 2063, 2246):
            x = int(round(base_x * context.scale_x))
            lo = max(0, x - radius)
            hi = min(len(col_diff), x + radius + 1)
            if hi > lo:
                separator_scores.append(float(np.max(col_diff[lo:hi])))
        min_sep = min(separator_scores) if len(separator_scores) == 3 else 0.0
        sep_score = min(1.0, min_sep / 25.0) if min_sep >= 17.5 else 0.0
    else:
        min_sep = 0.0
        sep_score = 0.0

    signals["grenade_subtypes"] = SignalResult(
        "grenade_subtypes",
        sep_score,
        1.0 if sep_score > 0.7 else 0.5,
        f"Grenade 4-slot header separator strength: {min_sep:.1f} (target >= 17.5)",
        raw_value=min_sep,
    )

    # 2. Card grid & Emote silhouette
    strips = []
    for x1, x2 in [(1730, 1927), (1967, 2164), (2203, 2399)]:
        rx = context.ref_rect(x1, 0, x2, 1284)
        s = context.roi_bgr(rx)
        if s.size > 0:
            strips.append(s)

    card_count = 0
    emote_count = 0
    first_row_y = 0

    if strips:
        cat_strip = np.concatenate(strips, axis=1)
        gray_cat = cv2.cvtColor(cat_strip, cv2.COLOR_BGR2GRAY)
        row_diff = np.mean(np.abs(np.diff(gray_cat.astype(np.float32), axis=0)), axis=1)

        slot_h = max(30, int(round(250 * context.scale_y)))
        step_y = max(slot_h + 4, int(round(267 * context.scale_y)))
        min_full_y = int(round(190 * context.scale_y))
        bottom_limit = context.scan_h - max(8, int(round(10 * context.scale_y)))

        best_rows = []
        for phase in range(min(step_y, context.scan_h)):
            rows = [y for y in range(phase, context.scan_h, step_y) if y >= min_full_y and y + slot_h <= bottom_limit]
            if len(rows) >= 2:
                best_rows = rows
                break

        if best_rows:
            first_row_y = best_rows[0]
            cols_base = [(1718, 1939), (1955, 2176), (2191, 2411)]
            for nominal_y in best_rows[:2]:
                for cx1, cx2 in cols_base:
                    scale_y_safe = max(context.scale_y, 0.001)
                    crect = context.ref_rect(cx1, nominal_y / scale_y_safe, cx2, (nominal_y + slot_h) / scale_y_safe)
                    c_bgr = context.roi_bgr(crect)
                    if c_bgr.size == 0 or float(np.std(c_bgr)) < 16.0:
                        continue
                    card_count += 1
                    c_hsv = cv2.cvtColor(c_bgr, cv2.COLOR_BGR2HSV)
                    sat = c_hsv[:, :, 1]
                    val = c_hsv[:, :, 2]
                    white_ratio = float(np.mean((sat <= 75) & (val >= 180)))
                    hue = c_hsv[:, :, 0]
                    red_ratio = float(np.mean(((hue <= 15) | (hue >= 160)) & (sat >= 55) & (val >= 55)))
                    purple_ratio = float(np.mean((hue >= 145) & (hue <= 175) & (sat >= 45) & (val >= 55)))
                    if white_ratio >= 0.045 and max(red_ratio, purple_ratio) >= 0.30:
                        emote_count += 1

        # Check band strengths for first row locations
        def band_strength(y1_ref: float, y2_ref: float) -> float:
            s_y = max(0, int(round(y1_ref * context.scale_y)))
            e_y = min(len(row_diff), int(round(y2_ref * context.scale_y)))
            return float(np.max(row_diff[s_y:e_y])) if e_y > s_y else 0.0

        first_row_strength = band_strength(205, 225)
        subtype_row_strength = band_strength(291, 307)
        emote_row_strength = band_strength(307, 321)

    signals["emote_silhouette"] = SignalResult(
        "emote_silhouette",
        min(1.0, float(emote_count) / 2.0),
        1.0 if emote_count >= 2 else 0.5,
        f"Emote silhouettes: {emote_count} (total cards: {card_count})",
        raw_value={"emote_cards": emote_count, "total_cards": card_count},
    )

    norm_first_row = first_row_y / float(context.scan_h) if context.scan_h > 0 else 0.0
    is_early_first_row = 0.14 <= norm_first_row <= 0.22
    para_score = 1.0 if (is_early_first_row and sep_score < 0.3 and emote_count < 2 and card_count >= 2) else 0.0
    signals["parachute_geometry"] = SignalResult(
        "parachute_geometry",
        para_score,
        0.9 if para_score > 0 else 0.3,
        f"Parachute early first row start: {norm_first_row:.3f} (target 0.16..0.20)",
        raw_value=norm_first_row,
    )

    signals["card_grid_presence"] = SignalResult(
        "card_grid_presence",
        min(1.0, float(card_count) / 3.0),
        1.0 if card_count >= 3 else 0.5,
        f"Detected card count: {card_count}",
        raw_value=card_count,
    )

    return signals


_SUPERCAR_CEILING_CACHE: Optional[np.ndarray] = None


def detect_outfit_lobby_signals(context: ClassificationContext) -> dict[str, SignalResult]:
    """Measures outfit lobby anchors: supercar ceiling template, character density, right-side UI."""
    global _SUPERCAR_CEILING_CACHE
    signals = {}

    # 1. Supercar ceiling template match
    supercar_path = ASSETS_DIR / "supercar_ceiling.png"
    supercar_score = 0.0
    if supercar_path.is_file():
        if _SUPERCAR_CEILING_CACHE is None:
            raw_img = cv2.imread(str(supercar_path), cv2.IMREAD_GRAYSCALE)
            if raw_img is not None:
                _SUPERCAR_CEILING_CACHE = raw_img
        if _SUPERCAR_CEILING_CACHE is not None:
            ref_template = _SUPERCAR_CEILING_CACHE
            roi_rect = context.ref_rect(0, 0, 1500, 280)
            roi_gray = context.roi_gray(roi_rect)
            if roi_gray.shape[0] >= 20 and roi_gray.shape[1] >= 50:
                thumb = cv2.resize(roi_gray, (ref_template.shape[1], ref_template.shape[0]), interpolation=cv2.INTER_AREA)
                match_val = float(cv2.matchTemplate(thumb, ref_template, cv2.TM_CCOEFF_NORMED)[0, 0])
                supercar_score = max(0.0, match_val)

    signals["supercar_ceiling"] = SignalResult(
        "supercar_ceiling",
        min(1.0, supercar_score),
        1.0 if supercar_score >= 0.80 else 0.6,
        f"Supercar ceiling match: {supercar_score:.3f} (target >= 0.80)",
        raw_value=supercar_score,
    )

    # 2. Right-side wardrobe interface structure
    right_rect = context.ref_rect(1700, 0, 2778, 1284)
    right_bgr = context.roi_bgr(right_rect)
    right_std = float(np.std(right_bgr)) if right_bgr.size > 0 else 0.0
    right_score = min(1.0, max(0.0, (right_std - 15.0) / 25.0)) if right_std >= 15.0 else 0.0
    signals["right_side_ui_variance"] = SignalResult(
        "right_side_ui_variance",
        right_score,
        0.8,
        f"Right side UI variance std: {right_std:.1f} (target >= 22.0)",
        raw_value=right_std,
    )

    # 3. Character presence in left/center scene
    char_rect = context.ref_rect(250, 80, 1500, 1180)
    char_bgr = context.roi_bgr(char_rect)
    char_std = float(np.std(char_bgr)) if char_bgr.size > 0 else 0.0
    char_score = min(1.0, max(0.0, (char_std - 15.0) / 25.0)) if char_std >= 15.0 else 0.0
    signals["character_presence"] = SignalResult(
        "character_presence",
        char_score,
        0.7,
        f"Character area variance std: {char_std:.1f}",
        raw_value=char_std,
    )

    return signals


