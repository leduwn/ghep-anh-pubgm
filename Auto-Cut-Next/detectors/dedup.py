"""Perceptual hashing and two-stage visual deduplication engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union
import cv2
import numpy as np

from core.models import DetectedAsset, Rect
from core.constants import DEFAULT_DUPLICATE_THRESHOLD


@dataclass(frozen=True)
class DedupProfile:
    """Category-specific deduplication settings and crop boundaries."""
    name: str
    crop_box_ratio: tuple[float, float, float, float] = (0.15, 0.15, 0.85, 0.85)
    phash_threshold: int = 10
    diff_threshold: float = 12.0


DEFAULT_CATEGORY_DEDUP_PROFILES: dict[str, DedupProfile] = {
    "GUN": DedupProfile(
        name="GUN",
        crop_box_ratio=(0.10, 0.10, 0.90, 0.90),
        phash_threshold=4,
        diff_threshold=6.0,
    ),
    "VEHICLE": DedupProfile(
        name="VEHICLE",
        crop_box_ratio=(0.15, 0.10, 0.85, 0.90),
        phash_threshold=8,
        diff_threshold=10.0,
    ),
    "OUTFIT": DedupProfile(
        name="OUTFIT",
        crop_box_ratio=(0.15, 0.20, 0.70, 0.80),
        phash_threshold=8,
        diff_threshold=10.0,
    ),
}


def compute_phash(tile_bgr: np.ndarray) -> int:
    """Computes a 64-bit perceptual hash (pHash) on the central 70% of the tile using 2D DCT."""
    if tile_bgr is None or tile_bgr.size == 0:
        return 0

    h, w = tile_bgr.shape[:2]
    # Central 70% to ignore borders
    y1, y2 = int(round(h * 0.15)), max(int(round(h * 0.15)) + 1, int(round(h * 0.85)))
    x1, x2 = int(round(w * 0.15)), max(int(round(w * 0.15)) + 1, int(round(w * 0.85)))
    central = tile_bgr[y1:y2, x1:x2]

    gray = cv2.cvtColor(central, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)

    dct = cv2.dct(resized)
    # Extract top-left 8x8 low-frequency coefficients
    dct_low = dct[:8, :8]
    # Exclude DC coefficient at [0,0] from median calculation
    med = float(np.median(dct_low.flatten()[1:]))

    # Construct 64-bit integer
    bit_arr = (dct_low > med).flatten()
    hash_val = 0
    for b in bit_arr:
        hash_val = (hash_val << 1) | int(b)
    return hash_val


def compute_visual_core(
    tile_bgr: np.ndarray,
    crop_box_ratio: tuple[float, float, float, float] = (0.15, 0.15, 0.85, 0.85),
) -> np.ndarray:
    """Extracts a normalized 48x48 grayscale feature array from central crop."""
    if tile_bgr is None or tile_bgr.size == 0:
        return np.zeros((48, 48), dtype=np.float32)

    h, w = tile_bgr.shape[:2]
    y1_r, x1_r, y2_r, x2_r = crop_box_ratio
    y1 = int(round(h * y1_r))
    y2 = max(y1 + 1, int(round(h * y2_r)))
    x1 = int(round(w * x1_r))
    x2 = max(x1 + 1, int(round(w * x2_r)))
    central = tile_bgr[y1:y2, x1:x2]

    gray = cv2.cvtColor(central, cv2.COLOR_BGR2GRAY)
    thumb = cv2.resize(gray, (48, 48), interpolation=cv2.INTER_AREA).astype(np.float32)

    # Normalize contrast/brightness
    mean_val = float(np.mean(thumb))
    std_val = float(np.std(thumb))
    if std_val > 1e-4:
        norm = (thumb - mean_val) / std_val
    else:
        norm = thumb - mean_val
    return norm


def hamming_distance(h1: int, h2: int) -> int:
    """Calculates bitwise Hamming distance between two 64-bit integers."""
    return bin(h1 ^ h2).count("1")


def are_visually_identical(
    tile_a: np.ndarray,
    tile_b: np.ndarray,
    hash_a: Optional[int] = None,
    hash_b: Optional[int] = None,
    diff_threshold: float = 12.0,
    phash_threshold: int = 10,
    crop_box_ratio: tuple[float, float, float, float] = (0.15, 0.15, 0.85, 0.85),
) -> tuple[bool, float, int]:
    """Two-stage duplicate check: fast pHash shortlist followed by normalized MAE confirmation."""
    ha = hash_a if hash_a is not None else compute_phash(tile_a)
    hb = hash_b if hash_b is not None else compute_phash(tile_b)

    dist = hamming_distance(ha, hb)
    if dist > phash_threshold:
        return False, 999.0, dist

    norm_a = compute_visual_core(tile_a, crop_box_ratio=crop_box_ratio)
    norm_b = compute_visual_core(tile_b, crop_box_ratio=crop_box_ratio)

    # Scaled MAE
    mae = float(np.mean(np.abs(norm_a - norm_b))) * 25.0
    is_dup = (mae < diff_threshold)
    return is_dup, mae, dist


class AccountDeduplicator:
    """Manages category-scoped, account-level asset deduplication across screenshots."""

    def __init__(
        self,
        diff_threshold: float = 12.0,
        phash_threshold: int = 10,
        duplicate_mae_threshold: Optional[float] = None,
        duplicate_phash_max_distance: Optional[int] = None,
        category_profiles: Optional[dict[str, DedupProfile]] = None,
    ):
        self.diff_threshold = duplicate_mae_threshold if duplicate_mae_threshold is not None else diff_threshold
        self.phash_threshold = duplicate_phash_max_distance if duplicate_phash_max_distance is not None else phash_threshold
        self.category_profiles = dict(DEFAULT_CATEGORY_DEDUP_PROFILES)
        if category_profiles:
            self.category_profiles.update(category_profiles)

    @property
    def mae_threshold(self) -> float:
        return self.diff_threshold

    @property
    def phash_max_distance(self) -> int:
        return self.phash_threshold

    def get_profile(self, category: str) -> DedupProfile:
        cat_upper = category.upper()
        if cat_upper in self.category_profiles:
            prof = self.category_profiles[cat_upper]
            return DedupProfile(
                name=prof.name,
                crop_box_ratio=prof.crop_box_ratio,
                phash_threshold=min(self.phash_threshold, prof.phash_threshold),
                diff_threshold=min(self.diff_threshold, prof.diff_threshold),
            )
        return DedupProfile(
            name=cat_upper,
            crop_box_ratio=(0.15, 0.15, 0.85, 0.85),
            phash_threshold=self.phash_threshold,
            diff_threshold=self.diff_threshold,
        )

    def deduplicate_session_assets(
        self,
        assets: list[DetectedAsset],
        source_tiles: dict[str, np.ndarray],  # map asset_id -> original tile BGR
        source_indices: dict[str, int],      # map source_id -> source_index
    ) -> tuple[list[DetectedAsset], int]:
        """Runs deterministic category-scoped deduplication across all session assets."""
        if not assets:
            return [], 0

        # Sort assets deterministically: active items first, then source_index asc, row asc, col asc, asset.id asc
        sorted_assets = sorted(
            assets,
            key=lambda a: (
                0 if (not a.locked and not a.empty and not a.partial) else 1,
                source_indices.get(a.source_id, 99999),
                a.grid_position[0],
                a.grid_position[1],
                a.id,
            ),
        )

        canonical_by_cat: dict[str, list[tuple[DetectedAsset, np.ndarray, int]]] = {}
        duplicates_count = 0

        for asset in sorted_assets:
            cat = asset.category.upper()
            if cat not in canonical_by_cat:
                canonical_by_cat[cat] = []

            # Filtered empty cards do not participate in visual dedup to prevent false duplicate chains
            if asset.empty:
                asset.duplicate = False
                asset.duplicate_of = None
                continue

            tile = source_tiles.get(asset.id)
            if tile is None or tile.size == 0:
                asset.duplicate = False
                asset.duplicate_of = None
                continue

            # Compute hash once
            h = compute_phash(tile)
            matched_canonical_id: Optional[str] = None
            prof = self.get_profile(cat)

            for can_asset, can_tile, can_h in canonical_by_cat[cat]:
                is_dup, _, _ = are_visually_identical(
                    tile,
                    can_tile,
                    hash_a=h,
                    hash_b=can_h,
                    diff_threshold=prof.diff_threshold,
                    phash_threshold=prof.phash_threshold,
                    crop_box_ratio=prof.crop_box_ratio,
                )
                if is_dup:
                    matched_canonical_id = can_asset.id
                    break

            if matched_canonical_id is not None:
                asset.duplicate = True
                asset.duplicate_of = matched_canonical_id
                duplicates_count += 1
            else:
                asset.duplicate = False
                asset.duplicate_of = None
                # Only non-empty, non-partial cards may serve as canonical references
                if not asset.partial:
                    canonical_by_cat[cat].append((asset, tile, h))

        return sorted_assets, duplicates_count
