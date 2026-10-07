"""Integration tests running review queue building and manual correction on real fixtures."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from core.constants import ReviewStatus
from core.session import WorkspaceManager
from app.pipeline import AutoCutPipeline


REAL_INPUT_DIR = Path(__file__).resolve().parent.parent.parent / "Cắt" / "input"


@pytest.fixture(scope="module")
def real_fixture_pipeline(tmp_path_factory):
    if not REAL_INPUT_DIR.is_dir():
        pytest.skip(f"Real fixture directory absent: {REAL_INPUT_DIR}")

    all_images = sorted([
        f for f in REAL_INPUT_DIR.iterdir()
        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ])
    if not all_images:
        pytest.skip(f"No real screenshot fixtures in {REAL_INPUT_DIR}")

    # Create temporary isolated workspace
    temp_ws = tmp_path_factory.mktemp("real_review_ws")
    ws = WorkspaceManager(temp_ws)
    pipeline = AutoCutPipeline(workspace=ws)
    account_id = "real_review_test_account"

    # Ingest first 10 screenshots to keep test fast
    sample_images = all_images[:10]
    session = pipeline.ingest_sources(account_id, sample_images)
    session = pipeline.classify_session(account_id)
    session = pipeline.detect_session(account_id)
    return pipeline, account_id


def test_build_review_queue_on_real_fixtures(real_fixture_pipeline):
    """Builds review queue on real screenshots, verifying deterministic generation."""
    pipeline, account_id = real_fixture_pipeline
    session = pipeline.build_review_queue(account_id)

    assert isinstance(session.review_items, dict)
    items = list(session.review_items.values())

    # Every item must have valid ID, subsystem, status, priority, and reason
    for it in items:
        assert it.id.startswith("review:")
        assert it.subsystem in {"CLASSIFICATION", "DETECTION", "ASSET_QUALITY", "OCR_GUN", "UID"}
        assert it.status in {"OPEN", "RESOLVED_AUTO", "RESOLVED_MANUAL", "REJECTED", "SKIPPED", "STALE"}
        assert it.priority in {"P0", "P1", "P2", "P3"}

    # Re-running build_queue yields identical count and IDs (idempotency)
    session2 = pipeline.build_review_queue(account_id)
    assert len(session2.review_items) == len(session.review_items)
    assert set(session2.review_items.keys()) == set(session.review_items.keys())


def test_manual_resolution_workflow_on_real_fixtures(real_fixture_pipeline):
    """Executes a manual correction cycle on real fixture session and verifies audit log."""
    pipeline, account_id = real_fixture_pipeline
    service = pipeline.get_review_service(account_id)

    open_items = service.list_items(status=ReviewStatus.OPEN.value)
    if not open_items:
        pytest.skip("No open review items in sample to test manual resolution")

    target_item = open_items[0]
    initial_history_len = len(service.session.review_history)

    # Resolve target item
    res = service.accept_machine_value(target_item.id, notes="Verified on real fixture")
    assert res.status == ReviewStatus.RESOLVED_MANUAL.value
    assert len(service.session.review_history) == initial_history_len + 1

    # Verify persistent state upon reload
    reloaded = pipeline.workspace.load_session(account_id)
    assert reloaded.review_items[target_item.id].status == ReviewStatus.RESOLVED_MANUAL.value
    assert len(reloaded.review_history) == initial_history_len + 1
