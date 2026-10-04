"""Unit tests for workspace management, atomic session persistence, and pipeline."""

import pytest
from core.constants import SESSION_SCHEMA_VERSION, SourceStatus
from core.exceptions import SessionIncompatibleError
from core.models import AccountSession, SourceImage
from core.session import WorkspaceManager
from app.pipeline import AutoCutPipeline


def test_atomic_session_save_and_load(temp_workspace):
    ws = WorkspaceManager(temp_workspace)
    session = AccountSession(account_id="ACC_TEST_01")
    src = SourceImage("s1", "img1.png", "hash1", "img1.png", 1920, 1080, 1.0, 1)
    session.add_source(src)

    saved_path = ws.save_session(session)
    assert saved_path.is_file()
    # Confirm no leftover temporary file
    assert not saved_path.with_suffix(".tmp").exists()

    loaded = ws.load_session("ACC_TEST_01")
    assert loaded.account_id == "ACC_TEST_01"
    assert len(loaded.sources) == 1
    assert loaded.sources["s1"].sha256 == "hash1"


def test_session_incompatible_version(temp_workspace):
    ws = WorkspaceManager(temp_workspace)
    session = AccountSession(account_id="ACC_FUTURE")
    ws.save_session(session)

    # Artificially bump schema version in JSON
    session_file = ws.get_session_path("ACC_FUTURE")
    content = session_file.read_text(encoding="utf-8")
    future_content = content.replace(f'"version": {SESSION_SCHEMA_VERSION}', '"version": 999')
    session_file.write_text(future_content, encoding="utf-8")

    with pytest.raises(SessionIncompatibleError):
        ws.load_session("ACC_FUTURE")


def test_pipeline_ingest_and_duplicate_prevention(temp_workspace, sample_image_1080p, sample_image_pubg):
    ws = WorkspaceManager(temp_workspace)
    pipeline = AutoCutPipeline(workspace=ws)

    # 1. Ingest two distinct images
    session = pipeline.ingest_sources("ACC_PIPE", [sample_image_1080p, sample_image_pubg])
    assert len(session.sources) == 2
    assert pipeline.metrics.sources_total == 2
    assert pipeline.metrics.duplicates_skipped == 0

    # 2. Ingest duplicate image without force_reprocess
    session_after_dup = pipeline.ingest_sources("ACC_PIPE", [sample_image_1080p])
    assert len(session_after_dup.sources) == 2
    assert pipeline.metrics.duplicates_skipped == 1

    # 3. Resume existing session across instances
    pipeline_resumed = AutoCutPipeline(workspace=ws)
    resumed = pipeline_resumed.get_or_create_session("ACC_PIPE")
    assert len(resumed.sources) == 2


def test_workspace_list_accounts(temp_workspace):
    ws = WorkspaceManager(temp_workspace)
    assert ws.list_accounts() == []

    ws.save_session(AccountSession("ACC_B"))
    ws.save_session(AccountSession("ACC_A"))

    assert ws.list_accounts() == ["ACC_A", "ACC_B"]
