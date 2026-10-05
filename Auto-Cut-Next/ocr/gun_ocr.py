"""Weapon metadata extractor coordinating level, name, and elimination counter OCR."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from core.models import DetectedAsset, GunMetadata, Rect
from .cache import OCRCache, build_ocr_cache_key
from .engine import OCREngine
from .models import GunOCRResult, OCRObservation
from .parsers import parse_gun_level, parse_gun_name, parse_kill_counter
from .preprocessing import check_counter_badge_presence

logger = logging.getLogger("auto_cut.ocr.gun")


def resolve_gun_rois(asset: DetectedAsset, image_shape: tuple[int, ...]) -> tuple[Rect, Rect, Rect]:
    """Resolves level_roi, name_roi, and kill_counter_roi from asset metadata or calculates defaults."""
    h, w = image_shape[:2]
    meta = asset.metadata or {}

    # 1. Level ROI
    if "level_roi" in meta and isinstance(meta["level_roi"], dict):
        level_roi = Rect.from_dict(meta["level_roi"])
    else:
        level_roi = Rect(0, int(round(0.08 * h)), int(round(0.25 * w)), int(round(0.12 * h)))

    # 2. Name ROI
    if "name_roi" in meta and isinstance(meta["name_roi"], dict):
        name_roi = Rect.from_dict(meta["name_roi"])
    else:
        name_roi = Rect(0, int(round(0.02 * h)), int(round(0.45 * w)), int(round(0.10 * h)))

    # 3. Kill Counter ROI
    if "kill_counter_roi" in meta and isinstance(meta["kill_counter_roi"], dict):
        counter_roi = Rect.from_dict(meta["kill_counter_roi"])
    else:
        card_gx = asset.crop_rect.x if not asset.crop_rect.is_empty else int(round(0.70 * w))
        c_x2 = max(0, card_gx - 10)
        c_x1 = max(0, card_gx - int(round(w * 0.16)))
        c_y1 = int(round(h * 0.07))
        c_y2 = int(round(h * 0.20))
        counter_roi = Rect(c_x1, c_y1, max(1, c_x2 - c_x1), max(1, c_y2 - c_y1))

    return level_roi, name_roi, counter_roi


class GunOCRExtractor:
    """Extracts weapon name, upgrade level, and elimination counter for a detected gun asset."""

    def __init__(
        self,
        engine: OCREngine,
        cache: Optional[OCRCache] = None,
        accept_threshold: float = 0.80,
        review_threshold: float = 0.50,
    ):
        self.engine = engine
        self.cache = cache
        self.accept_threshold = accept_threshold
        self.review_threshold = review_threshold

    def extract(
        self,
        image: np.ndarray,
        source_sha256: str,
        asset: DetectedAsset,
        force: bool = False,
    ) -> GunOCRResult:
        """Runs OCR extraction pipeline on the source image for the given gun asset."""
        level_roi, name_roi, counter_roi = resolve_gun_rois(asset, image.shape)
        review_reasons: list[str] = []

        # --- 1. Level OCR ---
        level_key = build_ocr_cache_key(source_sha256, level_roi, route="gun_level")
        level_obs = self.cache.get(level_key, force=force) if self.cache else None
        if level_obs is None:
            level_obs = self.engine.read_text(image, roi=level_roi)
            if self.cache:
                self.cache.put(level_key, level_obs)

        level, level_src, level_conf, level_reasons, raw_lvl = parse_gun_level(level_obs)
        if level_reasons:
            review_reasons.extend(level_reasons)

        # --- 2. Weapon Name OCR ---
        name_key = build_ocr_cache_key(source_sha256, name_roi, route="gun_name")
        name_obs = self.cache.get(name_key, force=force) if self.cache else None
        if name_obs is None:
            name_obs = self.engine.read_text(image, roi=name_roi)
            if self.cache:
                self.cache.put(name_key, name_obs)

        w_name, name_conf, name_reasons, raw_name = parse_gun_name(name_obs)
        if name_reasons:
            review_reasons.extend(name_reasons)

        # --- 3. Elimination Counter Visual Presence & OCR ---
        is_present, edge_count, color_score = check_counter_badge_presence(image, counter_roi)
        kill_counter = None
        counter_conf = 0.0
        raw_counter = None

        if is_present:
            counter_key = build_ocr_cache_key(source_sha256, counter_roi, route="gun_counter")
            counter_obs = self.cache.get(counter_key, force=force) if self.cache else None
            if counter_obs is None:
                counter_obs = self.engine.read_text(image, roi=counter_roi, allowlist="0123456789")
                if self.cache:
                    self.cache.put(counter_key, counter_obs)

            kill_counter, counter_conf, counter_reasons, raw_counter = parse_kill_counter(
                counter_obs, counter_present=True
            )
            if counter_reasons:
                review_reasons.extend(counter_reasons)

        # --- 4. Composite Confidence & Review Assessment ---
        scores = []
        if level is not None:
            scores.append(level_conf)
        if w_name is not None:
            scores.append(name_conf)
        if kill_counter is not None:
            scores.append(counter_conf)

        ocr_conf = float(sum(scores) / len(scores)) if scores else 0.0
        review_required = False

        if level is None:
            review_required = True
            review_reasons.append("Weapon level could not be identified")
        if w_name is None:
            review_required = True
            review_reasons.append("Weapon name could not be identified")
        if ocr_conf < self.review_threshold:
            review_required = True
            review_reasons.append(f"OCR overall confidence below threshold ({ocr_conf:.2f} < {self.review_threshold:.2f})")

        return GunOCRResult(
            level=level,
            level_source=level_src,
            weapon_name=w_name,
            weapon_family=None,
            counter_present=is_present,
            kill_counter=kill_counter,
            ocr_confidence=round(ocr_conf, 3),
            level_confidence=round(level_conf, 3),
            name_confidence=round(name_conf, 3),
            counter_confidence=round(counter_conf, 3),
            review_required=review_required,
            review_reasons=review_reasons,
            raw_level_text=raw_lvl,
            raw_name_text=raw_name,
            raw_counter_text=raw_counter,
        )

    def apply_to_asset(
        self,
        asset: DetectedAsset,
        result: GunOCRResult,
    ) -> None:
        """Applies GunOCRResult to the asset while strictly preserving manual overrides."""
        # Preserve existing manual overrides
        prev_lvl_man = asset.gun_metadata.level_manual if asset.gun_metadata else None
        prev_nm_man = asset.gun_metadata.name_manual if asset.gun_metadata else None
        prev_cnt_man = asset.gun_metadata.counter_manual if asset.gun_metadata else None

        asset.gun_metadata = GunMetadata(
            level=result.level,
            weapon_name=result.weapon_name,
            weapon_family=result.weapon_family,
            kill_counter=result.kill_counter,
            badge=None,
            ocr_confidence=result.ocr_confidence,
            level_manual=prev_lvl_man,
            name_manual=prev_nm_man,
            counter_manual=prev_cnt_man,
            raw_level_text=result.raw_level_text,
            raw_name_text=result.raw_name_text,
            raw_counter_text=result.raw_counter_text,
            counter_present=result.counter_present,
            counter_confidence=result.counter_confidence,
            level_confidence=result.level_confidence,
            name_confidence=result.name_confidence,
            level_source=result.level_source,
            needs_review=result.review_required,
            review_reasons=list(result.review_reasons),
        )

        if result.review_required:
            asset.review_required = True
            for r in result.review_reasons:
                if r not in asset.review_reasons:
                    asset.review_reasons.append(r)
