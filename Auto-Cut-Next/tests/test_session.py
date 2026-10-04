"""Unit tests for workspace management, atomic session persistence, and pipeline."""

from pathlib import Path
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



def test_session_incompatible_older_version(temp_workspace):
    ws = WorkspaceManager(temp_workspace)
    session = AccountSession(account_id="ACC_OLD")
    ws.save_session(session)

    # Change schema version to 0
    session_file = ws.get_session_path("ACC_OLD")
    content = session_file.read_text(encoding="utf-8")
    old_content = content.replace(f'"version": {SESSION_SCHEMA_VERSION}', '"version": 0')
    session_file.write_text(old_content, encoding="utf-8")

    with pytest.raises(SessionIncompatibleError):
        ws.load_session("ACC_OLD")


def test_force_reprocess_invalidates_derived_assets(temp_workspace, sample_image_1080p):
    ws = WorkspaceManager(temp_workspace)
    pipeline = AutoCutPipeline(workspace=ws)

    # Ingest source A
    session = pipeline.ingest_sources("ACC_FORCE", [sample_image_1080p])
    assert len(session.sources) == 1
    src_id = list(session.sources.keys())[0]

    # Add simulated derived asset
    from core.models import DetectedAsset, Rect
    asset = DetectedAsset("a1", src_id, "GUN", Rect(0, 0, 10, 10), 10, 10, "det", "1.0")
    session.add_asset(asset)
    ws.save_session(session)
    assert len(session.assets) == 1

    # Ingest without force -> asset preserved, duplicate skipped
    pipeline2 = AutoCutPipeline(workspace=ws)
    s2 = pipeline2.ingest_sources("ACC_FORCE", [sample_image_1080p], force_reprocess=False)
    assert len(s2.sources) == 1
    assert len(s2.assets) == 1
    assert pipeline2.metrics.sources_duplicates == 1

    # Ingest WITH force -> source refreshed, duplicate NOT added, derived asset invalidated!
    pipeline3 = AutoCutPipeline(workspace=ws)
    s3 = pipeline3.ingest_sources("ACC_FORCE", [sample_image_1080p], force_reprocess=True)
    assert len(s3.sources) == 1
    assert len(s3.assets) == 0  # Invalidated!
    assert pipeline3.metrics.sources_forced == 1
    assert pipeline3.metrics.sources_added == 0


def test_pipeline_ingest_folder(temp_workspace, sample_image_1080p, sample_image_pubg):
    ws = WorkspaceManager(temp_workspace)
    pipeline = AutoCutPipeline(workspace=ws)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / "img1.png").write_bytes(sample_image_1080p.read_bytes())
        (folder / "img2.png").write_bytes(sample_image_pubg.read_bytes())

        session = pipeline.ingest_folder("ACC_FOLDER", folder)
        assert len(session.sources) == 2
        assert pipeline.metrics.sources_added == 2
        assert pipeline.metrics.sources_seen == 2




def test_pipeline_default_uses_canonical_settings():
    pipeline = AutoCutPipeline(settings=None)
    # Must use canonical default settings with absolute workspace path
    assert pipeline.settings is not None
    assert pipeline.settings.workspace_dir.is_absolute()
    assert pipeline.settings.classifier_accept_threshold == 0.85

