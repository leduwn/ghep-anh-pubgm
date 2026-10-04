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
    """Verifies environment, imports, models, settings, atomic session, cache, logger, and classifier smoke test."""
    print("=" * 60)
    print(f"      {APP_NAME} v{APP_VERSION} - SELF-TEST (MILESTONE 2)")
    print("=" * 60)

    import tempfile

    # 1. Imports
    print("[1/7] Checking core imports...")
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
    print("[2/7] Validating settings & canonical default...")
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
    print("[3/7] Testing atomic workspace session write & schema check...")
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
    print("[4/7] Checking ingestor & sandbox traversal protection...")
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
    print("[5/7] Testing atomic disk cache & corruption recovery...")
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
    print("[6/7] Testing logger instance isolation & cleanup...")
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
    print("[7/7] Testing screen classifier initialization & smoke categorization...")
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

    print("=" * 60)
    print("      ALL 7 SELF-TESTS PASSED SUCCESSFULLY!")
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

    # Command: info
    info_p = subparsers.add_parser("info", help="Display account session summary")
    info_p.add_argument("account", help="Account identifier")

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

        print(f"Account:    {session.account_id}")
        print(f"Version:    {session.version}")
        print(f"Sources:    {len(session.sources)}")
        print(f"Classified: {len(session.classifications)}")
        print(f"Auto:       {auto_cnt}")
        print(f"Review:     {rev_cnt}")
        print(f"Unknown:    {unk_cnt}")
        print(f"Errors:     {err_cnt}")
        print(f"Assets:     {len(session.assets)}")
        print(f"UID:        {session.uid or 'N/A'}")
        print(f"Created:    {session.created_at}")
        print(f"Updated:    {session.updated_at}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
