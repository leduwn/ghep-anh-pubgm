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

    def ingest_sources(
        self,
        account_id: str,
        file_paths: list[Union[str, Path]],
        force_reprocess: bool = False,
    ) -> AccountSession:
        """Ingests files into account session with deduplication and thumbnails."""
        session = self.get_or_create_session(account_id)
        dirs = self.workspace.init_account_workspace(account_id)
        thumbs_dir = dirs["thumbs"]

        with self.metrics.timer("ingest"):
            for idx, raw_path in enumerate(file_paths, start=len(session.sources) + 1):
                path = Path(raw_path).resolve()
                t0 = time.perf_counter()

                source = self.ingestor.ingest_file(
                    path,
                    source_index=idx,
                    thumb_dir=thumbs_dir,
                )
                duration_ms = (time.perf_counter() - t0) * 1000.0

                if source.status == SourceStatus.SUCCESS.value:
                    existing = session.get_source_by_sha256(source.sha256)
                    if existing and not force_reprocess:
                        self.metrics.duplicates_skipped += 1
                        self.logger.info(
                            f"Skipped duplicate source '{path.name}' (matches {existing.filename})",
                            stage=Stage.INGEST,
                            account=account_id,
                            source=path.name,
                            status="DUPLICATE",
                            duration_ms=duration_ms,
                        )
                        continue

                    session.add_source(source)
                    self.metrics.sources_total += 1
                    self.logger.info(
                        f"Ingested source {source.filename} ({source.width}x{source.height})",
                        stage=Stage.INGEST,
                        account=account_id,
                        source=path.name,
                        status="SUCCESS",
                        duration_ms=duration_ms,
                    )
                else:
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
