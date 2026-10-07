"""UID extraction across primary screen ROIs and multi-source consensus resolution."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

import numpy as np

from core.models import Rect
from .cache import OCRCache, build_ocr_cache_key
from .engine import OCREngine
from .models import UIDCandidate, UIDConsensusResult
from .parsers import parse_uid

logger = logging.getLogger("auto_cut.ocr.uid")


def get_uid_candidate_rois(image_shape: tuple[int, ...]) -> list[tuple[str, Rect]]:
    """Generates cascade of candidate ROIs where PUBG Mobile UIDs typically appear."""
    h, w = image_shape[:2]
    return [
        ("bottom_left", Rect(0, int(round(0.85 * h)), int(round(0.42 * w)), int(round(0.15 * h)))),
        ("top_right", Rect(int(round(0.60 * w)), 0, int(round(0.40 * w)), int(round(0.16 * h)))),
        ("top_left", Rect(0, 0, int(round(0.40 * w)), int(round(0.16 * h)))),
        ("bottom_bar", Rect(0, int(round(0.80 * h)), w, int(round(0.20 * h)))),
    ]


class UIDOCRExtractor:
    """Extracts UID candidates from a single screenshot using ROI cascading."""

    def __init__(
        self,
        engine: OCREngine,
        cache: Optional[OCRCache] = None,
    ):
        self.engine = engine
        self.cache = cache

    def extract_from_source(
        self,
        image: np.ndarray,
        source_id: str,
        source_sha256: str,
        force: bool = False,
    ) -> list[UIDCandidate]:
        """Runs cascade ROI scanning on an ingested screenshot to extract UID candidates."""
        if image is None or image.size == 0:
            return []

        rois = get_uid_candidate_rois(image.shape)
        candidates: list[UIDCandidate] = []

        for roi_name, roi in rois:
            cache_key = build_ocr_cache_key(source_sha256, roi, route=f"uid_{roi_name}")
            observations = self.cache.get(cache_key, force=force) if self.cache else None

            if observations is None:
                observations = self.engine.read_text(image, roi=roi)
                if self.cache:
                    self.cache.put(cache_key, observations)

            roi_candidates = parse_uid(observations, source_id=source_id, roi_name=roi_name)
            if roi_candidates:
                candidates.extend(roi_candidates)
                # If high-confidence labeled candidate found in bottom-left or top-right, cascade can complete early
                if any(c.confidence >= 0.85 for c in roi_candidates):
                    break

        return candidates


def resolve_uid_consensus(
    candidates: list[UIDCandidate],
    accept_threshold: float = 0.80,
    review_threshold: float = 0.50,
) -> UIDConsensusResult:
    """Aggregates UID candidates across all account sources to resolve consensus and detect conflicts."""
    if not candidates:
        return UIDConsensusResult(
            uid=None,
            confidence=0.0,
            candidates=[],
            sources_count=0,
            has_conflict=False,
            review_required=False,
            reasons=["No UID candidates detected across sources"],
        )

    # Group candidates by normalized UID string
    groups: dict[str, list[UIDCandidate]] = defaultdict(list)
    for c in candidates:
        groups[c.uid].append(c)

    scored_groups: list[tuple[str, float, int, list[UIDCandidate]]] = []
    for uid_val, group_cands in groups.items():
        unique_sources = {c.source_id for c in group_cands}
        src_count = len(unique_sources)
        base_conf = max(c.confidence for c in group_cands)
        # Multi-source consensus boost: +0.05 per additional corroborating source (up to 1.0)
        boosted_conf = min(1.0, base_conf + 0.05 * (src_count - 1))
        scored_groups.append((uid_val, boosted_conf, src_count, group_cands))

    # Sort descending by boosted confidence, then source count
    scored_groups.sort(key=lambda x: (x[1], x[2]), reverse=True)

    best_uid, best_conf, best_src_count, best_cands = scored_groups[0]
    reasons: list[str] = []
    has_conflict = False
    review_required = False

    # Check for genuine conflicts (multiple different UIDs with high confidence)
    if len(scored_groups) > 1:
        second_uid, second_conf, second_src_count, _ = scored_groups[1]
        if second_conf >= review_threshold and second_uid != best_uid:
            has_conflict = True
            review_required = True
            reasons.append(
                f"UID conflict: observed '{best_uid}' (conf={best_conf:.2f}, {best_src_count} src) "
                f"and '{second_uid}' (conf={second_conf:.2f}, {second_src_count} src)"
            )

    if best_conf < review_threshold:
        review_required = True
        reasons.append(f"UID confidence below review threshold ({best_conf:.2f} < {review_threshold:.2f})")
    elif best_src_count > 1:
        reasons.append(f"UID corroborated across {best_src_count} independent sources")

    accepted_uid: Optional[str] = best_uid
    if has_conflict:
        accepted_uid = None
        reasons.append("UID rejected due to multi-source conflict")
    elif best_conf < accept_threshold:
        accepted_uid = None
        review_required = True
        reasons.append(f"UID confidence below accept threshold ({best_conf:.2f} < {accept_threshold:.2f})")

    return UIDConsensusResult(
        uid=accepted_uid,
        confidence=round(best_conf, 3),
        candidates=candidates,
        sources_count=best_src_count,
        has_conflict=has_conflict,
        review_required=review_required,
        reasons=reasons,
    )
