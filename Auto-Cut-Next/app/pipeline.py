"""Central pipeline orchestrator for Auto-Cut-Next."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np

from core.constants import (
    Stage,
    SourceStatus,
    Decision,
    Category,
    DetectionStatus,
    CLASSIFIER_VERSION,
    ROUTER_VERSION,
    MISC_GRID_VERSION,
)
from core.cache import DiskCache, CacheKeyGenerator
from core.ingest import ImageIngestor
from core.logging import StageLogger
from core.metrics import MetricsCollector
from core.models import AccountSession, SourceImage, ClassificationResult, DetectedAsset
from core.session import WorkspaceManager
from core.settings import AutoCutSettings
from detectors import (
    ClassificationContext,
    ScreenClassifier,
    DetectionContext,
    CardGeometryProfile,
    CardCandidate,
    GridDetectionResult,
    SpecializedDetectionResult,
    SourceDetectionResult,
    GenericDetector,
    CategoryRouter,
)


class AutoCutPipeline:
    """Coordinates ingestion, session management, and stage execution."""

    def __init__(
        self,
        settings: Optional[AutoCutSettings] = None,
        workspace: Optional[WorkspaceManager] = None,
        logger: Optional[StageLogger] = None,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.settings = settings if settings is not None else AutoCutSettings.load_default()
        self.workspace = workspace or WorkspaceManager(self.settings.workspace_dir)
        self.logger = logger or StageLogger(self.workspace.workspace_root / "logs")
        self.metrics = metrics or MetricsCollector()
        self.ingestor = ImageIngestor()
        self._disk_cache: Optional[DiskCache] = None

    @property
    def disk_cache(self) -> DiskCache:
        if self._disk_cache is None:
            self._disk_cache = DiskCache(self.workspace.workspace_root / "cache" / "detection")
        return self._disk_cache

    def get_or_create_session(self, account_id: str) -> AccountSession:
        """Retrieves existing session or initializes a new one."""
        if self.workspace.session_exists(account_id):
            session = self.workspace.load_session(account_id)
            self.logger.info(
                f"Resumed existing session with {len(session.sources)} sources",
                stage=Stage.INGEST,
                account=account_id,
                status="RESUME",
            )
            return session
        session = AccountSession(account_id=account_id)
        self.workspace.save_session(session)
        self.logger.info(
            f"Created new session for account '{account_id}'",
            stage=Stage.INGEST,
            account=account_id,
            status="INIT",
        )
        return session

    def ingest_folder(
        self,
        account_id: str,
        folder_path: Union[str, Path],
        force_reprocess: bool = False,
        recursive: bool = False,
    ) -> AccountSession:
        """Safely scans and ingests all images from a specific folder with sandbox enforcement."""
        folder = Path(folder_path).resolve()
        if not folder.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder}")

        sandboxed_ingestor = ImageIngestor(allowed_root=folder, thumb_max_dim=self.ingestor.thumb_max_dim)
        files = sandboxed_ingestor.scan_directory(folder, recursive=recursive, enforce_root=True)
        return self.ingest_sources(account_id, files, force_reprocess=force_reprocess, ingestor=sandboxed_ingestor)

    def ingest_sources(
        self,
        account_id: str,
        file_paths: list[Union[str, Path]],
        force_reprocess: bool = False,
        ingestor: Optional[ImageIngestor] = None,
    ) -> AccountSession:
        """Ingests files into account session with deduplication and thumbnails."""
        active_ingestor = ingestor or self.ingestor
        session = self.get_or_create_session(account_id)
        dirs = self.workspace.init_account_workspace(account_id)
        thumbs_dir = dirs["thumbs"]

        with self.metrics.timer("ingest"):
            for idx, raw_path in enumerate(file_paths, start=len(session.sources) + 1):
                path = Path(raw_path).resolve()
                t0 = time.perf_counter()

                self.metrics.sources_seen += 1
                source = active_ingestor.ingest_file(
                    path,
                    source_index=idx,
                    thumb_dir=thumbs_dir,
                )
                duration_ms = (time.perf_counter() - t0) * 1000.0

                if source.status == SourceStatus.SUCCESS.value:
                    is_existing = session.get_source_by_sha256(source.sha256) is not None
                    upserted, is_affected = session.upsert_source(source, force=force_reprocess)

                    if not is_affected:
                        self.metrics.sources_duplicates += 1
                        self.logger.info(
                            f"Skipped duplicate source '{path.name}' (matches {upserted.filename})",
                            stage=Stage.INGEST,
                            account=account_id,
                            source=path.name,
                            status="DUPLICATE",
                            duration_ms=duration_ms,
                        )
                    elif is_existing and force_reprocess:
                        self.metrics.sources_forced += 1
                        self.logger.info(
                            f"Force refreshed source {upserted.filename} (invalidated derived assets)",
                            stage=Stage.INGEST,
                            account=account_id,
                            source=path.name,
                            status="FORCED",
                            duration_ms=duration_ms,
                        )
                    else:
                        self.metrics.sources_added += 1
                        self.logger.info(
                            f"Ingested source {source.filename} ({source.width}x{source.height})",
                            stage=Stage.INGEST,
                            account=account_id,
                            source=path.name,
                            status="SUCCESS",
                            duration_ms=duration_ms,
                        )
                else:
                    self.metrics.sources_failed += 1
                    self.logger.warning(
                        f"Failed to ingest source '{path.name}': {source.error_message}",
                        stage=Stage.INGEST,
                        account=account_id,
                        source=path.name,
                        status="FAILED",
                        duration_ms=duration_ms,
                    )

        self.workspace.save_session(session)
        return session

    def classify_session(
        self,
        account_id: str,
        force: bool = False,
    ) -> AccountSession:
        """Runs screen classification engine on all successful sources for an account."""
        session = self.get_or_create_session(account_id)
        classifier = ScreenClassifier(
            accept_threshold=self.settings.classifier_accept_threshold,
            review_threshold=self.settings.classifier_review_threshold,
            ambiguity_margin=self.settings.classifier_ambiguity_margin,
        )
        debug_dir = None
        if self.settings.enable_debug:
            account_dirs = self.workspace.init_account_workspace(account_id)
            debug_dir = account_dirs["debug"] / "classification"
            debug_dir.mkdir(parents=True, exist_ok=True)

        disk_cache = DiskCache(self.workspace.workspace_root / "cache" / "classification")

        successful_sources = sorted(
            [s for s in session.sources.values() if s.status == SourceStatus.SUCCESS.value],
            key=lambda s: s.source_index,
        )

        last_checkpoint_time = time.perf_counter()
        sources_since_checkpoint = 0

        with self.metrics.timer("classify"):
            for source in successful_sources:
                self.metrics.classify_seen += 1
                source_path = Path(source.path)

                # Compatible session result reuse
                if not force and source.id in session.classifications:
                    existing_res = session.classifications[source.id]
                    if existing_res.detector_version == classifier.VERSION:
                        self.metrics.classify_cached += 1
                        self.metrics.sources_classified += 1
                        if existing_res.decision == Decision.AUTO_ACCEPT.value:
                            self.metrics.classify_auto += 1
                        elif existing_res.decision == Decision.REVIEW.value:
                            self.metrics.classify_review += 1
                        elif existing_res.decision == Decision.UNKNOWN.value:
                            self.metrics.classify_unknown += 1
                        elif existing_res.decision == Decision.ERROR.value:
                            self.metrics.classify_errors += 1
                        continue

                # Missing source file
                if not source_path.is_file():
                    err_msg = f"Source file missing: {source_path}"
                    result = ClassificationResult(
                        category=Category.OTHER.value,
                        confidence=0.0,
                        decision=Decision.ERROR.value,
                        reasons=[err_msg],
                        detector="screen_classifier",
                        detector_version=classifier.VERSION,
                        error_message=err_msg,
                    )
                    session.classifications[source.id] = result
                    session.touch()
                    self.metrics.classify_errors += 1
                    self.logger.error(
                        f"Missing source file: {source.filename}",
                        stage=Stage.CLASSIFY,
                        account=account_id,
                        source=source.filename,
                        status="ERROR",
                    )
                    continue

                # Disk cache lookup
                cache_key = CacheKeyGenerator.generate(
                    image_sha256=source.sha256,
                    crop_rect=None,
                    subsystem_version=classifier.VERSION,
                    route=f"classify:a{self.settings.classifier_accept_threshold}:r{self.settings.classifier_review_threshold}:m{self.settings.classifier_ambiguity_margin}",
                )

                cached_data = disk_cache.get(cache_key) if not force else None
                if cached_data is not None:
                    result = ClassificationResult.from_dict(cached_data)
                    session.classifications[source.id] = result
                    session.touch()
                    self.metrics.classify_cached += 1
                    self.metrics.sources_classified += 1
                    if result.decision == Decision.AUTO_ACCEPT.value:
                        self.metrics.classify_auto += 1
                    elif result.decision == Decision.REVIEW.value:
                        self.metrics.classify_review += 1
                    elif result.decision == Decision.UNKNOWN.value:
                        self.metrics.classify_unknown += 1
                    continue
                # Decode image safely
                t_decode_0 = time.perf_counter()
                try:
                    img_bytes = source_path.read_bytes()
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception as exc:
                    img_bgr = None
                    decode_err = str(exc)
                else:
                    decode_err = "Decode returned None" if img_bgr is None else ""

                t_decode_ms = (time.perf_counter() - t_decode_0) * 1000.0

                if img_bgr is None or img_bgr.size == 0:
                    err_msg = f"Failed to decode source image: {decode_err}"
                    result = ClassificationResult(
                        category=Category.OTHER.value,
                        confidence=0.0,
                        decision=Decision.ERROR.value,
                        reasons=[err_msg],
                        detector="screen_classifier",
                        detector_version=classifier.VERSION,
                        duration_ms=t_decode_ms,
                        error_message=err_msg,
                    )
                    session.classifications[source.id] = result
                    session.touch()
                    self.metrics.classify_errors += 1
                    self.logger.error(
                        f"Corrupt/undecodable source image: {source.filename}",
                        stage=Stage.CLASSIFY,
                        account=account_id,
                        source=source.filename,
                        status="ERROR",
                    )
                    continue

                # Context & Classification
                ctx = ClassificationContext(
                    img_bgr,
                    max_scan_dim=self.settings.classifier_scan_max_dimension,
                    source=source,
                )
                try:
                    result = classifier.classify(ctx)
                except Exception as exc:
                    err_msg = f"Classification exception: {exc}"
                    result = ClassificationResult(
                        category=Category.OTHER.value,
                        confidence=0.0,
                        decision=Decision.ERROR.value,
                        reasons=[err_msg],
                        detector="screen_classifier",
                        detector_version=classifier.VERSION,
                        error_message=err_msg,
                    )
                    self.metrics.classify_errors += 1
                    self.logger.error(
                        f"Classification failure on {source.filename}: {exc}",
                        stage=Stage.CLASSIFY,
                        account=account_id,
                        source=source.filename,
                        status="ERROR",
                    )
                finally:
                    ctx.close()

                if result.decision != Decision.ERROR.value:
                    try:
                        disk_cache.put(cache_key, result.to_dict())
                    except Exception as exc:
                        logger.warning(f"Failed to cache classification for {source.id}: {exc}")
                        self.metrics.cache_write_errors += 1

                if debug_dir:
                    diag_path = debug_dir / f"{source.id}.json"
                    try:
                        with open(diag_path, "w", encoding="utf-8") as f:
                            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass

                session.classifications[source.id] = result
                session.touch()

                self.metrics.classify_processed += 1
                self.metrics.sources_classified += 1
                if result.decision == Decision.AUTO_ACCEPT.value:
                    self.metrics.classify_auto += 1
                elif result.decision == Decision.REVIEW.value:
                    self.metrics.classify_review += 1
                elif result.decision == Decision.UNKNOWN.value:
                    self.metrics.classify_unknown += 1

                alt_desc = f", alt={result.alternatives[0]['category']} ({result.alternatives[0]['score']})" if (result.decision == Decision.REVIEW.value and result.alternatives) else ""
                self.logger.info(
                    f"category={result.category} confidence={result.confidence:.2f} decision={result.decision}{alt_desc}",
                    stage=Stage.CLASSIFY,
                    account=account_id,
                    source=source.filename,
                    status=result.decision,
                    duration_ms=result.duration_ms,
                )

                sources_since_checkpoint += 1
                now = time.perf_counter()
                if sources_since_checkpoint >= 10 or (now - last_checkpoint_time) >= 2.0:
                    self.workspace.save_session(session)
                    last_checkpoint_time = now
                    sources_since_checkpoint = 0

        self.workspace.save_session(session)
        return session


    def detect_session(
        self,
        account_id: str,
        force: bool = False,
        profile: Optional[CardGeometryProfile] = None,
    ) -> AccountSession:
        """Executes generic grid detector and card quality pipeline on eligible classified sources."""
        session = self.get_or_create_session(account_id)
        detector = GenericDetector(
            profile=profile,
            lock_threshold=self.settings.lock_threshold,
            empty_content_threshold=self.settings.empty_content_threshold,
            duplicate_mae_threshold=self.settings.duplicate_mae_threshold,
            duplicate_phash_max_distance=self.settings.duplicate_phash_max_distance,
            detector_confidence_threshold=self.settings.detector_confidence_threshold,
        )

        disk_cache = self.disk_cache

        router = CategoryRouter(
            quality_evaluator=detector.quality_evaluator,
            detector_confidence_threshold=self.settings.detector_confidence_threshold,
        )

        eligible_categories = {
            Category.GUN.value,
            Category.VEHICLE.value,
            Category.OUTFIT.value,
            Category.ITEM_SET.value,
            Category.HELMET.value,
            Category.BACKPACK.value,
            Category.MASK.value,
            Category.GRENADE.value,
            Category.PARACHUTE.value,
            Category.EMOTE.value,
            Category.MISC.value,
        }
        deferred_categories: set[str] = set()

        successful_sources = sorted(
            [s for s in session.sources.values() if s.status == SourceStatus.SUCCESS.value],
            key=lambda s: s.source_index,
        )

        source_indices = {s.id: s.source_index for s in successful_sources}
        tile_crops: dict[str, np.ndarray] = {}

        last_checkpoint_time = time.perf_counter()
        sources_since_checkpoint = 0

        with self.metrics.timer("detect"):
            for source in successful_sources:
                self.metrics.detect_sources_seen += 1
                source_path = Path(source.path)

                # Check classification existence and gating
                class_res = session.classifications.get(source.id)
                if (
                    class_res is None
                    or class_res.decision in {Decision.UNKNOWN.value, Decision.ERROR.value}
                    or class_res.category == Category.OTHER.value
                    or class_res.category not in eligible_categories
                ):
                    session.invalidate_detection_assets_for_source(source.id)
                    session.detections.pop(source.id, None)
                    session.touch()
                    continue

                # Category gating: specialized categories are deferred to M4
                if class_res.category in deferred_categories:
                    self.metrics.detect_sources_deferred += 1
                    session.invalidate_detection_assets_for_source(source.id)
                    session.detections[source.id] = SourceDetectionResult(
                        source_id=source.id,
                        status=DetectionStatus.DEFERRED.value,
                        detector="generic_grid_detector",
                        detector_version=MISC_GRID_VERSION,
                        reasons=["Specialized detector required (deferred to M4)"],
                    )
                    session.touch()
                    continue

                # Check stale classification version
                if class_res.detector_version != CLASSIFIER_VERSION:
                    session.detections[source.id] = SourceDetectionResult(
                        source_id=source.id,
                        status=DetectionStatus.ERROR.value,
                        detector="generic_grid_detector",
                        detector_version=MISC_GRID_VERSION,
                        reasons=["Classification version stale; reclassification required"],
                        error_message="Classification version stale",
                    )
                    session.touch()
                    self.metrics.detect_sources_errors += 1
                    continue

                # Check file existence
                if not source_path.is_file():
                    err_msg = f"Source file missing: {source_path}"
                    session.detections[source.id] = SourceDetectionResult(
                        source_id=source.id,
                        status=DetectionStatus.ERROR.value,
                        detector="generic_grid_detector",
                        detector_version=MISC_GRID_VERSION,
                        reasons=[err_msg],
                        error_message=err_msg,
                    )
                    session.touch()
                    self.metrics.detect_sources_errors += 1
                    self.logger.error(
                        f"Missing source file during detection: {source.filename}",
                        stage=Stage.DETECT,
                        account=account_id,
                        source=source.filename,
                        status="ERROR",
                    )
                    continue
                # Resolve detector metadata for category and composite disk cache key
                det_instance, det_name, det_ver = router.get_detector_for_category(class_res.category)
                route_token = (
                    f"router:{ROUTER_VERSION}:"
                    f"primary:{det_name}@{det_ver}:"
                    f"fallback:generic_grid@{MISC_GRID_VERSION}:"
                    f"cat:{class_res.category}:"
                    f"conf{self.settings.detector_confidence_threshold:.2f}:"
                    f"l{self.settings.lock_threshold:.2f}:"
                    f"e{self.settings.empty_content_threshold:.2f}"
                )
                cache_key = CacheKeyGenerator.generate(
                    image_sha256=source.sha256,
                    crop_rect=None,
                    subsystem_version=ROUTER_VERSION,
                    route=route_token,
                )

                spec_res: Optional[SpecializedDetectionResult] = None
                cached_data = disk_cache.get(cache_key) if not force else None
                if cached_data is not None:
                    try:
                        spec_res = SpecializedDetectionResult.from_dict(cached_data)
                        self.metrics.detect_sources_cached += 1
                    except Exception:
                        spec_res = None

                # Image decode & context execution if not retrieved from cache
                t_detect_0 = time.perf_counter()
                context: Optional[DetectionContext] = None
                try:
                    img_bytes = source_path.read_bytes()
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception as exc:
                    img_bgr = None
                    decode_err = str(exc)
                else:
                    decode_err = "Decode returned None" if img_bgr is None else ""

                if img_bgr is None or img_bgr.size == 0:
                    err_msg = f"Failed to decode source image: {decode_err}"
                    session.detections[source.id] = SourceDetectionResult(
                        source_id=source.id,
                        status=DetectionStatus.ERROR.value,
                        detector=det_name,
                        detector_version=det_ver,
                        primary_detector=det_name,
                        reasons=[err_msg],
                        error_message=err_msg,
                    )
                    session.touch()
                    self.metrics.detect_sources_errors += 1
                    continue

                context = DetectionContext(
                    img_bgr,
                    source_id=source.id,
                    source_sha256=source.sha256,
                    max_scan_dim=self.settings.classifier_scan_max_dimension,
                    source=source,
                )

                from_cache = spec_res is not None
                if spec_res is None:
                    spec_res = router.route(context, classification=class_res, settings=self.settings)
                    self.metrics.detect_sources_processed += 1
                    # Persist candidates to disk cache
                    try:
                        disk_cache.put(cache_key, spec_res.to_dict())
                    except Exception as exc:
                        self.logger.warning(f"Failed to cache detection for {source.id}: {exc}")
                        self.metrics.cache_write_errors += 1

                # Update specialized & fallback metrics (only for actual executions, not cache hits)
                if not from_cache:
                    if spec_res.metadata.get("specialized_attempted", False):
                        self.metrics.specialized_attempted += 1
                        if spec_res.metadata.get("specialized_success", False):
                            self.metrics.specialized_success += 1

                    if spec_res.metadata.get("fallback_attempted", False):
                        self.metrics.fallback_attempted += 1
                        if spec_res.metadata.get("fallback_success", False):
                            self.metrics.fallback_success += 1

                    if spec_res.metadata.get("fallback_used", False):
                        self.metrics.fallback_selected += 1

                cat_val = class_res.category.upper()
                if cat_val == Category.GUN.value:
                    self.metrics.gun_detected += 1
                elif cat_val == Category.VEHICLE.value:
                    self.metrics.vehicle_detected += 1
                elif cat_val == Category.OUTFIT.value:
                    self.metrics.outfit_detected += 1
                elif cat_val in (Category.HELMET.value, Category.BACKPACK.value, Category.MASK.value):
                    self.metrics.equipment_detected += 1
                elif cat_val in (Category.GRENADE.value, Category.PARACHUTE.value, Category.EMOTE.value):
                    self.metrics.accessory_detected += 1
                elif cat_val in (Category.ITEM_SET.value, Category.MISC.value):
                    self.metrics.inventory_detected += 1

                if spec_res.detected:
                    assets = router.create_assets_from_result(
                        spec_res,
                        context,
                        category=class_res.category,
                        source_review_required=(class_res.decision == Decision.REVIEW.value),
                    )

                    # Invalidate only previously detected assets for this source
                    session.invalidate_detection_assets_for_source(source.id)
                    for a in assets:
                        session.add_asset(a)
                        tile_crops[a.id] = context.crop_original(a.crop_rect)

                    self.metrics.candidates_found += len(spec_res.candidates)
                    self.metrics.assets_created += len(assets)
                    self.metrics.locked_found += sum(1 for a in assets if a.locked)
                    self.metrics.empty_found += sum(1 for a in assets if a.empty)
                    self.metrics.partial_found += sum(1 for a in assets if a.partial)
                    self.metrics.detector_review_required += sum(1 for a in assets if a.review_required)

                    active_cnt = sum(1 for a in assets if not (a.locked or a.empty or a.partial or a.duplicate))
                    rev_cnt = sum(1 for a in assets if a.review_required)

                    is_low_conf = spec_res.confidence < self.settings.detector_confidence_threshold
                    det_status = DetectionStatus.REVIEW.value if (rev_cnt > 0 or is_low_conf) else DetectionStatus.SUCCESS.value
                    det_reasons = list(spec_res.reasons)
                    if is_low_conf:
                        det_reasons.append(f"Confidence {spec_res.confidence:.2f} below threshold {self.settings.detector_confidence_threshold:.2f}")

                    session.detections[source.id] = SourceDetectionResult(
                        source_id=source.id,
                        status=det_status,
                        detector=spec_res.detector_name,
                        detector_version=spec_res.detector_version,
                        primary_detector=spec_res.metadata.get("primary_detector", spec_res.detector_name),
                        fallback_detector=spec_res.metadata.get("fallback_detector"),
                        fallback_attempted=bool(spec_res.metadata.get("fallback_attempted", False)),
                        fallback_used=bool(spec_res.metadata.get("fallback_used", False)),
                        specialized_confidence=float(spec_res.metadata.get("specialized_confidence", spec_res.confidence)),
                        fallback_confidence=float(spec_res.metadata.get("fallback_confidence", 0.0)),
                        card_count=len(assets),
                        active_count=active_cnt,
                        locked_count=sum(1 for a in assets if a.locked),
                        empty_count=sum(1 for a in assets if a.empty),
                        partial_count=sum(1 for a in assets if a.partial),
                        review_count=rev_cnt,
                        reasons=det_reasons,
                        duration_ms=(time.perf_counter() - t_detect_0) * 1000.0,
                    )
                else:
                    self.metrics.detect_sources_no_grid += 1
                    session.invalidate_detection_assets_for_source(source.id)
                    session.detections[source.id] = SourceDetectionResult(
                        source_id=source.id,
                        status=DetectionStatus.NO_GRID.value,
                        detector=spec_res.detector_name,
                        detector_version=spec_res.detector_version,
                        primary_detector=spec_res.metadata.get("primary_detector", spec_res.detector_name),
                        fallback_detector=spec_res.metadata.get("fallback_detector"),
                        fallback_attempted=bool(spec_res.metadata.get("fallback_attempted", False)),
                        fallback_used=bool(spec_res.metadata.get("fallback_used", False)),
                        specialized_confidence=float(spec_res.metadata.get("specialized_confidence", 0.0)),
                        fallback_confidence=float(spec_res.metadata.get("fallback_confidence", 0.0)),
                        card_count=0,
                        active_count=0,
                        reasons=spec_res.reasons or ["No cards detected by specialized detector or fallback"],
                        duration_ms=(time.perf_counter() - t_detect_0) * 1000.0,
                    )

                session.touch()
                if context:
                    context.close()

                # Structured log per source
                det_res = session.detections[source.id]
                self.logger.info(
                    f"detector={spec_res.detector_name} cards={det_res.card_count} "
                    f"active={det_res.active_count} locked={det_res.locked_count} "
                    f"empty={det_res.empty_count} partial={det_res.partial_count}",
                    stage=Stage.DETECT,
                    account=account_id,
                    source=source.filename,
                    status=det_res.status,
                    duration_ms=det_res.duration_ms,
                )

                sources_since_checkpoint += 1
                now = time.perf_counter()
                if sources_since_checkpoint >= 10 or (now - last_checkpoint_time) >= 2.0:
                    self.workspace.save_session(session)
                    last_checkpoint_time = now
                    sources_since_checkpoint = 0

            # Account-level perceptual deduplication
            # Group missing tiles by source_id so each source image is decoded at most ONCE
            missing_by_source: dict[str, list[DetectedAsset]] = {}
            for asset in session.assets:
                if asset.id not in tile_crops:
                    missing_by_source.setdefault(asset.source_id, []).append(asset)

            from core.ingest import read_image_cv2
            for src_id, assets_for_src in missing_by_source.items():
                src = session.sources.get(src_id)
                if src and Path(src.path).is_file():
                    s_bgr = read_image_cv2(src.path)
                    if s_bgr is not None:
                        self.metrics.source_decodes += 1
                        sh, sw = s_bgr.shape[:2]
                        for a in assets_for_src:
                            c = a.crop_rect.clamp(sw, sh)
                            tile_crops[a.id] = s_bgr[c.y:c.bottom, c.x:c.right]
                        del s_bgr  # Release memory immediately

            updated_assets, dups = detector.deduplicator.deduplicate_session_assets(
                session.assets,
                source_tiles=tile_crops,
                source_indices=source_indices,
            )
            session.assets = updated_assets
            self.metrics.duplicates_found = dups
            self.metrics.assets_detected = len(session.assets)

            # Update detection record duplicate counts
            for src_id, det in session.detections.items():
                det.duplicate_count = sum(1 for a in session.assets if a.source_id == src_id and a.duplicate)
                det.active_count = sum(1 for a in session.assets if a.source_id == src_id and not (a.locked or a.empty or a.partial or a.duplicate))

        self.workspace.save_session(session)
        return session

    def ocr_session(
        self,
        account_id: str,
        force: bool = False,
        gun_only: bool = False,
        uid_only: bool = False,
        engine: Optional[Any] = None,
    ) -> AccountSession:
        """Executes OCR recognition for gun metadata and account UID.

        Guarantees lazy-loading of heavy OCR dependencies and single image decode per pass.
        """
        session = self.workspace.load_session(account_id)
        if not session.sources:
            self.logger.warning("No sources to process in session", stage=Stage.OCR, account=account_id)
            return session

        # Lazy imports of OCR subsystem
        from ocr.cache import OCRCache
        from ocr.engine import EasyOCREngine
        from ocr.scheduler import OCRScheduler

        created_engine = False
        if engine is None:
            created_engine = True
            models_dir = self.workspace.workspace_root / "models" / "easyocr"
            engine = EasyOCREngine(
                model_storage_dir=models_dir,
                device=self.settings.ocr_device,
                download_enabled=self.settings.ocr_download_enabled,
                on_gpu_fallback=lambda r: setattr(self.metrics, "ocr_gpu_fallbacks", self.metrics.ocr_gpu_fallbacks + 1),
            )

        ocr_cache = OCRCache(
            cache_dir=self.workspace.workspace_root / "cache" / "ocr",
            memory_capacity=self.settings.ocr_cache_size,
        )

        if force:
            session.invalidate_ocr(gun_only=gun_only, uid_only=uid_only)

        scheduler = OCRScheduler(
            engine=engine,
            cache=ocr_cache,
            settings=self.settings,
            metrics=self.metrics,
        )

        with self.metrics.timer("ocr"):
            session = scheduler.run_session_ocr(
                session=session,
                force=force,
                gun_only=gun_only,
                uid_only=uid_only,
            )

        self.workspace.save_session(session)

        if created_engine:
            engine.close()

        self.logger.info(
            f"OCR complete: guns={self.metrics.ocr_guns_processed} "
            f"success={self.metrics.ocr_guns_success} "
            f"uid={session.uid or 'N/A'} conf={session.uid_confidence:.2f}",
            stage=Stage.OCR,
            account=account_id,
            status="SUCCESS",
        )
        return session



