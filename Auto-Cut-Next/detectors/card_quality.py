"""Card quality evaluator: lock detection, content/empty detection, and partial validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

LOCK_MASK_PATH = Path(__file__).resolve().parent.parent / "assets" / "detector" / "lock_mask.png"
_LOCK_TEMPLATE_CACHE: Optional[np.ndarray] = None


@dataclass
class CardQualityResult:
    """Evaluation result for an extracted card tile."""
    locked: bool = False
    empty: bool = False
    partial: bool = False
    lock_score: float = 0.0
    content_score: float = 1.0
    partial_score: float = 0.0
    confidence: float = 1.0
    review_required: bool = False
    reasons: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def get_lock_template() -> Optional[np.ndarray]:
    """Loads and caches binary lock mask template (24x28)."""
    global _LOCK_TEMPLATE_CACHE
    if _LOCK_TEMPLATE_CACHE is None and LOCK_MASK_PATH.is_file():
        mask_img = cv2.imread(str(LOCK_MASK_PATH), cv2.IMREAD_GRAYSCALE)
        if mask_img is not None:
            _LOCK_TEMPLATE_CACHE = (mask_img > 127)
    return _LOCK_TEMPLATE_CACHE


def compute_lock_score(tile_bgr: np.ndarray) -> tuple[float, dict[str, Any]]:
    """Calculates lock icon presence via corner connected-components and IoU with template."""
    template = get_lock_template()
    if template is None or tile_bgr is None or tile_bgr.size == 0:
        return 0.0, {}

    # Normalize tile to 160x160
    resized = cv2.resize(tile_bgr, (160, 160), interpolation=cv2.INTER_AREA)
    # Top-right corner region: y: 0..52, x: 100..159
    corner = resized[:52, 100:159]
    bright_mask = (np.min(corner, axis=2) > 175).astype(np.uint8)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bright_mask, connectivity=8)
    best_score = 0.0
    best_stats = {}

    for idx in range(1, num_labels):
        x, y, w, h, area = stats[idx]
        if w < 7 or h < 9 or not (0.5 < (w / float(h)) < 1.15):
            continue

        comp_mask = (labels[y:y + h, x:x + w] == idx).astype(np.uint8) * 255
        scaled_mask = cv2.resize(comp_mask, (template.shape[1], template.shape[0]), interpolation=cv2.INTER_NEAREST) > 127
        inter = np.count_nonzero(scaled_mask & template)
        union = np.count_nonzero(scaled_mask | template)
        iou = float(inter) / float(max(1, union))

        if iou > best_score:
            best_score = iou
            best_stats = {"w": w, "h": h, "area": area, "iou": iou}

    return best_score, best_stats


def compute_content_score(tile_bgr: np.ndarray) -> tuple[float, float]:
    """Calculates high-frequency detail score in central 64x64 region."""
    if tile_bgr is None or tile_bgr.size == 0:
        return 0.0, 0.0

    resized = cv2.resize(tile_bgr, (64, 64), interpolation=cv2.INTER_AREA)
    pixels = resized.astype(np.float32)
    blur = cv2.GaussianBlur(pixels, (5, 5), 1.0)
    detail = np.abs(pixels - blur)

    # Focus on central area (10:54, 10:54) to ignore border edges
    central_detail = detail[10:54, 10:54]
    max_channel_detail = np.max(central_detail, axis=2)
    detail_ratio = float(np.mean(max_channel_detail > 14.0))

    normalized_score = min(1.0, detail_ratio / 0.05)
    return normalized_score, detail_ratio


class CardQualityEvaluator:
    """Evaluates individual candidate tiles for lock, empty, and partial degradation."""

    def __init__(
        self,
        lock_threshold: float = 0.50,
        empty_detail_threshold: float = 0.15,
        lock_uncertainty_margin: float = 0.10,
        empty_uncertainty_margin: float = 0.10,
    ):
        self.lock_threshold = lock_threshold
        self.empty_detail_threshold = empty_detail_threshold
        self.lock_uncertainty_margin = lock_uncertainty_margin
        self.empty_uncertainty_margin = empty_uncertainty_margin

    def evaluate(
        self,
        tile_bgr: np.ndarray,
        partial_score: float = 0.0,
    ) -> CardQualityResult:
        """Runs quality pipeline on candidate tile."""
        reasons = []
        is_partial = partial_score >= 0.10
        if is_partial:
            reasons.append(f"Partial card detected (partial_score={partial_score:.2f})")

        lock_sc, lock_diag = compute_lock_score(tile_bgr)
        is_locked = lock_sc >= self.lock_threshold
        lock_uncertain = (not is_locked) and (lock_sc >= max(0.0, self.lock_threshold - self.lock_uncertainty_margin))

        if is_locked:
            reasons.append(f"Locked item card (score={lock_sc:.2f} >= {self.lock_threshold:.2f})")
        elif lock_uncertain:
            reasons.append(f"Uncertain lock score near threshold (score={lock_sc:.2f})")

        content_sc, raw_detail = compute_content_score(tile_bgr)
        # Empty if raw_detail <= 0.018 or normalized content_score < empty_detail_threshold
        is_empty = (raw_detail <= 0.018) or (content_sc < self.empty_detail_threshold)
        empty_uncertain = (not is_empty) and (content_sc < self.empty_detail_threshold + self.empty_uncertainty_margin)

        if is_empty:
            reasons.append(f"Empty/blank item slot (detail={raw_detail:.4f}, score={content_sc:.2f})")
        elif empty_uncertain:
            reasons.append(f"Low content detail near empty threshold (detail={raw_detail:.4f})")

        review_required = lock_uncertain or empty_uncertain or (0.05 <= partial_score < 0.10)

        confidence = 1.0
        if review_required:
            confidence = 0.65
        elif is_locked or is_empty or is_partial:
            confidence = 0.90

        return CardQualityResult(
            locked=is_locked,
            empty=is_empty,
            partial=is_partial,
            lock_score=round(lock_sc, 4),
            content_score=round(content_sc, 4),
            partial_score=round(partial_score, 4),
            confidence=round(confidence, 4),
            review_required=review_required,
            reasons=reasons,
            diagnostics={
                "raw_detail_ratio": raw_detail,
                "lock_stats": lock_diag,
            },
        )

