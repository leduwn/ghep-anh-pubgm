"""Deterministic screen classifier aggregating measurable computer vision signals."""

from __future__ import annotations

import time
from typing import Any, Optional

import cv2
import numpy as np

from core.constants import (
    CLASSIFIER_VERSION,
    Category,
    Decision,
    DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD,
    DEFAULT_CLASSIFIER_REVIEW_THRESHOLD,
    DEFAULT_CLASSIFIER_AMBIGUITY_MARGIN,
)
from core.models import ClassificationResult
from .classification_context import ClassificationContext
from .classification_signals import (
    SignalResult,
    detect_blue_indicator,
    detect_gun_lab_signals,
    detect_wardrobe_signals,
    detect_backpack_selector_signals,
    detect_detail_popup_signals,
    detect_accessory_signals,
    detect_outfit_lobby_signals,
)


class ScreenClassifier:
    """Classifies PUBG Mobile screenshot contexts into canonical item categories."""

    VERSION = CLASSIFIER_VERSION

    def __init__(
        self,
        accept_threshold: float = DEFAULT_CLASSIFIER_ACCEPT_THRESHOLD,
        review_threshold: float = DEFAULT_CLASSIFIER_REVIEW_THRESHOLD,
        ambiguity_margin: float = DEFAULT_CLASSIFIER_AMBIGUITY_MARGIN,
    ):
        self.accept_threshold = accept_threshold
        self.review_threshold = review_threshold
        self.ambiguity_margin = ambiguity_margin

    def classify(self, context: ClassificationContext) -> ClassificationResult:
        """Runs feature extraction, evidence accumulation, conflict resolution, and decision."""
        t0 = time.perf_counter()
        reasons: list[str] = []
        signals_map: dict[str, float] = {}

        # 1. Main tab blue indicator
        main_tab_y, mt_sig = detect_blue_indicator(context, 2520.0, 2620.0)
        signals_map["main_tab_indicator_y"] = main_tab_y if main_tab_y is not None else -1.0
        signals_map["main_tab_indicator_score"] = mt_sig.score
        signals_map["main_tab_indicator_rel"] = mt_sig.reliability

        main_tab_name = "NONE"
        near_boundary = False
        if main_tab_y is not None:
            ref_y = main_tab_y * ClassificationContext.REF_HEIGHT
            for b in (300.0, 475.0, 665.0, 900.0, 1150.0):
                if abs(ref_y - b) <= 12.0:
                    near_boundary = True
                    break

            if ref_y < 300.0:
                main_tab_name = "OUTFIT"
            elif ref_y < 475.0:
                main_tab_name = "NORMAL_GUN"
            elif ref_y < 665.0:
                main_tab_name = "VEHICLE"
            elif ref_y < 900.0:
                main_tab_name = "ACCESSORY"
            elif ref_y < 1150.0:
                main_tab_name = "MISC"
            else:
                main_tab_name = "OTHER"

        # 2. Extract measurable domain signals
        gun_sigs = detect_gun_lab_signals(context)
        for k, v in gun_sigs.items():
            signals_map[k] = v.score

        wardrobe_sigs = detect_wardrobe_signals(context)
        for k, v in wardrobe_sigs.items():
            signals_map[k] = v.score

        backpack_sig = detect_backpack_selector_signals(context)
        signals_map[backpack_sig.name] = backpack_sig.score

        popup_sig = detect_detail_popup_signals(context)
        signals_map[popup_sig.name] = popup_sig.score

        acc_sigs = detect_accessory_signals(context)
        for k, v in acc_sigs.items():
            signals_map[k] = v.score

        lobby_sigs = detect_outfit_lobby_signals(context)
        for k, v in lobby_sigs.items():
            signals_map[k] = v.score

        # 3. Subtab blue indicator
        sub_tab_y, st_sig = detect_blue_indicator(context, 2390.0, 2495.0)
        signals_map["sub_tab_indicator_y"] = sub_tab_y if sub_tab_y is not None else -1.0
        signals_map["sub_tab_indicator_score"] = st_sig.score
        signals_map["sub_tab_indicator_rel"] = st_sig.reliability
        ref_sub_y = sub_tab_y * ClassificationContext.REF_HEIGHT if sub_tab_y is not None else None

        # 4. Synthesize evidence for candidates
        candidates: dict[Category, float] = {cat: 0.0 for cat in Category}

        # Wardrobe layout check
        grid_score = wardrobe_sigs["inventory_grid_rhythm"].score
        rail_score = wardrobe_sigs["rail_smoothness"].score
        has_wardrobe = (grid_score >= 0.50 and rail_score >= 0.40)

        # Gun Lab Evidence
        header_sc = gun_sigs["gun_lab_header"].score
        orange_sc = gun_sigs["gun_lab_orange_badge"].score
        dark_sc = gun_sigs["gun_lab_dark_center"].score

        if header_sc >= 0.40 and orange_sc >= 0.40 and dark_sc >= 0.40:
            gun_comp = 0.35 * header_sc + 0.35 * orange_sc + 0.30 * dark_sc
            candidates[Category.GUN] = min(0.97, 0.70 + 0.27 * gun_comp)
            reasons.append("Gun Lab screen confirmed (header text, orange badge, dark workshop)")
        elif dark_sc >= 0.40 and (header_sc < 0.20 or orange_sc < 0.20):
            candidates[Category.GUN] = 0.20
        else:
            candidates[Category.GUN] = 0.0

        # Normal Gun tab rule:
        if main_tab_name == "NORMAL_GUN" and candidates[Category.GUN] < 0.70:
            candidates[Category.GUN] = 0.0
            candidates[Category.OTHER] = 0.86
            reasons.append("Normal gun inventory tab detected; only Gun Lab is processed as GUN")

        # Vehicle Evidence
        if main_tab_name == "VEHICLE":
            rel_multiplier = 0.94 if mt_sig.reliability >= 0.9 else 0.80
            if near_boundary:
                rel_multiplier -= 0.15
            candidates[Category.VEHICLE] = max(candidates[Category.VEHICLE], rel_multiplier)
            reasons.append(f"Main tab indicator in vehicle section (y={main_tab_y:.3f})")

        # Backpack Evidence: wardrobe + selector
        if (main_tab_name in {"OUTFIT", "NONE"}) and has_wardrobe and backpack_sig.score >= 0.60:
            candidates[Category.BACKPACK] = 0.95
            reasons.append("Wardrobe layout with 3-level backpack level selector")
        elif (main_tab_name in {"OUTFIT", "NONE"}) and backpack_sig.score >= 0.60:
            candidates[Category.BACKPACK] = 0.65

        # Item Set Evidence: wardrobe + popup frame
        if (main_tab_name in {"OUTFIT", "NONE"}) and has_wardrobe and popup_sig.score >= 0.60:
            candidates[Category.ITEM_SET] = 0.94
            reasons.append("Wardrobe layout with item detail popup frame")

        # Helmet & Mask subtab evidence with boundary tolerance
        if (main_tab_name in {"OUTFIT", "NONE"}) and has_wardrobe and ref_sub_y is not None:
            if 300.0 <= ref_sub_y < 450.0:
                rel = 0.93 if st_sig.reliability >= 0.9 else 0.80
                if abs(ref_sub_y - 450.0) <= 15.0:
                    candidates[Category.HELMET] = rel - 0.12
                    candidates[Category.MASK] = rel - 0.15
                    reasons.append("Subtab indicator near Helmet/Mask boundary (ambiguous)")
                else:
                    candidates[Category.HELMET] = rel
                    reasons.append(f"Wardrobe helmet subtab selected (sub_y={ref_sub_y:.1f})")
            elif ref_sub_y >= 450.0 and backpack_sig.score < 0.60:
                rel = 0.91 if st_sig.reliability >= 0.9 else 0.78
                if abs(ref_sub_y - 450.0) <= 15.0:
                    candidates[Category.MASK] = rel - 0.12
                    candidates[Category.HELMET] = rel - 0.15
                    reasons.append("Subtab indicator near Mask/Helmet boundary (ambiguous)")
                else:
                    candidates[Category.MASK] = rel
                    reasons.append(f"Wardrobe mask subtab selected (sub_y={ref_sub_y:.1f})")

        # Outfit Evidence:
        # Path A: Wardrobe screen with SET subtab (<300) and NO popup frame
        if (main_tab_name in {"OUTFIT", "NONE"}) and has_wardrobe and (ref_sub_y is None or ref_sub_y < 300.0) and popup_sig.score < 0.60:
            candidates[Category.OUTFIT] = max(candidates[Category.OUTFIT], 0.93)
            reasons.append("Wardrobe outfit inventory layout without detail popup")

        # Path B: Outfit lobby
        supercar_match = lobby_sigs["supercar_ceiling"].score >= 0.80
        right_ui = lobby_sigs["right_side_ui_variance"].score >= 0.25
        char_pres = lobby_sigs["character_presence"].score >= 0.25

        if supercar_match and right_ui:
            candidates[Category.OUTFIT] = max(candidates[Category.OUTFIT], 0.92)
            reasons.append("Supercar outfit lobby template match confirmed")
        elif right_ui and char_pres and (main_tab_name in {"OUTFIT", "NONE"}):
            if context.aspect_ratio >= 1.6 and not has_wardrobe:
                candidates[Category.OUTFIT] = max(candidates[Category.OUTFIT], 0.84)
                reasons.append("Full-body outfit lobby scene confirmed")

        # Accessory tab candidates (Emote, Grenade, Parachute)
        if main_tab_name == "ACCESSORY":
            emote_sc = acc_sigs["emote_silhouette"].score
            sep_sc = acc_sigs["grenade_subtypes"].score
            para_sc = acc_sigs["parachute_geometry"].score

            if sep_sc >= 0.60:
                candidates[Category.GRENADE] = 0.93
                reasons.append("Accessory grenade 4-subtype slots header detected")
            elif emote_sc >= 0.60:
                candidates[Category.EMOTE] = 0.93
                reasons.append(f"Accessory emote silhouettes confirmed ({acc_sigs['emote_silhouette'].raw_value})")
            elif para_sc >= 0.60:
                candidates[Category.PARACHUTE] = 0.91
                reasons.append("Accessory parachute early first-row geometry confirmed")
            else:
                candidates[Category.MISC] = 0.60
                reasons.append("Accessory tab detected without distinct grenade/emote/parachute pattern")

        # Misc Tab (Tab 5)
        if main_tab_name == "MISC":
            misc_score = 0.88 if mt_sig.reliability >= 0.9 else 0.75
            candidates[Category.MISC] = max(candidates[Category.MISC], misc_score)
            reasons.append("Main tab item/misc container tab selected")

        # Default OTHER candidate if everything else is low
        if max(candidates.values()) < 0.35:
            candidates[Category.OTHER] = 0.35
            reasons.append("No conclusive category pattern matched")

        # 5. Conflict resolution & ranking
        sorted_candidates = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
        top_cat, top_score = sorted_candidates[0]
        second_cat, second_score = sorted_candidates[1]

        # Ambiguity margin check
        is_ambiguous = False
        if top_score >= self.review_threshold and second_score >= 0.40:
            if (top_score - second_score) < self.ambiguity_margin:
                is_ambiguous = True

        # Decision calculation
        if is_ambiguous:
            decision = Decision.REVIEW.value
            reasons.append(
                f"Top candidates {top_cat.value}={top_score:.2f} and {second_cat.value}={second_score:.2f} "
                f"within ambiguity margin {self.ambiguity_margin:.2f}"
            )
        elif top_score >= self.accept_threshold:
            decision = Decision.AUTO_ACCEPT.value
        elif top_score >= self.review_threshold:
            decision = Decision.REVIEW.value
            reasons.append(f"Confidence {top_score:.2f} below auto accept threshold {self.accept_threshold:.2f}")
        else:
            decision = Decision.UNKNOWN.value
            reasons.append(f"Confidence {top_score:.2f} below review threshold {self.review_threshold:.2f}")

        final_category = top_cat.value
        candidate_category: Optional[str] = top_cat.value
        if decision == Decision.UNKNOWN and top_score < 0.35:
            final_category = Category.OTHER.value

        alternatives = [
            {"category": cat.value, "score": round(score, 3)}
            for cat, score in sorted_candidates[1:4]
            if score > 0.15
        ]

        duration_ms = (time.perf_counter() - t0) * 1000.0

        return ClassificationResult(
            category=final_category,
            confidence=round(top_score, 4),
            decision=decision,
            reasons=reasons,
            detector="screen_classifier",
            detector_version=self.VERSION,
            signals=signals_map,
            candidate_category=candidate_category,
            alternatives=alternatives,
            duration_ms=round(duration_ms, 2),
        )

