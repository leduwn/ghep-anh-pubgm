"""Central review queue builder inspecting AccountSession state."""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.constants import (
    Category,
    Decision,
    DetectionStatus,
    ReviewSubsystem,
    ReviewStatus,
    ReviewPriority,
    ReviewReason,
)
from core.models import AccountSession, DetectedAsset, SourceImage
from .models import (
    ReviewItem,
    ReviewResolution,
    make_classification_review_id,
    make_detection_review_id,
    make_asset_quality_review_id,
    make_ocr_review_id,
    make_uid_review_id,
    compute_machine_fingerprint,
)

logger = logging.getLogger("auto_cut.review.builder")


class ReviewQueueBuilder:
    """Consolidates classification, detection, asset quality, OCR, and UID review tasks."""

    def __init__(
        self,
        ocr_accept_threshold: float = 0.80,
        detector_confidence_threshold: float = 0.60,
    ):
        self.ocr_accept_threshold = ocr_accept_threshold
        self.detector_confidence_threshold = detector_confidence_threshold

    def build_queue(self, session: AccountSession) -> list[ReviewItem]:
        """Builds a consolidated, deterministic review queue from current session state.

        Idempotent: running multiple times on unchanged session yields identical items.
        Preserves existing manual resolutions and detects staleness on machine acceptances.
        """
        source_index_map: dict[str, int] = {
            src.id: src.source_index for src in session.sources.values()
        }

        generated_items: dict[str, ReviewItem] = {}

        # ----------------------------------------------------------------------
        # 1. Classification Review Items
        # ----------------------------------------------------------------------
        for s_id, src in sorted(session.sources.items(), key=lambda it: it[1].source_index):
            cl = session.classifications.get(s_id)
            if cl is None:
                continue

            # Check if source classification was manually overridden
            is_manual_override = False
            manual_cat: Optional[str] = None
            if hasattr(src, "manual_category") and getattr(src, "manual_category"):
                manual_cat = getattr(src, "manual_category")
                is_manual_override = True

            # Review item condition: REVIEW, UNKNOWN, ERROR or manual override
            needs_review = (
                cl.decision in {Decision.REVIEW.value, Decision.UNKNOWN.value, Decision.ERROR.value}
                or is_manual_override
            )
            if not needs_review:
                continue

            review_id = make_classification_review_id(s_id)
            if cl.decision == Decision.ERROR.value:
                priority = ReviewPriority.P0.value
                reason = ReviewReason.CLASSIFICATION_ERROR.value
            elif cl.decision == Decision.UNKNOWN.value:
                priority = ReviewPriority.P1.value
                reason = ReviewReason.CLASSIFICATION_UNKNOWN.value
            elif cl.alternatives or cl.candidate_category:
                priority = ReviewPriority.P2.value
                reason = ReviewReason.CLASSIFICATION_AMBIGUOUS.value
            else:
                priority = ReviewPriority.P2.value
                reason = ReviewReason.CLASSIFICATION_LOW_CONFIDENCE.value

            fingerprint = compute_machine_fingerprint(
                subsystem_version=cl.detector_version,
                value=cl.category,
                confidence=cl.confidence,
                reason=cl.decision,
            )

            msg = (
                f"Classification requires review: {cl.category} "
                f"(confidence={cl.confidence:.2f}, decision={cl.decision})"
            )
            if cl.alternatives:
                top_alt = cl.alternatives[0]
                alt_cat = top_alt.get("category", "")
                alt_sc = top_alt.get("score", 0.0)
                msg += f", alternative={alt_cat} ({alt_sc:.2f})"

            item = ReviewItem(
                id=review_id,
                subsystem=ReviewSubsystem.CLASSIFICATION.value,
                status=ReviewStatus.OPEN.value,
                priority=priority,
                reason=reason,
                message=msg,
                source_id=s_id,
                category=cl.category,
                field_name="category",
                confidence=cl.confidence,
                machine_value=cl.category,
                candidates=cl.alternatives,
                metadata={
                    "decision": cl.decision,
                    "reasons": cl.reasons,
                    "signals": cl.signals,
                    "candidate_category": cl.candidate_category,
                    "filename": src.filename,
                },
                fingerprint=fingerprint,
            )

            if is_manual_override:
                item.status = ReviewStatus.RESOLVED_MANUAL.value
                item.resolution = ReviewResolution(
                    action="set_category",
                    resolved_by="manual",
                    value=manual_cat,
                    notes=f"Manually categorized as {manual_cat}",
                )

            generated_items[review_id] = item

        # ----------------------------------------------------------------------
        # 2. Source-Level Detection Review Items
        # ----------------------------------------------------------------------
        for s_id, src in sorted(session.sources.items(), key=lambda it: it[1].source_index):
            det = session.detections.get(s_id)
            if det is None:
                continue

            cl = session.classifications.get(s_id)
            cat_val = cl.category.upper() if cl else "UNKNOWN"

            # Check trigger conditions:
            # - status == REVIEW
            # - status == NO_GRID for an eligible category expected to produce assets
            # - fallback_used on semantic category (GUN, VEHICLE, OUTFIT)
            # - status == ERROR
            # - specialized confidence < threshold
            is_no_grid = (det.status == DetectionStatus.NO_GRID.value)
            is_error = (det.status == DetectionStatus.ERROR.value)
            is_review = (det.status == DetectionStatus.REVIEW.value)
            is_semantic_fallback = bool(
                getattr(det, "fallback_used", False) and cat_val in {"GUN", "VEHICLE", "OUTFIT"}
            )
            spec_conf = getattr(det, "specialized_confidence", det.confidence)
            spec_low = bool(
                getattr(det, "specialized_attempted", False)
                and spec_conf < self.detector_confidence_threshold
            )

            needs_detection_review = is_error or is_review or is_semantic_fallback or (
                is_no_grid and cat_val in {"GUN", "VEHICLE", "OUTFIT", "HELMET", "BACKPACK", "ITEM_SET"}
            )

            if not needs_detection_review:
                continue

            review_id = make_detection_review_id(s_id)
            if is_error:
                priority = ReviewPriority.P0.value
                reason = ReviewReason.PIPELINE_ERROR.value
            elif is_no_grid:
                priority = ReviewPriority.P1.value if cat_val in {"GUN", "VEHICLE"} else ReviewPriority.P2.value
                reason = ReviewReason.NO_GRID.value
            elif is_semantic_fallback:
                priority = ReviewPriority.P2.value
                reason = ReviewReason.SEMANTIC_FALLBACK.value
            elif spec_low:
                priority = ReviewPriority.P2.value
                reason = ReviewReason.SPECIALIZED_DETECTOR_LOW_CONFIDENCE.value
            else:
                priority = ReviewPriority.P2.value
                reason = ReviewReason.DETECTION_REVIEW.value

            primary_det = getattr(det, "primary_detector", det.detector)
            fallback_det = getattr(det, "fallback_detector", None)
            fallback_att = getattr(det, "fallback_attempted", False)
            fallback_used = getattr(det, "fallback_used", False)
            fb_conf = getattr(det, "fallback_confidence", 0.0)

            # Assets count for source
            src_assets = [a for a in session.assets if a.source_id == s_id]

            fingerprint = compute_machine_fingerprint(
                subsystem_version=det.detector_version,
                value=det.detector,
                confidence=det.confidence,
                reason=det.status,
                extra_token=f"{fallback_used}:{len(src_assets)}",
            )

            msg = (
                f"Detection requires review on {src.filename}: "
                f"status={det.status}, detector={det.detector} (conf={det.confidence:.2f})"
            )
            if fallback_used:
                msg += f", fallback_used=True from {primary_det}"

            item = ReviewItem(
                id=review_id,
                subsystem=ReviewSubsystem.DETECTION.value,
                status=ReviewStatus.OPEN.value,
                priority=priority,
                reason=reason,
                message=msg,
                source_id=s_id,
                category=cat_val,
                confidence=det.confidence,
                machine_value=det.detector,
                metadata={
                    "status": det.status,
                    "primary_detector": primary_det,
                    "fallback_detector": fallback_det,
                    "fallback_attempted": fallback_att,
                    "fallback_used": fallback_used,
                    "specialized_confidence": spec_conf,
                    "fallback_confidence": fb_conf,
                    "candidate_count": len(src_assets),
                    "reasons": det.reasons,
                    "filename": src.filename,
                },
                fingerprint=fingerprint,
            )
            generated_items[review_id] = item

        # ----------------------------------------------------------------------
        # 3. Asset Quality Review Items (Deduplicated)
        # ----------------------------------------------------------------------
        for asset in session.assets:
            # Skip assets with manual override
            if asset.manual_override:
                continue

            # Only review meaningful actionable quality issues:
            # Partial, empty suspected, locked
            has_partial = asset.partial
            has_empty = asset.empty
            has_locked = asset.locked
            has_quality = bool(asset.review_required and not (has_partial or has_empty or has_locked))

            # Deduplication: if source already has a detection review (e.g. semantic fallback),
            # do not flood queue with identical items for every asset unless it has specific defects
            source_has_detection_review = make_detection_review_id(asset.source_id) in generated_items

            if has_partial:
                r_code = ReviewReason.PARTIAL_ASSET.value
                msg = f"Partial asset boundary detected (order={asset.order})"
            elif has_empty:
                r_code = ReviewReason.EMPTY_SUSPECTED.value
                msg = f"Suspected empty card tile (order={asset.order})"
            elif has_locked:
                r_code = ReviewReason.LOCKED_ASSET.value
                msg = f"Locked asset tile detected (order={asset.order})"
            elif has_quality and not source_has_detection_review:
                r_code = ReviewReason.QUALITY_REVIEW.value
                msg = f"Asset quality requires review (conf={asset.confidence:.2f})"
            else:
                continue

            review_id = make_asset_quality_review_id(asset.id, r_code)
            fingerprint = compute_machine_fingerprint(
                subsystem_version=asset.detector_version,
                value=asset.id,
                confidence=asset.confidence,
                reason=r_code,
            )

            item = ReviewItem(
                id=review_id,
                subsystem=ReviewSubsystem.ASSET_QUALITY.value,
                status=ReviewStatus.OPEN.value,
                priority=ReviewPriority.P3.value,
                reason=r_code,
                message=msg,
                source_id=asset.source_id,
                asset_id=asset.id,
                category=asset.category,
                confidence=asset.confidence,
                machine_value=asset.crop_rect.to_dict(),
                metadata={
                    "crop_rect": asset.crop_rect.to_dict(),
                    "quality_scores": asset.quality_scores,
                    "review_reasons": asset.review_reasons,
                },
                fingerprint=fingerprint,
            )
            generated_items[review_id] = item

        # ----------------------------------------------------------------------
        # 4. Field-Level Gun OCR Review Items
        # ----------------------------------------------------------------------
        for asset in session.assets:
            if asset.category != Category.GUN.value:
                continue

            gm = asset.gun_metadata
            if gm is None:
                continue

            # A. Field: level
            if gm.level_manual is not None:
                # Manually resolved
                lvl_id = make_ocr_review_id(asset.id, "level")
                generated_items[lvl_id] = ReviewItem(
                    id=lvl_id,
                    subsystem=ReviewSubsystem.OCR_GUN.value,
                    status=ReviewStatus.RESOLVED_MANUAL.value,
                    priority=ReviewPriority.P2.value,
                    reason=ReviewReason.OCR_LEVEL_LOW_CONFIDENCE.value,
                    message=f"Gun level manually set to {gm.level_manual}",
                    source_id=asset.source_id,
                    asset_id=asset.id,
                    category=Category.GUN.value,
                    field_name="level",
                    confidence=1.0,
                    machine_value=gm.level,
                    resolution=ReviewResolution(
                        action="set_level",
                        resolved_by="manual",
                        value=gm.level_manual,
                        notes=f"Manually set level to {gm.level_manual}",
                    ),
                )
            elif gm.effective_level is None or gm.level_confidence < self.ocr_accept_threshold:
                lvl_id = make_ocr_review_id(asset.id, "level")
                fp = compute_machine_fingerprint(
                    subsystem_version=session.ocr_version,
                    value=str(gm.level),
                    confidence=gm.level_confidence,
                    reason=gm.level_source,
                )
                generated_items[lvl_id] = ReviewItem(
                    id=lvl_id,
                    subsystem=ReviewSubsystem.OCR_GUN.value,
                    status=ReviewStatus.OPEN.value,
                    priority=ReviewPriority.P2.value,
                    reason=ReviewReason.OCR_LEVEL_LOW_CONFIDENCE.value,
                    message=f"Weapon level OCR uncertain: {gm.level} (conf={gm.level_confidence:.2f}, source={gm.level_source})",
                    source_id=asset.source_id,
                    asset_id=asset.id,
                    category=Category.GUN.value,
                    field_name="level",
                    confidence=gm.level_confidence,
                    machine_value=gm.level,
                    metadata={
                        "raw_text": gm.raw_level_text,
                        "level_source": gm.level_source,
                    },
                    fingerprint=fp,
                )

            # B. Field: name
            if gm.name_manual is not None:
                nm_id = make_ocr_review_id(asset.id, "name")
                generated_items[nm_id] = ReviewItem(
                    id=nm_id,
                    subsystem=ReviewSubsystem.OCR_GUN.value,
                    status=ReviewStatus.RESOLVED_MANUAL.value,
                    priority=ReviewPriority.P2.value,
                    reason=ReviewReason.OCR_NAME_LOW_CONFIDENCE.value,
                    message=f"Weapon name manually set to '{gm.name_manual}'",
                    source_id=asset.source_id,
                    asset_id=asset.id,
                    category=Category.GUN.value,
                    field_name="name",
                    confidence=1.0,
                    machine_value=gm.weapon_name,
                    resolution=ReviewResolution(
                        action="set_name",
                        resolved_by="manual",
                        value=gm.name_manual,
                        notes=f"Manually set name to '{gm.name_manual}'",
                    ),
                )
            elif not gm.weapon_name or gm.name_confidence < self.ocr_accept_threshold:
                nm_id = make_ocr_review_id(asset.id, "name")
                fp = compute_machine_fingerprint(
                    subsystem_version=session.ocr_version,
                    value=str(gm.weapon_name),
                    confidence=gm.name_confidence,
                    reason="name",
                )
                generated_items[nm_id] = ReviewItem(
                    id=nm_id,
                    subsystem=ReviewSubsystem.OCR_GUN.value,
                    status=ReviewStatus.OPEN.value,
                    priority=ReviewPriority.P2.value,
                    reason=ReviewReason.OCR_NAME_LOW_CONFIDENCE.value,
                    message=f"Weapon name OCR uncertain: '{gm.weapon_name}' (conf={gm.name_confidence:.2f})",
                    source_id=asset.source_id,
                    asset_id=asset.id,
                    category=Category.GUN.value,
                    field_name="name",
                    confidence=gm.name_confidence,
                    machine_value=gm.weapon_name,
                    metadata={"raw_text": gm.raw_name_text},
                    fingerprint=fp,
                )

            # C. Field: kill_counter (preserves counter semantics!)
            # Badge absent -> counter not required -> NO review
            # Badge present -> OCR weak/failed -> REVIEW counter
            if gm.counter_present:
                cnt_id = make_ocr_review_id(asset.id, "counter")
                if gm.counter_manual is not None:
                    generated_items[cnt_id] = ReviewItem(
                        id=cnt_id,
                        subsystem=ReviewSubsystem.OCR_GUN.value,
                        status=ReviewStatus.RESOLVED_MANUAL.value,
                        priority=ReviewPriority.P2.value,
                        reason=ReviewReason.OCR_COUNTER_UNCERTAIN.value,
                        message=f"Kill counter manually set to '{gm.counter_manual}'",
                        source_id=asset.source_id,
                        asset_id=asset.id,
                        category=Category.GUN.value,
                        field_name="counter",
                        confidence=1.0,
                        machine_value=gm.kill_counter,
                        resolution=ReviewResolution(
                            action="set_counter",
                            resolved_by="manual",
                            value=gm.counter_manual,
                            notes=f"Manually set counter to '{gm.counter_manual}'",
                        ),
                    )
                elif not gm.kill_counter or gm.counter_confidence < self.ocr_accept_threshold:
                    fp = compute_machine_fingerprint(
                        subsystem_version=session.ocr_version,
                        value=str(gm.kill_counter),
                        confidence=gm.counter_confidence,
                        reason="counter",
                    )
                    generated_items[cnt_id] = ReviewItem(
                        id=cnt_id,
                        subsystem=ReviewSubsystem.OCR_GUN.value,
                        status=ReviewStatus.OPEN.value,
                        priority=ReviewPriority.P2.value,
                        reason=ReviewReason.OCR_COUNTER_UNCERTAIN.value,
                        message=f"Kill counter badge present but count uncertain: '{gm.kill_counter}' (conf={gm.counter_confidence:.2f})",
                        source_id=asset.source_id,
                        asset_id=asset.id,
                        category=Category.GUN.value,
                        field_name="counter",
                        confidence=gm.counter_confidence,
                        machine_value=gm.kill_counter,
                        metadata={
                            "raw_text": gm.raw_counter_text,
                            "counter_present": True,
                        },
                        fingerprint=fp,
                    )

        # ----------------------------------------------------------------------
        # 5. UID Consensus Review Item
        # ----------------------------------------------------------------------
        uid_id = make_uid_review_id(session.account_id)
        if session.uid_manual is not None:
            generated_items[uid_id] = ReviewItem(
                id=uid_id,
                subsystem=ReviewSubsystem.UID.value,
                status=ReviewStatus.RESOLVED_MANUAL.value,
                priority=ReviewPriority.P1.value,
                reason=ReviewReason.UID_LOW_CONFIDENCE.value,
                message=f"Account UID manually confirmed as {session.uid_manual}",
                field_name="uid",
                confidence=1.0,
                machine_value=session.uid,
                candidates=session.uid_candidates,
                resolution=ReviewResolution(
                    action="set_uid",
                    resolved_by="manual",
                    value=session.uid_manual,
                    notes=f"Manually set UID to {session.uid_manual}",
                ),
            )
        elif session.uid_review_required or (
            session.uid_candidates and (
                session.uid is None or session.uid_confidence < self.ocr_accept_threshold
            )
        ):
            # Check if there is an explicit conflict among candidates
            distinct_uids = {c.get("uid") for c in session.uid_candidates if c.get("uid")}
            has_conflict = len(distinct_uids) > 1

            prio = ReviewPriority.P1.value if has_conflict else ReviewPriority.P2.value
            r_code = ReviewReason.UID_CONFLICT.value if has_conflict else ReviewReason.UID_LOW_CONFIDENCE.value

            fp = compute_machine_fingerprint(
                subsystem_version=session.ocr_version,
                value=str(session.uid),
                confidence=session.uid_confidence,
                reason=r_code,
                extra_token=f"{len(session.uid_candidates)}:{sorted(distinct_uids)}",
            )

            msg = f"Account UID requires review: {session.uid} (conf={session.uid_confidence:.2f})"
            if has_conflict:
                msg += f", candidate conflict across {len(distinct_uids)} values: {list(distinct_uids)[:3]}"

            generated_items[uid_id] = ReviewItem(
                id=uid_id,
                subsystem=ReviewSubsystem.UID.value,
                status=ReviewStatus.OPEN.value,
                priority=prio,
                reason=r_code,
                message=msg,
                field_name="uid",
                confidence=session.uid_confidence,
                machine_value=session.uid,
                candidates=session.uid_candidates,
                metadata={
                    "candidates_count": len(session.uid_candidates),
                    "distinct_uids": list(distinct_uids),
                },
                fingerprint=fp,
            )

        # ----------------------------------------------------------------------
        # 6. Reconcile with Existing Review State & Staleness Detection
        # ----------------------------------------------------------------------
        existing_items = session.review_items
        final_items: dict[str, ReviewItem] = {}

        for item_id, new_item in generated_items.items():
            if item_id in existing_items:
                old_item = existing_items[item_id]
                new_item.created_at = old_item.created_at

                # If previously resolved manually via specific override
                if old_item.status == ReviewStatus.RESOLVED_MANUAL.value:
                    if old_item.resolution and old_item.resolution.action != "accept_machine":
                        # Explicit manual overrides are authoritative!
                        new_item.status = ReviewStatus.RESOLVED_MANUAL.value
                        new_item.resolution = old_item.resolution
                    elif old_item.resolution and old_item.resolution.action == "accept_machine":
                        # User accepted machine value: check staleness!
                        if old_item.resolution.fingerprint == new_item.fingerprint:
                            # Unchanged machine state -> stays accepted
                            new_item.status = ReviewStatus.RESOLVED_MANUAL.value
                            new_item.resolution = old_item.resolution
                        else:
                            # Underlying machine state materially changed! Reopen.
                            new_item.status = ReviewStatus.OPEN.value
                            new_item.metadata["staleness_notice"] = (
                                "Previous machine acceptance became stale due to machine value/confidence change."
                            )
                elif old_item.status in {ReviewStatus.REJECTED.value, ReviewStatus.SKIPPED.value}:
                    new_item.status = old_item.status
                    new_item.resolution = old_item.resolution

            final_items[item_id] = new_item

        # ----------------------------------------------------------------------
        # 7. Deterministic Sorting & Ordering
        # ----------------------------------------------------------------------
        priority_rank = {
            ReviewPriority.P0.value: 0,
            ReviewPriority.P1.value: 1,
            ReviewPriority.P2.value: 2,
            ReviewPriority.P3.value: 3,
        }
        subsystem_rank = {
            ReviewSubsystem.CLASSIFICATION.value: 0,
            ReviewSubsystem.DETECTION.value: 1,
            ReviewSubsystem.ASSET_QUALITY.value: 2,
            ReviewSubsystem.OCR_GUN.value: 3,
            ReviewSubsystem.UID.value: 4,
        }

        def _sort_key(item: ReviewItem) -> tuple:
            p_val = priority_rank.get(item.priority, 9)
            sub_val = subsystem_rank.get(item.subsystem, 9)
            src_idx = source_index_map.get(item.source_id or "", 9999)
            f_name = item.field_name or ""
            return (p_val, sub_val, src_idx, f_name, item.id)

        sorted_items = sorted(final_items.values(), key=_sort_key)
        for idx, item in enumerate(sorted_items):
            item.order_index = idx

        # Persist updated items onto session
        session.review_items = {it.id: it for it in sorted_items}
        session.touch()

        return sorted_items
