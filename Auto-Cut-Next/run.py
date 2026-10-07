#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entry point for Auto-Cut-Next."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
NEXT_ROOT = Path(__file__).resolve().parent
if str(NEXT_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXT_ROOT))

from core.constants import APP_NAME, APP_VERSION
from core.settings import AutoCutSettings
from core.session import WorkspaceManager
from app.pipeline import AutoCutPipeline


def run_self_test() -> int:
    """Verifies environment, imports, models, settings, atomic session, cache, logger, classifier, and generic detector."""
    print("=" * 60)
    print(f"      {APP_NAME} v{APP_VERSION} - SELF-TEST (MILESTONE 6)")
    print("=" * 60)

    import tempfile

    # 1. Imports
    print("[1/10] Checking core imports...")
    try:
        from core.models import SourceImage, Rect, DetectedAsset, AccountSession
        from core.ingest import ImageIngestor
        from core.cache import LRUCache, DiskCache
        from core.logging import StageLogger
        print("      PASS: Core models and modules imported cleanly.")
    except Exception as exc:
        print(f"      FAIL: Core imports error: {exc}")
        return 1

    # 2. Settings validation & canonical default loading
    print("[2/10] Validating settings & canonical default...")
    try:
        settings = AutoCutSettings.load_default()
        settings.validate()
        assert settings.default_gun_columns >= 1
        assert settings.default_vehicle_rows >= 1
        assert settings.workspace_dir.is_absolute()
        print(f"      PASS: Settings validated (workspace={settings.workspace_dir.name}).")
    except Exception as exc:
        print(f"      FAIL: Settings validation error: {exc}")
        return 1

    # 3. Workspace atomic session write
    print("[3/10] Testing atomic workspace session write & schema check...")
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            ws = WorkspaceManager(temp_dir)
            session = AccountSession(account_id="self_test_acc")
            saved_path = ws.save_session(session)
            loaded = ws.load_session("self_test_acc")
            assert loaded.account_id == "self_test_acc"
            assert saved_path.is_file()
            assert not saved_path.with_suffix(".tmp").exists()
        print("      PASS: Atomic workspace session save/load verified.")
    except Exception as exc:
        print(f"      FAIL: Workspace write error: {exc}")
        return 1

    # 4. Ingestor & Sandbox enforcement
    print("[4/10] Checking ingestor & sandbox traversal protection...")
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            td = Path(temp_dir)
            sandbox = td / "sandbox"
            sandbox.mkdir()
            outside_file = td / "outside.png"
            outside_file.write_bytes(b"dummy")

            ingestor = ImageIngestor(allowed_root=sandbox)
            from core.exceptions import PathTraversalError
            try:
                ingestor.validate_path_safety(outside_file)
                print("      FAIL: Sandbox did not reject outside path.")
                return 1
            except PathTraversalError:
                pass
        print("      PASS: Ingestor sandbox protection verified.")
    except Exception as exc:
        print(f"      FAIL: Ingestor sandbox error: {exc}")
        return 1

    # 5. Atomic DiskCache & corruption recovery
    print("[5/10] Testing atomic disk cache & corruption recovery...")
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = DiskCache(temp_dir)
            cache.put("key1", {"value": 123})
            assert cache.get("key1") == {"value": 123}

            # Corrupt file
            target_path = cache._path_for_key("key1")
            target_path.write_bytes(b"INVALID_JSON_CORRUPT")
            assert cache.get("key1") is None
            assert cache.corruptions == 1
        print("      PASS: DiskCache atomic write and corruption recovery verified.")
    except Exception as exc:
        print(f"      FAIL: DiskCache error: {exc}")
        return 1

    # 6. Logger isolation & lifecycle
    print("[6/10] Testing logger instance isolation & cleanup...")
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            td = Path(temp_dir)
            logger_a = StageLogger(log_dir=td / "a", log_filename="test.log", console=False)
            logger_b = StageLogger(log_dir=td / "b", log_filename="test.log", console=False)

            logger_a.info("MSG_FOR_A_ONLY")
            logger_b.info("MSG_FOR_B_ONLY")

            logger_a.close()
            logger_b.close()

            content_a = (td / "a" / "test.log").read_text(encoding="utf-8")
            content_b = (td / "b" / "test.log").read_text(encoding="utf-8")

            assert "MSG_FOR_A_ONLY" in content_a
            assert "MSG_FOR_B_ONLY" not in content_a
            assert "MSG_FOR_B_ONLY" in content_b
            assert "MSG_FOR_A_ONLY" not in content_b
        print("      PASS: Logger instances cleanly isolated and closed.")
    except Exception as exc:
        print(f"      FAIL: Logger isolation error: {exc}")
        return 1

    # 7. Classifier smoke test
    print("[7/10] Testing screen classifier initialization & smoke categorization...")
    try:
        import numpy as np
        from core.constants import Category, Decision
        from detectors import ClassificationContext, ScreenClassifier
        dummy_img = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctx = ClassificationContext(dummy_img)
        classifier = ScreenClassifier()
        res = classifier.classify(ctx)
        ctx.close()
        assert res.category in {c.value for c in Category}
        assert res.decision in {d.value for d in Decision}
        assert res.detector_version == ScreenClassifier.VERSION
        print(f"      PASS: Classifier smoke test passed (category={res.category}, decision={res.decision}).")
    except Exception as exc:
        print(f"      FAIL: Classifier smoke test error: {exc}")
        return 1

    # 8. Generic grid detector smoke test
    print("[8/10] Testing generic grid detector & card quality smoke test...")
    try:
        import cv2
        import numpy as np
        from detectors import DetectionContext, GenericDetector
        # Create synthetic canvas with 2 dark tiles in a row
        img = np.zeros((400, 600, 3), dtype=np.uint8)
        img[:, :] = (180, 180, 180)
        for col in range(2):
            x = 50 + col * 150
            cv2.rectangle(img, (x, 50), (x + 120, 170), (40, 40, 40), -1)
            cv2.rectangle(img, (x + 20, 70), (x + 100, 150), (80, 20, 40), -1)
            cv2.circle(img, (x + 60, 110), 20, (240, 240, 240), -1)

        ctx = DetectionContext(img)
        detector = GenericDetector()
        grid_res = detector.detect_grid(ctx)
        ctx.close()
        assert grid_res.detected
        assert len(grid_res.candidates) >= 2
        print(f"      PASS: Generic grid detector smoke test passed (found {len(grid_res.candidates)} cards, grid={grid_res.rows}x{grid_res.columns}).")
    except Exception as exc:
        print(f"      FAIL: Generic detector smoke test error: {exc}")
        return 1

    # 9. Specialized detectors & CategoryRouter smoke test
    print("[9/10] Testing specialized PUBG detectors & CategoryRouter...")
    try:
        from core.models import ClassificationResult
        from detectors import CategoryRouter
        router = CategoryRouter()
        assert router.get_detector_for_category(Category.GUN.value)[1] == "gun_workshop_detector"
        assert router.get_detector_for_category(Category.VEHICLE.value)[1] == "vehicle_card_detector"
        assert router.get_detector_for_category(Category.OUTFIT.value)[1] == "outfit_character_detector"

        # Synthetic workshop test
        w, h = 1280, 720
        syn_img = np.zeros((h, w, 3), dtype=np.uint8)
        syn_img[:] = (20, 20, 20)
        card_x, card_y, card_w, card_h = int(0.60 * w), int(0.25 * h), int(0.25 * w), int(0.20 * h)
        cv2.rectangle(syn_img, (card_x, card_y), (card_x + card_w, card_y + card_h), (30, 140, 240), 8)
        cv2.rectangle(syn_img, (card_x + 8, card_y + 8), (card_x + card_w - 8, card_y + card_h - 8), (80, 80, 80), -1)

        ctx_spec = DetectionContext(syn_img)
        res_spec = router.route(ctx_spec, classification=ClassificationResult(Category.GUN.value, 0.95))
        assert res_spec.detected
        assert res_spec.detector_name == "gun_workshop_detector"
        assert res_spec.metadata.get("fallback_used") is False
        ctx_spec.close()

        # Shared-context fallback test on blank screen
        blank_img = np.zeros((h, w, 3), dtype=np.uint8)
        ctx_blank = DetectionContext(blank_img)
        res_fb = router.route(ctx_blank, classification=ClassificationResult(Category.GUN.value, 0.90))
        assert res_fb.metadata.get("fallback_attempted") is True
        assert res_fb.metadata.get("fallback_used") is False
        assert res_fb.detected is False
        assert res_fb.metadata.get("primary_detector") == "gun_workshop_detector"
        assert res_fb.metadata.get("fallback_detector") == "generic_grid_detector"
        ctx_blank.close()

        print("      PASS: Specialized detectors & CategoryRouter zero-redecode fallback verified.")
    except Exception as exc:
        print(f"      FAIL: Specialized detectors smoke test error: {exc}")
        return 1

    # 10. OCR Engine & Scheduler smoke test
    print("[10/10] Testing OCR parsers, fake engine, and multi-source consensus...")
    try:
        from ocr.models import OCRObservation
        from ocr.parsers import parse_gun_level, parse_gun_name, parse_uid
        from ocr.engine import FakeOCREngine
        from ocr.uid_ocr import resolve_uid_consensus

        # Test level parser with 3/3 -> 4
        level_obs = [OCRObservation(text="Tiến độ: 3/3", confidence=0.96)]
        lv, src, conf, _, _ = parse_gun_level(level_obs)
        assert lv == 4
        assert src == "progress"

        # Test canonical weapon parser
        name_obs = [OCRObservation(text="M416 Băng Giá", confidence=0.98)]
        w_name, name_conf, _, _ = parse_gun_name(name_obs)
        assert w_name == "M416"

        # Test UID parser & multi-source consensus
        uid_obs = [OCRObservation(text="UID: 5123456789", confidence=0.95)]
        cands = parse_uid(uid_obs, source_id="src_1")
        assert len(cands) == 1
        assert cands[0].uid == "5123456789"

        consensus = resolve_uid_consensus(cands)
        assert consensus.uid == "5123456789"
        assert consensus.confidence >= 0.95
        assert not consensus.has_conflict

        # Verify FakeOCREngine
        fake_engine = FakeOCREngine(default_observations=[OCRObservation(text="M416", confidence=1.0)])
        res = fake_engine.read_text(np.zeros((10, 10, 3), dtype=np.uint8))
        assert len(res) == 1
        assert res[0].text == "M416"
        print("      PASS: OCR parsers, FakeOCREngine, and UID consensus verified.")
    except Exception as exc:
        print(f"      FAIL: OCR smoke test error: {exc}")
        return 1

    # 11. Review Engine & Manual Resolution Workflow
    print("[11/11] Testing review queue builder, deterministic IDs, staleness, and manual resolution...")
    try:
        from core.models import AccountSession, SourceImage, ClassificationResult, DetectedAsset, Rect, GunMetadata
        from core.constants import ReviewSubsystem, ReviewStatus, ReviewPriority, ReviewReason, Decision
        from review.review_builder import ReviewQueueBuilder
        from review.review_service import ReviewService

        with tempfile.TemporaryDirectory() as temp_dir:
            ws = WorkspaceManager(temp_dir)
            session = AccountSession(account_id="self_test_review")

            # Add source and classification needing review
            src = SourceImage(id="src_1", filename="screen_1.png", path=temp_dir, sha256="abc123", source_index=0)
            session.sources[src.id] = src
            session.classifications[src.id] = ClassificationResult(
                category="GUN",
                confidence=0.55,
                decision=Decision.REVIEW.value,
                detector_version="2.0.0",
            )

            # Add Gun asset with low level confidence
            asset = DetectedAsset(
                id="asset_gun_1",
                source_id=src.id,
                category="GUN",
                crop_rect=Rect(10, 10, 100, 100),
                gun_metadata=GunMetadata(
                    weapon_name="M416",
                    name_confidence=0.95,
                    level=3,
                    level_confidence=0.45,
                    level_source="test",
                    counter_present=True,
                    kill_counter=None,
                    counter_confidence=0.0,
                ),
            )
            session.assets.append(asset)

            # Build review queue
            builder = ReviewQueueBuilder()
            items = builder.build_queue(session)
            assert len(items) >= 3  # classification, ocr level, ocr counter (badge present!)
            assert any(it.subsystem == ReviewSubsystem.CLASSIFICATION.value for it in items)
            assert any(it.subsystem == ReviewSubsystem.OCR_GUN.value and it.field_name == "level" for it in items)
            assert any(it.subsystem == ReviewSubsystem.OCR_GUN.value and it.field_name == "counter" for it in items)

            # Service manual resolution
            service = ReviewService(session=session, workspace=ws)
            # Manual override level
            res_lvl = service.set_level("asset_gun_1", 4, notes="Manually verified level 4")
            assert res_lvl.status == ReviewStatus.RESOLVED_MANUAL.value
            assert asset.gun_metadata.level_manual == 4
            assert asset.gun_metadata.effective_level == 4

            # Manual UID override
            res_uid = service.set_uid("5123456789", notes="Confirmed UID")
            assert res_uid.status == ReviewStatus.RESOLVED_MANUAL.value
            assert session.effective_uid == "5123456789"

            # Category override with downstream invalidation
            res_cat = service.set_category("src_1", "VEHICLE", notes="Actually vehicle")
            assert res_cat.status == ReviewStatus.RESOLVED_MANUAL.value
            assert len(session.assets) == 0  # Invalidated downstream gun asset!
            assert len(session.review_history) >= 3  # Audit actions recorded

            # Rebuild queue: gun asset OCR review items pruned
            rebuilt = builder.build_queue(session)
            assert not any(it.asset_id == "asset_gun_1" for it in rebuilt)

        print("      PASS: Review queue builder, manual resolutions, and downstream invalidation verified.")
    except Exception as exc:
        print(f"      FAIL: Review system self-test error: {exc}")
        return 1

    print("=" * 60)
    print("      ALL 11 SELF-TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - Next-Gen PUBG Mobile Asset Extraction & Compositing Suite"
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} v{APP_VERSION}")
    parser.add_argument("--self-test", action="store_true", help="Run diagnostic self-test")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: ingest
    ingest_p = subparsers.add_parser("ingest", help="Ingest screenshot folder into an account session")
    ingest_p.add_argument("account", help="Account identifier (letters, digits, dashes)")
    ingest_p.add_argument("folder", help="Path to screenshot folder")
    ingest_p.add_argument("--force", action="store_true", help="Force reprocess duplicate sources")

    # Command: classify
    classify_p = subparsers.add_parser("classify", help="Classify screenshot screens for an account")
    classify_p.add_argument("account", help="Account identifier")
    classify_p.add_argument("--force", action="store_true", help="Force reclassification of sources")
    classify_p.add_argument("--verbose", action="store_true", help="Verbose logging")
    classify_p.add_argument("--json", action="store_true", dest="json_output", help="Output summary as JSON")

    # Command: detect
    detect_p = subparsers.add_parser("detect", help="Run generic card grid detection on classified screens")
    detect_p.add_argument("account", help="Account identifier")
    detect_p.add_argument("--force", action="store_true", help="Force redetection of sources")
    detect_p.add_argument("--verbose", action="store_true", help="Verbose logging")
    detect_p.add_argument("--json", action="store_true", dest="json_output", help="Output summary as JSON")

    # Command: ocr
    ocr_p = subparsers.add_parser("ocr", help="Run OCR for weapon metadata and account UID")
    ocr_p.add_argument("account", help="Account identifier")
    ocr_p.add_argument("--force", action="store_true", help="Force re-OCR bypassing caches")
    ocr_p.add_argument("--gun-only", action="store_true", help="Only run weapon metadata OCR")
    ocr_p.add_argument("--uid-only", action="store_true", help="Only run UID recognition")
    ocr_p.add_argument("--verbose", action="store_true", help="Verbose logging")
    ocr_p.add_argument("--json", action="store_true", dest="json_output", help="Output summary as JSON")

    # Command: info
    info_p = subparsers.add_parser("info", help="Display account session summary")
    info_p.add_argument("account", help="Account identifier")

    # Command: review
    review_p = subparsers.add_parser("review", help="Unified review queue and manual correction workflow")
    review_sub = review_p.add_subparsers(dest="review_action", help="Review actions")

    # review build <account>
    r_build = review_sub.add_parser("build", help="Build or refresh review queue for account")
    r_build.add_argument("account", help="Account identifier")

    # review list <account> [--status ...] [--priority ...] [--subsystem ...] [--json]
    r_list = review_sub.add_parser("list", help="List review items for account")
    r_list.add_argument("account", help="Account identifier")
    r_list.add_argument("--status", choices=["OPEN", "RESOLVED_AUTO", "RESOLVED_MANUAL", "REJECTED", "SKIPPED", "STALE"], help="Filter by review status")
    r_list.add_argument("--priority", choices=["P0", "P1", "P2", "P3"], help="Filter by priority")
    r_list.add_argument("--subsystem", choices=["CLASSIFICATION", "DETECTION", "ASSET_QUALITY", "OCR_GUN", "UID"], help="Filter by subsystem")
    r_list.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # review show <account> <item_id> [--json]
    r_show = review_sub.add_parser("show", help="Show details for a specific review item")
    r_show.add_argument("account", help="Account identifier")
    r_show.add_argument("item_id", help="Review item ID")
    r_show.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # review accept <account> <item_id> [--notes ...]
    r_accept = review_sub.add_parser("accept", help="Accept machine recommendation for item")
    r_accept.add_argument("account", help="Account identifier")
    r_accept.add_argument("item_id", help="Review item ID")
    r_accept.add_argument("--notes", help="Optional resolution notes")

    # review set-category <account> <source_id> <category> [--notes ...]
    r_set_cat = review_sub.add_parser("set-category", help="Override classification category")
    r_set_cat.add_argument("account", help="Account identifier")
    r_set_cat.add_argument("source_id", help="Source image ID")
    r_set_cat.add_argument("category", help="Target category (GUN, VEHICLE, OUTFIT, etc.)")
    r_set_cat.add_argument("--notes", help="Optional resolution notes")

    # review set-level <account> <asset_id> <level> [--notes ...]
    r_set_lvl = review_sub.add_parser("set-level", help="Override weapon level on Gun asset")
    r_set_lvl.add_argument("account", help="Account identifier")
    r_set_lvl.add_argument("asset_id", help="Asset ID")
    r_set_lvl.add_argument("level", type=int, help="Weapon level (1-100)")
    r_set_lvl.add_argument("--notes", help="Optional resolution notes")

    # review set-name <account> <asset_id> <name> [--notes ...]
    r_set_nm = review_sub.add_parser("set-name", help="Override weapon name on Gun asset")
    r_set_nm.add_argument("account", help="Account identifier")
    r_set_nm.add_argument("asset_id", help="Asset ID")
    r_set_nm.add_argument("name", help="Canonical weapon name")
    r_set_nm.add_argument("--notes", help="Optional resolution notes")

    # review set-counter <account> <asset_id> <counter> [--notes ...]
    r_set_cnt = review_sub.add_parser("set-counter", help="Override kill counter on Gun asset")
    r_set_cnt.add_argument("account", help="Account identifier")
    r_set_cnt.add_argument("asset_id", help="Asset ID")
    r_set_cnt.add_argument("counter", help="Kill counter value")
    r_set_cnt.add_argument("--notes", help="Optional resolution notes")

    # review clear-counter <account> <asset_id> [--notes ...]
    r_clr_cnt = review_sub.add_parser("clear-counter", help="Clear counter requirement (badge absent)")
    r_clr_cnt.add_argument("account", help="Account identifier")
    r_clr_cnt.add_argument("asset_id", help="Asset ID")
    r_clr_cnt.add_argument("--notes", help="Optional resolution notes")

    # review set-uid <account> <uid> [--notes ...]
    r_set_uid = review_sub.add_parser("set-uid", help="Override account UID (8-14 digits)")
    r_set_uid.add_argument("account", help="Account identifier")
    r_set_uid.add_argument("uid", help="Account UID (8-14 digits)")
    r_set_uid.add_argument("--notes", help="Optional resolution notes")

    # review reject <account> <item_id> [--notes ...]
    r_rej = review_sub.add_parser("reject", help="Reject a review item")
    r_rej.add_argument("account", help="Account identifier")
    r_rej.add_argument("item_id", help="Review item ID")
    r_rej.add_argument("--notes", help="Optional resolution notes")

    # review skip <account> <item_id> [--notes ...]
    r_skip = review_sub.add_parser("skip", help="Skip a review item for now")
    r_skip.add_argument("account", help="Account identifier")
    r_skip.add_argument("item_id", help="Review item ID")
    r_skip.add_argument("--notes", help="Optional resolution notes")

    # review history <account> [--json]
    r_hist = review_sub.add_parser("history", help="Show review audit action history")
    r_hist.add_argument("account", help="Account identifier")
    r_hist.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # review summary <account> [--json]
    r_sum = review_sub.add_parser("summary", help="Show review queue statistics summary")
    r_sum.add_argument("account", help="Account identifier")
    r_sum.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if args.command == "ingest":
        pipeline = AutoCutPipeline()
        folder = Path(args.folder).resolve()
        if not folder.is_dir():
            print(f"Error: Directory not found: {folder}", file=sys.stderr)
            return 1
        print(f"[*] Scanning and ingesting from {folder.name}...")
        session = pipeline.ingest_folder(args.account, folder, force_reprocess=args.force)
        print(f"[+] Ingestion complete for '{args.account}'. Total sources in session: {len(session.sources)}")
        print(pipeline.metrics.summary())
        return 0

    if args.command == "classify":
        import json
        import time
        from core.constants import Category, Decision

        ws = WorkspaceManager()
        if not ws.session_exists(args.account):
            print(f"Error: No session found for account '{args.account}'. Run ingest first.", file=sys.stderr)
            return 1

        pipeline = AutoCutPipeline()
        t0 = time.perf_counter()
        session = pipeline.classify_session(args.account, force=args.force)
        elapsed = time.perf_counter() - t0

        # Tally categories
        cat_counts = {cat.value: 0 for cat in Category}
        decision_counts = {
            "AUTO": 0,
            "REVIEW": 0,
            "UNKNOWN": 0,
            "ERROR": 0,
        }

        for res in session.classifications.values():
            if res.category in cat_counts:
                cat_counts[res.category] += 1
            else:
                cat_counts["OTHER"] += 1

            if res.decision == Decision.AUTO_ACCEPT.value:
                decision_counts["AUTO"] += 1
            elif res.decision == Decision.REVIEW.value:
                decision_counts["REVIEW"] += 1
            elif res.decision == Decision.UNKNOWN.value:
                decision_counts["UNKNOWN"] += 1
            elif res.decision == Decision.ERROR.value:
                decision_counts["ERROR"] += 1

        if args.json_output:
            data = {
                "account": args.account,
                "sources": len(session.sources),
                "classified": len(session.classifications),
                "categories": cat_counts,
                "decisions": decision_counts,
                "cache_hits": pipeline.metrics.classify_cached,
                "time_seconds": round(elapsed, 2),
            }
            print(json.dumps(data, indent=2))
            return 0

        print(f"Account: {args.account}")
        print(f"Sources: {len(session.sources)}\n")
        for cat in Category:
            print(f"{cat.value:<12} {cat_counts.get(cat.value, 0):>3}")
        print()
        print(f"AUTO:       {decision_counts['AUTO']:>3}")
        print(f"REVIEW:     {decision_counts['REVIEW']:>3}")
        print(f"UNKNOWN:    {decision_counts['UNKNOWN']:>3}")
        print(f"ERROR:      {decision_counts['ERROR']:>3}")
        print()
        print(f"Cache hits: {pipeline.metrics.classify_cached}")
        print(f"Time: {elapsed:.2f} s")
        return 0

    if args.command == "detect":
        import json
        import time

        ws = WorkspaceManager()
        if not ws.session_exists(args.account):
            print(f"Error: No session found for account '{args.account}'. Run ingest and classify first.", file=sys.stderr)
            return 1

        pipeline = AutoCutPipeline()
        t0 = time.perf_counter()
        session = pipeline.detect_session(args.account, force=args.force)
        elapsed = time.perf_counter() - t0

        eligible_count = sum(1 for d in session.detections.values() if d.status != "DEFERRED")
        processed_count = pipeline.metrics.detect_sources_processed + pipeline.metrics.detect_sources_cached
        total_cards = len(session.assets)
        active_cards = sum(1 for a in session.assets if not (a.locked or a.empty or a.partial or a.duplicate))
        locked_cards = sum(1 for a in session.assets if a.locked)
        empty_cards = sum(1 for a in session.assets if a.empty)
        partial_cards = sum(1 for a in session.assets if a.partial)
        duplicate_cards = sum(1 for a in session.assets if a.duplicate)
        review_cards = sum(1 for a in session.assets if a.review_required)
        no_grid_count = sum(1 for d in session.detections.values() if d.status == "NO_GRID")
        error_count = sum(1 for d in session.detections.values() if d.status == "ERROR")

        if args.json_output:
            data = {
                "account": args.account,
                "sources_eligible": eligible_count,
                "processed": processed_count,
                "cards_found": total_cards,
                "active": active_cards,
                "locked": locked_cards,
                "empty": empty_cards,
                "partial": partial_cards,
                "duplicates": duplicate_cards,
                "review": review_cards,
                "no_grid": no_grid_count,
                "errors": error_count,
                "time_seconds": round(elapsed, 2),
            }
            print(json.dumps(data, indent=2))
            return 0

        print(f"Account: {args.account}\n")
        print(f"Sources eligible: {eligible_count}")
        print(f"Processed:        {processed_count}\n")
        print(f"Cards found:      {total_cards}")
        print(f"Active:           {active_cards}")
        print(f"Locked:           {locked_cards}")
        print(f"Empty:            {empty_cards}")
        print(f"Partial:          {partial_cards}")
        print(f"Duplicates:       {duplicate_cards}")
        print(f"Review:           {review_cards}\n")
        print(f"No grid:          {no_grid_count}")
        print(f"Errors:           {error_count}")
        return 0

    if args.command == "ocr":
        import json
        import time

        ws = WorkspaceManager()
        if not ws.session_exists(args.account):
            print(f"Error: No session found for account '{args.account}'. Run ingest, classify, and detect first.", file=sys.stderr)
            return 1

        pipeline = AutoCutPipeline()
        t0 = time.perf_counter()
        session = pipeline.ocr_session(
            args.account,
            force=args.force,
            gun_only=args.gun_only,
            uid_only=args.uid_only,
        )
        elapsed = time.perf_counter() - t0

        gun_count = sum(1 for a in session.assets if a.category == "GUN")
        guns_with_level = sum(1 for a in session.assets if a.category == "GUN" and a.gun_metadata and a.gun_metadata.level is not None)
        guns_with_name = sum(1 for a in session.assets if a.category == "GUN" and a.gun_metadata and a.gun_metadata.weapon_name is not None)
        guns_with_counter = sum(1 for a in session.assets if a.category == "GUN" and a.gun_metadata and a.gun_metadata.kill_counter is not None)
        gun_review = sum(1 for a in session.assets if a.category == "GUN" and a.review_required)

        if args.json_output:
            data = {
                "account": args.account,
                "gun_assets": gun_count,
                "guns_level_found": guns_with_level,
                "guns_name_found": guns_with_name,
                "guns_counter_found": guns_with_counter,
                "gun_review_required": gun_review,
                "uid": session.uid,
                "uid_confidence": session.uid_confidence,
                "uid_review_required": session.uid_review_required,
                "cache_hits": pipeline.metrics.ocr_cache_hits,
                "time_seconds": round(elapsed, 2),
            }
            print(json.dumps(data, indent=2))
            return 0

        print(f"Account: {args.account}\n")
        print(f"Guns processed:   {gun_count}")
        print(f"Levels parsed:    {guns_with_level}")
        print(f"Names parsed:     {guns_with_name}")
        print(f"Counters parsed:  {guns_with_counter}")
        print(f"Review required:  {gun_review}\n")
        print(f"UID:              {session.uid or 'N/A'}")
        print(f"UID Confidence:   {session.uid_confidence:.2f}")
        print(f"UID Review:       {session.uid_review_required}")
        print(f"OCR Cache Hits:   {pipeline.metrics.ocr_cache_hits}")
        print(f"Time:             {elapsed:.2f} s")
        return 0

    if args.command == "info":
        from core.constants import Decision
        ws = WorkspaceManager()
        if not ws.session_exists(args.account):
            print(f"Error: No session found for account '{args.account}'", file=sys.stderr)
            return 1
        session = ws.load_session(args.account)

        auto_cnt = sum(1 for c in session.classifications.values() if c.decision == Decision.AUTO_ACCEPT.value)
        rev_cnt = sum(1 for c in session.classifications.values() if c.decision == Decision.REVIEW.value)
        unk_cnt = sum(1 for c in session.classifications.values() if c.decision == Decision.UNKNOWN.value)
        err_cnt = sum(1 for c in session.classifications.values() if c.decision == Decision.ERROR.value)

        detected_cnt = len(session.detections)
        active_assets = sum(1 for a in session.assets if not (a.locked or a.empty or a.partial or a.duplicate))
        locked_assets = sum(1 for a in session.assets if a.locked)
        empty_assets = sum(1 for a in session.assets if a.empty)
        partial_assets = sum(1 for a in session.assets if a.partial)
        duplicate_assets = sum(1 for a in session.assets if a.duplicate)
        review_assets = sum(1 for a in session.assets if a.review_required)

        gun_count = sum(1 for a in session.assets if a.category == "GUN")
        guns_with_level = sum(1 for a in session.assets if a.category == "GUN" and a.gun_metadata and a.gun_metadata.level is not None)
        guns_with_counter = sum(1 for a in session.assets if a.category == "GUN" and a.gun_metadata and a.gun_metadata.kill_counter is not None)

        print(f"Account:    {session.account_id}")
        print(f"Version:    {session.version}")
        print(f"Sources:    {len(session.sources)}")
        print(f"Classified: {len(session.classifications)}")
        print(f"Detected:   {detected_cnt}")
        print()
        print(f"Assets total: {len(session.assets)}")
        print(f"Active:       {active_assets}")
        print(f"Locked:       {locked_assets}")
        print(f"Empty:        {empty_assets}")
        print(f"Partial:      {partial_assets}")
        print(f"Duplicate:    {duplicate_assets}")
        print(f"Review:       {review_assets}")
        print()
        print(f"Gun Assets:   {gun_count}")
        print(f"Guns Level:   {guns_with_level}")
        print(f"Guns Counter: {guns_with_counter}")
        print(f"UID:          {session.uid or 'N/A'} (conf={session.uid_confidence:.2f}, rev={session.uid_review_required})")
        print(f"Created:      {session.created_at}")
        print(f"Updated:      {session.updated_at}")
        return 0

    if args.command == "review":
        import json
        ws = WorkspaceManager()
        if not ws.session_exists(args.account):
            print(f"Error: No session found for account '{args.account}'", file=sys.stderr)
            return 1

        pipeline = AutoCutPipeline()
        service = pipeline.get_review_service(args.account)

        action = getattr(args, "review_action", None)
        if not action or action == "build":
            session = pipeline.build_review_queue(args.account)
            print(f"[+] Review queue built for '{args.account}'. Total items: {len(session.review_items)}")
            summary = service.get_summary()
            print(f"    Open: {summary['open']} (P0={summary['open_by_priority']['P0']}, P1={summary['open_by_priority']['P1']}, P2={summary['open_by_priority']['P2']}, P3={summary['open_by_priority']['P3']})")
            print(f"    Resolved Manual: {summary['resolved_manual']}")
            return 0

        if action == "list":
            items = service.list_items(status=args.status, priority=args.priority, subsystem=args.subsystem)
            if getattr(args, "json_output", False):
                print(json.dumps([it.to_dict() for it in items], indent=2))
                return 0
            print(f"Review Items for '{args.account}' ({len(items)} items):\n")
            print(f"{'IDX':<4} {'PRIO':<5} {'SUBSYSTEM':<15} {'STATUS':<15} {'REASON':<28} {'ID':<35}")
            print("-" * 110)
            for it in items:
                print(f"{it.order_index:<4} {it.priority:<5} {it.subsystem:<15} {it.status:<15} {it.reason:<28} {it.id:<35}")
            return 0

        if action == "show":
            item = service.get_item(args.item_id)
            if item is None:
                print(f"Error: Review item '{args.item_id}' not found", file=sys.stderr)
                return 1
            if getattr(args, "json_output", False):
                print(json.dumps(item.to_dict(), indent=2))
                return 0
            print(f"ID:        {item.id}")
            print(f"Subsystem: {item.subsystem}")
            print(f"Status:    {item.status}")
            print(f"Priority:  {item.priority}")
            print(f"Reason:    {item.reason}")
            print(f"Message:   {item.message}")
            if item.source_id:
                print(f"Source ID: {item.source_id}")
            if item.asset_id:
                print(f"Asset ID:  {item.asset_id}")
            if item.field_name:
                print(f"Field:     {item.field_name}")
            print(f"Machine:   {item.machine_value} (conf={item.confidence:.2f})")
            if item.resolution:
                print(f"Resolved:  action={item.resolution.action}, by={item.resolution.resolved_by}, val={item.resolution.value}")
            return 0

        if action == "accept":
            try:
                res = service.accept_machine_value(args.item_id, notes=args.notes)
                print(f"[+] Accepted machine value for '{args.item_id}'. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "set-category":
            try:
                res = service.set_category(args.source_id, args.category, notes=args.notes)
                print(f"[+] Overrode category for source '{args.source_id}' to '{args.category}'. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "set-level":
            try:
                res = service.set_level(args.asset_id, args.level, notes=args.notes)
                print(f"[+] Set level for asset '{args.asset_id}' to {args.level}. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "set-name":
            try:
                res = service.set_name(args.asset_id, args.name, notes=args.notes)
                print(f"[+] Set name for asset '{args.asset_id}' to '{args.name}'. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "set-counter":
            try:
                res = service.set_counter(args.asset_id, args.counter, notes=args.notes)
                print(f"[+] Set counter for asset '{args.asset_id}' to '{args.counter}'. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "clear-counter":
            try:
                res = service.clear_counter(args.asset_id, notes=args.notes)
                print(f"[+] Cleared counter for asset '{args.asset_id}'. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "set-uid":
            try:
                res = service.set_uid(args.uid, notes=args.notes)
                print(f"[+] Set UID to '{args.uid}'. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "reject":
            try:
                res = service.reject_item(args.item_id, notes=args.notes)
                print(f"[+] Rejected item '{args.item_id}'. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "skip":
            try:
                res = service.skip_item(args.item_id, notes=args.notes)
                print(f"[+] Skipped item '{args.item_id}'. Status: {res.status}")
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if action == "history":
            history = service.session.review_history
            if getattr(args, "json_output", False):
                print(json.dumps([h.to_dict() for h in history], indent=2))
                return 0
            print(f"Audit Trail for '{args.account}' ({len(history)} entries):\n")
            for h in history:
                print(f"[{h.timestamp}] {h.action:<15} item={h.review_item_id} old={h.old_value} new={h.new_value} notes={h.notes or ''}")
            return 0

        if action == "summary":
            summary = service.get_summary()
            if getattr(args, "json_output", False):
                print(json.dumps(summary, indent=2))
                return 0
            print(f"Review Summary for '{args.account}':")
            print(f"Total:            {summary['total']}")
            print(f"Open:             {summary['open']}")
            print(f"  P0:             {summary['open_by_priority']['P0']}")
            print(f"  P1:             {summary['open_by_priority']['P1']}")
            print(f"  P2:             {summary['open_by_priority']['P2']}")
            print(f"  P3:             {summary['open_by_priority']['P3']}")
            print(f"Resolved Manual:  {summary['resolved_manual']}")
            print(f"Resolved Auto:    {summary['resolved_auto']}")
            print(f"Rejected:         {summary['rejected']}")
            print(f"Skipped:          {summary['skipped']}")
            return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
