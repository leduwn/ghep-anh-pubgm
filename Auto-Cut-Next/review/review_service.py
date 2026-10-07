"""Review service providing manual resolutions, downstream invalidation, and audit logging."""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from core.constants import (
    Category,
    Decision,
    ReviewSubsystem,
    ReviewStatus,
    ReviewPriority,
    ReviewReason,
)
from core.models import AccountSession, GunMetadata
from core.session import WorkspaceManager
from .models import (
    ReviewItem,
    ReviewResolution,
    ReviewAction,
    make_classification_review_id,
    make_detection_review_id,
    make_asset_quality_review_id,
    make_ocr_review_id,
    make_uid_review_id,
)
from .review_builder import ReviewQueueBuilder

logger = logging.getLogger("auto_cut.review.service")


class ReviewService:
    """Manages manual resolutions, downstream invalidation, and audit trails."""

    def __init__(
        self,
        session: AccountSession,
        workspace: WorkspaceManager,
        pipeline: Optional[Any] = None,
    ):
        self.session = session
        self.workspace = workspace
        self.pipeline = pipeline
        self.builder = ReviewQueueBuilder()

    def get_item(self, item_id: str) -> Optional[ReviewItem]:
        """Retrieves a review item by deterministic ID."""
        return self.session.review_items.get(item_id)

    def list_items(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        subsystem: Optional[str] = None,
    ) -> list[ReviewItem]:
        """Lists review items matching optional filters, in deterministic order."""
        items = sorted(self.session.review_items.values(), key=lambda it: it.order_index)
        if status is not None:
            items = [it for it in items if it.status == status]
        if priority is not None:
            items = [it for it in items if it.priority == priority]
        if subsystem is not None:
            items = [it for it in items if it.subsystem == subsystem]
        return items

    def get_summary(self) -> dict[str, Any]:
        """Returns counts of review items grouped by status and priority."""
        total = len(self.session.review_items)
        open_cnt = sum(1 for it in self.session.review_items.values() if it.status == ReviewStatus.OPEN.value)
        manual_cnt = sum(1 for it in self.session.review_items.values() if it.status == ReviewStatus.RESOLVED_MANUAL.value)
        auto_cnt = sum(1 for it in self.session.review_items.values() if it.status == ReviewStatus.RESOLVED_AUTO.value)
        rejected_cnt = sum(1 for it in self.session.review_items.values() if it.status == ReviewStatus.REJECTED.value)
        skipped_cnt = sum(1 for it in self.session.review_items.values() if it.status == ReviewStatus.SKIPPED.value)

        p0_cnt = sum(1 for it in self.session.review_items.values() if it.priority == ReviewPriority.P0.value and it.status == ReviewStatus.OPEN.value)
        p1_cnt = sum(1 for it in self.session.review_items.values() if it.priority == ReviewPriority.P1.value and it.status == ReviewStatus.OPEN.value)
        p2_cnt = sum(1 for it in self.session.review_items.values() if it.priority == ReviewPriority.P2.value and it.status == ReviewStatus.OPEN.value)
        p3_cnt = sum(1 for it in self.session.review_items.values() if it.priority == ReviewPriority.P3.value and it.status == ReviewStatus.OPEN.value)

        return {
            "total": total,
            "open": open_cnt,
            "resolved_manual": manual_cnt,
            "resolved_auto": auto_cnt,
            "rejected": rejected_cnt,
            "skipped": skipped_cnt,
            "open_by_priority": {
                "P0": p0_cnt,
                "P1": p1_cnt,
                "P2": p2_cnt,
                "P3": p3_cnt,
            },
        }

    def accept_machine_value(self, item_id: str, notes: Optional[str] = None) -> ReviewItem:
        """Accepts the current machine output and binds the cryptographic fingerprint."""
        item = self.session.review_items.get(item_id)
        if item is None:
            raise KeyError(f"Review item '{item_id}' not found")

        old_val = item.resolution.value if item.resolution else None
        item.status = ReviewStatus.RESOLVED_MANUAL.value
        item.resolution = ReviewResolution(
            action="accept_machine",
            resolved_by="manual",
            value=item.machine_value,
            notes=notes or "Accepted machine recommendation",
            fingerprint=item.fingerprint,
        )
        item.touch()

        # Audit action
        action = ReviewAction(
            review_item_id=item_id,
            action="accept_machine",
            old_value=old_val,
            new_value=item.machine_value,
            notes=notes,
        )
        self.session.review_history.append(action)

        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Accepted machine value for review item '{item_id}'")
        return item

    def set_category(
        self,
        source_id: str,
        category: str,
        notes: Optional[str] = None,
    ) -> ReviewItem:
        """Manually overrides category, invalidates downstream detection/assets/OCR, and rebuilds queue."""
        src = self.session.sources.get(source_id)
        if src is None:
            raise KeyError(f"Source '{source_id}' not found")

        # Validate category
        valid_cats = {c.value for c in Category}
        cat_upper = category.upper()
        if cat_upper not in valid_cats:
            raise ValueError(f"Invalid category '{category}'. Must be one of: {sorted(valid_cats)}")

        old_cat = None
        if source_id in self.session.classifications:
            old_cat = self.session.classifications[source_id].category

        # 1. Update source manual category and classification
        setattr(src, "manual_category", cat_upper)
        if source_id in self.session.classifications:
            cl = self.session.classifications[source_id]
            cl.category = cat_upper
            cl.decision = Decision.AUTO_ACCEPT.value
            cl.confidence = 1.0
            cl.reasons = [f"Manually assigned category '{cat_upper}'"]
        else:
            from core.models import ClassificationResult
            self.session.classifications[source_id] = ClassificationResult(
                category=cat_upper,
                confidence=1.0,
                decision=Decision.AUTO_ACCEPT.value,
                reasons=[f"Manually assigned category '{cat_upper}'"],
            )

        # 2. Downstream invalidation: remove source detection and assets
        self.session.detections.pop(source_id, None)
        orphan_asset_ids = {a.id for a in self.session.assets if a.source_id == source_id}
        self.session.assets = [a for a in self.session.assets if a.source_id != source_id]

        # 3. Invalidate orphan OCR records
        for aid in orphan_asset_ids:
            self.session.ocr_results.pop(aid, None)

        # 4. Resolve classification review item
        item_id = make_classification_review_id(source_id)
        item = self.session.review_items.get(item_id)
        if item is None:
            item = ReviewItem(
                id=item_id,
                subsystem=ReviewSubsystem.CLASSIFICATION.value,
                source_id=source_id,
                category=cat_upper,
                field_name="category",
                confidence=1.0,
                machine_value=old_cat,
            )

        item.status = ReviewStatus.RESOLVED_MANUAL.value
        item.category = cat_upper
        item.resolution = ReviewResolution(
            action="set_category",
            resolved_by="manual",
            value=cat_upper,
            notes=notes or f"Manually assigned category '{cat_upper}'",
        )
        item.touch()
        self.session.review_items[item_id] = item

        # 5. Audit trail
        action = ReviewAction(
            review_item_id=item_id,
            action="set_category",
            old_value=old_cat,
            new_value=cat_upper,
            notes=notes,
        )
        self.session.review_history.append(action)

        # 6. Rebuild review queue to prune invalid detection/asset items and insert new ones
        self.builder.build_queue(self.session)
        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Overrode category for source '{source_id}' to '{cat_upper}', invalidated downstream assets")
        return self.session.review_items[item_id]

    def set_level(
        self,
        asset_id: str,
        level: int,
        notes: Optional[str] = None,
    ) -> ReviewItem:
        """Sets manual weapon level on Gun asset."""
        if not (1 <= int(level) <= 100):
            raise ValueError(f"Weapon level must be between 1 and 100, got {level}")

        target_asset = next((a for a in self.session.assets if a.id == asset_id), None)
        if target_asset is None:
            raise KeyError(f"Asset '{asset_id}' not found")

        if target_asset.gun_metadata is None:
            target_asset.gun_metadata = GunMetadata()

        old_level = target_asset.gun_metadata.effective_level
        target_asset.gun_metadata.level_manual = int(level)

        item_id = make_ocr_review_id(asset_id, "level")
        item = self.session.review_items.get(item_id)
        if item is None:
            item = ReviewItem(
                id=item_id,
                subsystem=ReviewSubsystem.OCR_GUN.value,
                source_id=target_asset.source_id,
                asset_id=asset_id,
                category=Category.GUN.value,
                field_name="level",
                machine_value=old_level,
            )

        item.status = ReviewStatus.RESOLVED_MANUAL.value
        item.resolution = ReviewResolution(
            action="set_level",
            resolved_by="manual",
            value=int(level),
            notes=notes or f"Manually set level to {level}",
        )
        item.touch()
        self.session.review_items[item_id] = item

        # Audit
        action = ReviewAction(
            review_item_id=item_id,
            action="set_level",
            old_value=old_level,
            new_value=int(level),
            notes=notes,
        )
        self.session.review_history.append(action)

        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Manually set level for asset '{asset_id}' to {level}")
        return item

    def set_name(
        self,
        asset_id: str,
        name: str,
        notes: Optional[str] = None,
    ) -> ReviewItem:
        """Sets manual weapon name on Gun asset."""
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Weapon name cannot be empty")

        target_asset = next((a for a in self.session.assets if a.id == asset_id), None)
        if target_asset is None:
            raise KeyError(f"Asset '{asset_id}' not found")

        if target_asset.gun_metadata is None:
            target_asset.gun_metadata = GunMetadata()

        old_name = target_asset.gun_metadata.effective_name
        target_asset.gun_metadata.name_manual = clean_name

        item_id = make_ocr_review_id(asset_id, "name")
        item = self.session.review_items.get(item_id)
        if item is None:
            item = ReviewItem(
                id=item_id,
                subsystem=ReviewSubsystem.OCR_GUN.value,
                source_id=target_asset.source_id,
                asset_id=asset_id,
                category=Category.GUN.value,
                field_name="name",
                machine_value=old_name,
            )

        item.status = ReviewStatus.RESOLVED_MANUAL.value
        item.resolution = ReviewResolution(
            action="set_name",
            resolved_by="manual",
            value=clean_name,
            notes=notes or f"Manually set name to '{clean_name}'",
        )
        item.touch()
        self.session.review_items[item_id] = item

        # Audit
        action = ReviewAction(
            review_item_id=item_id,
            action="set_name",
            old_value=old_name,
            new_value=clean_name,
            notes=notes,
        )
        self.session.review_history.append(action)

        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Manually set name for asset '{asset_id}' to '{clean_name}'")
        return item

    def set_counter(
        self,
        asset_id: str,
        counter: Union[int, str],
        notes: Optional[str] = None,
    ) -> ReviewItem:
        """Sets manual kill counter on Gun asset."""
        cnt_val = str(counter).strip()

        target_asset = next((a for a in self.session.assets if a.id == asset_id), None)
        if target_asset is None:
            raise KeyError(f"Asset '{asset_id}' not found")

        if target_asset.gun_metadata is None:
            target_asset.gun_metadata = GunMetadata()

        old_cnt = target_asset.gun_metadata.effective_counter
        target_asset.gun_metadata.counter_manual = cnt_val
        target_asset.gun_metadata.counter_present = True

        item_id = make_ocr_review_id(asset_id, "counter")
        item = self.session.review_items.get(item_id)
        if item is None:
            item = ReviewItem(
                id=item_id,
                subsystem=ReviewSubsystem.OCR_GUN.value,
                source_id=target_asset.source_id,
                asset_id=asset_id,
                category=Category.GUN.value,
                field_name="counter",
                machine_value=old_cnt,
            )

        item.status = ReviewStatus.RESOLVED_MANUAL.value
        item.resolution = ReviewResolution(
            action="set_counter",
            resolved_by="manual",
            value=cnt_val,
            notes=notes or f"Manually set counter to '{cnt_val}'",
        )
        item.touch()
        self.session.review_items[item_id] = item

        # Audit
        action = ReviewAction(
            review_item_id=item_id,
            action="set_counter",
            old_value=old_cnt,
            new_value=cnt_val,
            notes=notes,
        )
        self.session.review_history.append(action)

        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Manually set counter for asset '{asset_id}' to '{cnt_val}'")
        return item

    def clear_counter(
        self,
        asset_id: str,
        notes: Optional[str] = None,
    ) -> ReviewItem:
        """Clears counter requirement when kill counter badge is absent."""
        target_asset = next((a for a in self.session.assets if a.id == asset_id), None)
        if target_asset is None:
            raise KeyError(f"Asset '{asset_id}' not found")

        if target_asset.gun_metadata is None:
            target_asset.gun_metadata = GunMetadata()

        old_cnt = target_asset.gun_metadata.effective_counter
        target_asset.gun_metadata.counter_manual = None
        target_asset.gun_metadata.counter_present = False

        item_id = make_ocr_review_id(asset_id, "counter")
        item = self.session.review_items.get(item_id)
        if item is None:
            item = ReviewItem(
                id=item_id,
                subsystem=ReviewSubsystem.OCR_GUN.value,
                source_id=target_asset.source_id,
                asset_id=asset_id,
                category=Category.GUN.value,
                field_name="counter",
                machine_value=old_cnt,
            )

        item.status = ReviewStatus.RESOLVED_MANUAL.value
        item.resolution = ReviewResolution(
            action="clear_counter",
            resolved_by="manual",
            value=None,
            notes=notes or "Counter badge absent or cleared",
        )
        item.touch()
        self.session.review_items[item_id] = item

        # Audit
        action = ReviewAction(
            review_item_id=item_id,
            action="clear_counter",
            old_value=old_cnt,
            new_value=None,
            notes=notes,
        )
        self.session.review_history.append(action)

        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Cleared counter for asset '{asset_id}'")
        return item

    def set_uid(
        self,
        uid: str,
        notes: Optional[str] = None,
    ) -> ReviewItem:
        """Sets manual UID override (strictly 8-14 digits) surviving machine reruns."""
        clean_uid = str(uid).strip()
        if not (clean_uid.isdigit() and 8 <= len(clean_uid) <= 14):
            raise ValueError(f"Account UID must be 8-14 digits, got '{uid}'")

        old_uid = self.session.effective_uid
        self.session.uid_manual = clean_uid

        item_id = make_uid_review_id(self.session.account_id)
        item = self.session.review_items.get(item_id)
        if item is None:
            item = ReviewItem(
                id=item_id,
                subsystem=ReviewSubsystem.UID.value,
                field_name="uid",
                machine_value=old_uid,
            )

        item.status = ReviewStatus.RESOLVED_MANUAL.value
        item.resolution = ReviewResolution(
            action="set_uid",
            resolved_by="manual",
            value=clean_uid,
            notes=notes or f"Manually set UID to {clean_uid}",
        )
        item.touch()
        self.session.review_items[item_id] = item

        # Audit
        action = ReviewAction(
            review_item_id=item_id,
            action="set_uid",
            old_value=old_uid,
            new_value=clean_uid,
            notes=notes,
        )
        self.session.review_history.append(action)

        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Manually set account UID to '{clean_uid}'")
        return item

    def reject_item(
        self,
        item_id: str,
        notes: Optional[str] = None,
    ) -> ReviewItem:
        """Marks review item as rejected."""
        item = self.session.review_items.get(item_id)
        if item is None:
            raise KeyError(f"Review item '{item_id}' not found")

        item.status = ReviewStatus.REJECTED.value
        item.resolution = ReviewResolution(
            action="reject",
            resolved_by="manual",
            notes=notes or "Manually rejected item",
        )
        item.touch()

        # If item targets an asset, mark asset manual override
        if item.asset_id:
            asset = next((a for a in self.session.assets if a.id == item.asset_id), None)
            if asset:
                asset.manual_override = True

        action = ReviewAction(
            review_item_id=item_id,
            action="reject",
            old_value=item.machine_value,
            new_value="REJECTED",
            notes=notes,
        )
        self.session.review_history.append(action)

        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Rejected review item '{item_id}'")
        return item

    def skip_item(
        self,
        item_id: str,
        notes: Optional[str] = None,
    ) -> ReviewItem:
        """Marks review item as skipped."""
        item = self.session.review_items.get(item_id)
        if item is None:
            raise KeyError(f"Review item '{item_id}' not found")

        item.status = ReviewStatus.SKIPPED.value
        item.resolution = ReviewResolution(
            action="skip",
            resolved_by="manual",
            notes=notes or "Manually skipped item",
        )
        item.touch()

        action = ReviewAction(
            review_item_id=item_id,
            action="skip",
            old_value=item.machine_value,
            new_value="SKIPPED",
            notes=notes,
        )
        self.session.review_history.append(action)

        self.session.touch()
        self.workspace.save_session(self.session)
        logger.info(f"Skipped review item '{item_id}'")
        return item
