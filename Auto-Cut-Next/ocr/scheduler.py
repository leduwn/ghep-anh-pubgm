"""OCR task scheduler grouping execution by source ID to guarantee single image decode per pass."""

from __future__ import annotations

import gc
import logging
from collections import defaultdict
from typing import Optional

from core.constants import Category
from core.ingest import read_image_cv2
from core.metrics import MetricsCollector
from core.models import AccountSession, DetectedAsset
from core.settings import AutoCutSettings
from .cache import OCRCache
from .engine import OCREngine
from .gun_ocr import GunOCRExtractor
from .models import UIDCandidate
from .uid_ocr import UIDOCRExtractor, resolve_uid_consensus

logger = logging.getLogger("auto_cut.ocr.scheduler")


class OCRScheduler:
    """Orchestrates gun and UID OCR tasks across session sources with single-decode guarantee."""

    def __init__(
        self,
        engine: OCREngine,
        cache: Optional[OCRCache] = None,
        settings: Optional[AutoCutSettings] = None,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.engine = engine
        self.cache = cache
        self.settings = settings or AutoCutSettings()
        self.metrics = metrics or MetricsCollector()

        self.gun_extractor = GunOCRExtractor(
            engine=self.engine,
            cache=self.cache,
            accept_threshold=self.settings.ocr_accept_threshold,
            review_threshold=self.settings.ocr_review_threshold,
        )
        self.uid_extractor = UIDOCRExtractor(
            engine=self.engine,
            cache=self.cache,
        )

    def run_session_ocr(
        self,
        session: AccountSession,
        force: bool = False,
        gun_only: bool = False,
        uid_only: bool = False,
    ) -> AccountSession:
        """Executes OCR across all relevant sources in the session.

        Guarantees each source screenshot is decoded into memory at most once.
        """
        # 1. Identify target assets
        gun_assets_by_source: dict[str, list[DetectedAsset]] = defaultdict(list)
        if not uid_only:
            for asset in session.assets:
                if (
                    asset.category == Category.GUN.value
                    and not asset.locked
                    and not asset.empty
                    and not asset.partial
                    and not asset.duplicate
                ):
                    gun_assets_by_source[asset.source_id].append(asset)

        # 2. Determine which sources need UID scanning
        uid_sources: set[str] = set()
        if not gun_only:
            for s_id, src in session.sources.items():
                if src.status == "SUCCESS":
                    uid_sources.add(s_id)

        # 3. Form unified source task list
        all_target_sources = sorted(set(gun_assets_by_source.keys()) | uid_sources)
        self.metrics.ocr_sources_seen += len(all_target_sources)

        all_uid_candidates: list[UIDCandidate] = []
        if not force and session.uid_candidates and not uid_only and not gun_only:
            # If not forcing and candidates already exist, retain those from skipped sources
            pass

        # 4. Process each source with single decode
        for source_id in all_target_sources:
            source = session.sources.get(source_id)
            if source is None:
                continue

            guns_to_process = gun_assets_by_source.get(source_id, [])
            do_uid = source_id in uid_sources

            if not guns_to_process and not do_uid:
                continue

            # Single source image decode
            image = read_image_cv2(source.path)
            self.metrics.source_decodes += 1
            if image is None:
                logger.warning(f"Could not load image for source {source_id} at {source.path}")
                continue

            self.metrics.ocr_sources_processed += 1

            # A. Process gun assets for this source
            for asset in guns_to_process:
                self.metrics.ocr_guns_processed += 1
                try:
                    gun_res = self.gun_extractor.extract(
                        image=image,
                        source_sha256=source.sha256,
                        asset=asset,
                        force=force,
                    )
                    self.gun_extractor.apply_to_asset(asset, gun_res)

                    if gun_res.review_required:
                        self.metrics.ocr_guns_review += 1
                    else:
                        self.metrics.ocr_guns_success += 1

                    if gun_res.counter_present:
                        self.metrics.ocr_counters_found += 1
                        if gun_res.kill_counter is not None:
                            self.metrics.ocr_counters_verified += 1

                    # Persist raw observation into session.ocr_results
                    session.ocr_results[asset.id] = gun_res.to_dict()

                except Exception as exc:
                    logger.error(f"Failed gun OCR on asset {asset.id}: {exc}")
                    asset.review_required = True
                    asset.review_reasons.append(f"OCR processing exception: {exc}")

            # B. Process UID for this source
            if do_uid:
                try:
                    src_candidates = self.uid_extractor.extract_from_source(
                        image=image,
                        source_id=source_id,
                        source_sha256=source.sha256,
                        force=force,
                    )
                    all_uid_candidates.extend(src_candidates)
                except Exception as exc:
                    logger.error(f"Failed UID OCR on source {source_id}: {exc}")

            # Release decoded pixel buffer immediately
            del image
            gc.collect()

        # 5. UID multi-source consensus resolution
        if not gun_only:
            consensus = resolve_uid_consensus(
                candidates=all_uid_candidates,
                accept_threshold=self.settings.ocr_accept_threshold,
                review_threshold=self.settings.ocr_review_threshold,
            )
            session.uid = consensus.uid
            session.uid_confidence = consensus.confidence
            session.uid_review_required = consensus.review_required
            session.uid_candidates = [c.to_dict() for c in all_uid_candidates]

            if consensus.uid:
                self.metrics.ocr_uids_found += 1
            if consensus.has_conflict:
                self.metrics.ocr_uids_conflicts += 1

        # Record cache performance metrics
        if self.cache:
            cache_stats = self.cache.stats
            self.metrics.ocr_cache_hits += cache_stats.get("total_hits", 0)
            self.metrics.ocr_cache_misses += cache_stats.get("misses", 0)

        session.touch()
        return session
