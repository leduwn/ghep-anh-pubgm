"""Central pipeline orchestrator for Auto-Cut-Next."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Union

from core.constants import Stage, SourceStatus
from core.ingest import ImageIngestor
from core.logging import StageLogger
from core.metrics import MetricsCollector
from core.models import AccountSession, SourceImage
from core.session import WorkspaceManager
from core.settings import AutoCutSettings


class AutoCutPipeline:
    """Coordinates ingestion, session management, and stage execution."""

    def __init__(
        self,
        settings: Optional[AutoCutSettings] = None,
        workspace: Optional[WorkspaceManager] = None,
        logger: Optional[StageLogger] = None,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.settings = settings or AutoCutSettings()
        self.workspace = workspace or WorkspaceManager(self.settings.workspace_dir)
        self.logger = logger or StageLogger(self.workspace.workspace_root / "logs")
        self.metrics = metrics or MetricsCollector()
        self.ingestor = ImageIngestor()

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
