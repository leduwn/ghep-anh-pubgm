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
    """Verifies environment, imports, models, and workspace writing."""
    print("=" * 60)
    print(f"      {APP_NAME} v{APP_VERSION} - SELF-TEST")
    print("=" * 60)

    # 1. Imports
    print("[1/4] Checking core imports...")
    try:
        from core.models import SourceImage, Rect, DetectedAsset, AccountSession
        from core.ingest import ImageIngestor
        from core.cache import LRUCache, DiskCache
        print("      PASS: Core models and modules imported cleanly.")
    except Exception as exc:
        print(f"      FAIL: Core imports error: {exc}")
        return 1

    # 2. Settings validation
    print("[2/4] Validating default settings...")
    try:
        settings = AutoCutSettings()
        settings.validate()
        print(f"      PASS: Settings validated (workspace={settings.workspace_dir.name}).")
    except Exception as exc:
        print(f"      FAIL: Settings validation error: {exc}")
        return 1

    # 3. Workspace write
    print("[3/4] Testing atomic workspace session write...")
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            ws = WorkspaceManager(temp_dir)
            session = AccountSession(account_id="self_test_acc")
            saved_path = ws.save_session(session)
            loaded = ws.load_session("self_test_acc")
            assert loaded.account_id == "self_test_acc"
            assert saved_path.is_file()
        print("      PASS: Atomic workspace session save/load verified.")
    except Exception as exc:
        print(f"      FAIL: Workspace write error: {exc}")
        return 1

    # 4. Ingestor check
    print("[4/4] Checking image ingestor...")
    try:
        ingestor = ImageIngestor()
        assert ingestor is not None
        print("      PASS: Ingestor initialized.")
    except Exception as exc:
        print(f"      FAIL: Ingestor initialization error: {exc}")
        return 1

    print("=" * 60)
    print("      ALL SELF-TESTS PASSED SUCCESSFULLY!")
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
        files = pipeline.ingestor.scan_directory(folder)
        print(f"[*] Found {len(files)} image candidate(s) in {folder.name}")
        session = pipeline.ingest_sources(args.account, files, force_reprocess=args.force)
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
