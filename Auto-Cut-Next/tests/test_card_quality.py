"""Unit tests for card quality evaluator: lock detection, content detection, and partial rejection."""

import cv2
import numpy as np
import pytest

from detectors.card_quality import (
    CardQualityEvaluator,
    compute_lock_score,
    compute_content_score,
    get_lock_template,
)


def test_get_lock_template_loads():
    tmpl = get_lock_template()
    assert tmpl is not None
    assert isinstance(tmpl, np.ndarray)
    assert tmpl.ndim == 2
    assert tmpl.shape[0] > 10 and tmpl.shape[1] > 10


def test_compute_lock_score_clean_tile():
    clean_tile = np.zeros((160, 160, 3), dtype=np.uint8)
    clean_tile[:, :] = (40, 40, 40)
    score, stats = compute_lock_score(clean_tile)
    assert score < 0.20


def test_compute_lock_score_with_lock_template():
    tmpl = get_lock_template()
    assert tmpl is not None

    tile = np.zeros((160, 160, 3), dtype=np.uint8)
    tile[:, :] = (30, 30, 30)

    # Stamp bright lock icon in top-right corner region (x: 120..144, y: 10..38)
    th, tw = tmpl.shape
    corner_y, corner_x = 12, 125
    for r in range(th):
        for c in range(tw):
            if tmpl[r, c]:
                tile[corner_y + r, corner_x + c] = (255, 255, 255)

    score, stats = compute_lock_score(tile)
    assert score >= 0.50
    assert "iou" in stats


def test_compute_content_score_empty_vs_textured():
    # Empty blank tile
    empty_tile = np.zeros((120, 120, 3), dtype=np.uint8)
    empty_tile[:, :] = (35, 30, 25)
    score_empty, detail_empty = compute_content_score(empty_tile)
    assert detail_empty < 0.015
    assert score_empty < 0.15

    # Textured item tile with high frequency variations
    rng = np.random.default_rng(123)
    textured_tile = rng.integers(30, 220, size=(120, 120, 3), dtype=np.uint8)
    score_tex, detail_tex = compute_content_score(textured_tile)
    assert detail_tex > 0.05
    assert score_tex > 0.60


def test_card_quality_evaluator_empty_card():
    evaluator = CardQualityEvaluator()
    blank_tile = np.zeros((160, 160, 3), dtype=np.uint8)
    blank_tile[:, :] = (40, 40, 40)

    res = evaluator.evaluate(blank_tile, partial_score=0.0)
    assert res.empty is True
    assert res.locked is False
    assert res.partial is False
    assert any("Empty" in reason for reason in res.reasons)


def test_card_quality_evaluator_partial_card():
    evaluator = CardQualityEvaluator()
    rng = np.random.default_rng(42)
    textured = rng.integers(50, 200, size=(160, 160, 3), dtype=np.uint8)

    res = evaluator.evaluate(textured, partial_score=0.25)
    assert res.partial is True
    assert any("Partial" in reason for reason in res.reasons)


def test_card_quality_evaluator_clean_accepted_card():
    evaluator = CardQualityEvaluator()
    rng = np.random.default_rng(99)
    textured = rng.integers(50, 200, size=(160, 160, 3), dtype=np.uint8)

    res = evaluator.evaluate(textured, partial_score=0.0)
    assert res.locked is False
    assert res.empty is False
    assert res.partial is False
    assert res.review_required is False
    assert res.confidence == 1.0


def test_lock_false_positives_white_shapes():
    # White circle in top right (e.g. notification badge or number icon)
    tile_circle = np.zeros((160, 160, 3), dtype=np.uint8)
    tile_circle[:, :] = (35, 30, 25)
    cv2.circle(tile_circle, (135, 25), 10, (255, 255, 255), -1)

    score_circle, _ = compute_lock_score(tile_circle)
    assert score_circle < 0.35

    # White solid horizontal badge in top right
    tile_badge = np.zeros((160, 160, 3), dtype=np.uint8)
    tile_badge[:, :] = (35, 30, 25)
    cv2.rectangle(tile_badge, (120, 15), (150, 30), (255, 255, 255), -1)

    score_badge, _ = compute_lock_score(tile_badge)
    assert score_badge < 0.35


def test_content_score_border_only_empty():
    evaluator = CardQualityEvaluator()
    # Card with high contrast borders but totally flat/empty interior
    tile_border_only = np.zeros((160, 160, 3), dtype=np.uint8)
    tile_border_only[:, :] = (40, 40, 40)
    # Heavy border
    cv2.rectangle(tile_border_only, (0, 0), (159, 159), (255, 255, 255), 6)
    cv2.rectangle(tile_border_only, (10, 10), (149, 149), (200, 200, 200), 2)

    res = evaluator.evaluate(tile_border_only)
    assert res.empty is True


def test_empty_content_threshold_sensitivity():
    """Validates that empty decision strictly responds to empty_content_threshold setting without hidden hardcoded raw thresholds."""
    # 1. Clear empty tile (detail ~ 0.0)
    clear_empty = np.zeros((160, 160, 3), dtype=np.uint8)
    clear_empty[:, :] = (35, 30, 25)

    # 2. Border-only tile (high contrast border, flat center, detail ~ 0.0)
    border_only = np.zeros((160, 160, 3), dtype=np.uint8)
    border_only[:, :] = (35, 30, 25)
    cv2.rectangle(border_only, (0, 0), (159, 159), (255, 255, 255), 4)

    # 3. Intermediate subtle texture tile (detail ~ 0.02, normalized score ~ 0.40)
    subtle_tile = np.zeros((160, 160, 3), dtype=np.uint8)
    subtle_tile[:, :] = (35, 30, 25)
    # Add subtle localized mark in center (small circle)
    cv2.circle(subtle_tile, (80, 80), 9, (60, 55, 50), -1)

    sc_empty, _ = compute_content_score(clear_empty)
    sc_border, _ = compute_content_score(border_only)
    sc_subtle, _ = compute_content_score(subtle_tile)

    assert sc_empty < 0.10
    assert sc_border < 0.10
    assert 0.15 < sc_subtle < 0.60

    # Test threshold toggle on intermediate subtle tile:
    # If threshold is high (0.70), subtle tile is marked empty
    eval_high = CardQualityEvaluator(empty_content_threshold=0.70)
    assert eval_high.evaluate(subtle_tile).empty is True

    # If threshold is low (0.10), subtle tile is NOT marked empty
    eval_low = CardQualityEvaluator(empty_content_threshold=0.10)
    assert eval_low.evaluate(subtle_tile).empty is False

    # Clear empty and border-only remain empty under standard threshold (0.35)
    eval_std = CardQualityEvaluator(empty_content_threshold=0.35)
    assert eval_std.evaluate(clear_empty).empty is True
    assert eval_std.evaluate(border_only).empty is True

