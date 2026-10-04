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
    """Verifies environment, imports, models, settings, atomic session, cache, and logger isolation."""
    print("=" * 60)
    print(f"      {APP_NAME} v{APP_VERSION} - SELF-TEST (MILESTONE 1.1)")
    print("=" * 60)

    import tempfile

    # 1. Imports
    print("[1/6] Checking core imports...")
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
    print("[2/6] Validating settings & canonical default...")
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
    print("[3/6] Testing atomic workspace session write & schema check...")
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
    print("[4/6] Checking ingestor & sandbox traversal protection...")
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
    print("[5/6] Testing atomic disk cache & corruption recovery...")
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
    print("[6/6] Testing logger instance isolation & cleanup...")
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

    print("=" * 60)
    print("      ALL 6 SELF-TESTS PASSED SUCCESSFULLY!")
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

    if args.command == "info":
        ws = WorkspaceManager()
        if not ws.session_exists(args.account):
            print(f"Error: No session found for account '{args.account}'", file=sys.stderr)
            return 1
        session = ws.load_session(args.account)
        print(f"Account:   {session.account_id}")
        print(f"Version:   {session.version}")
        print(f"Sources:   {len(session.sources)}")
        print(f"Assets:    {len(session.assets)}")
        print(f"UID:       {session.uid or 'N/A'}")
        print(f"Created:   {session.created_at}")
        print(f"Updated:   {session.updated_at}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
