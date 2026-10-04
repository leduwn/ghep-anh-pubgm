"""Rotating structured logger with pipeline stage tracking for Auto-Cut-Next."""

from __future__ import annotations

import hashlib
import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional, Union

from .constants import Stage, DEFAULT_WORKSPACE_DIR


class StageFormatter(logging.Formatter):
    """Custom formatter producing uniform structured log lines."""

    def format(self, record: logging.LogRecord) -> str:
        stage = getattr(record, "stage", "-")
        account = getattr(record, "account", "-")
        source = getattr(record, "source", "-")
        status = getattr(record, "status", "-")
        duration = getattr(record, "duration_ms", None)

        dur_str = f" ({duration:.1f}ms)" if duration is not None else ""
        time_str = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        prefix = f"[{time_str}] [{record.levelname:<5}] [{stage:<9}] [{account}] [{source}] [{status}]{dur_str}"
        return f"{prefix} {record.getMessage()}"


class StageLogger:
    """Manages application-wide and account-specific logging with file rotation and ref-counted handlers."""

    _REGISTRY_LOCK = threading.RLock()
    _PATH_REFCOUNT: dict[Path, int] = {}
    _PATH_HANDLERS: dict[Path, list[logging.Handler]] = {}

    def __init__(
        self,
        log_dir: Optional[Union[str, Path]] = None,
        log_filename: str = "autocut_next.log",
        max_bytes: int = 8 * 1024 * 1024,
        backup_count: int = 5,
        console: bool = True,
        level: int = logging.INFO,
    ):
        self.log_dir = Path(log_dir) if log_dir else DEFAULT_WORKSPACE_DIR / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / log_filename
        resolved_path = self.log_path.resolve()
        self._resolved_path = resolved_path
        self._closed = False

        # Unique logger identity per resolved log path to avoid multi-workspace collisions
        logger_id = hashlib.sha1(str(resolved_path).encode("utf-8")).hexdigest()[:12]
        self.logger = logging.getLogger(f"AutoCutNext.{logger_id}")
        self.logger.setLevel(level)
        self.logger.propagate = False

        with self._REGISTRY_LOCK:
            self._PATH_REFCOUNT[resolved_path] = self._PATH_REFCOUNT.get(resolved_path, 0) + 1

            if resolved_path not in self._PATH_HANDLERS:
                handlers: list[logging.Handler] = []
                file_handler = RotatingFileHandler(
                    self.log_path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
                file_handler.setFormatter(StageFormatter())
                self.logger.addHandler(file_handler)
                handlers.append(file_handler)

                if console:
                    console_handler = logging.StreamHandler()
                    console_handler.setFormatter(StageFormatter())
                    self.logger.addHandler(console_handler)
                    handlers.append(console_handler)

                self._PATH_HANDLERS[resolved_path] = handlers

    def close(self) -> None:
        """Decrements refcount; closes and detaches handlers only when no active logger instances remain."""
        with self._REGISTRY_LOCK:
            if getattr(self, "_closed", False):
                return
            self._closed = True
            resolved_path = getattr(self, "_resolved_path", None)
            if not resolved_path or resolved_path not in self._PATH_REFCOUNT:
                return

            self._PATH_REFCOUNT[resolved_path] -= 1
            if self._PATH_REFCOUNT[resolved_path] <= 0:
                handlers = self._PATH_HANDLERS.pop(resolved_path, [])
                for h in handlers:
                    try:
                        h.flush()
                        h.close()
                    except Exception:
                        pass
                    self.logger.removeHandler(h)
                self._PATH_REFCOUNT.pop(resolved_path, None)

    def __enter__(self) -> "StageLogger":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def log(
        self,
        level: int,
        message: str,
        stage: Union[Stage, str] = Stage.INGEST,
        account: str = "-",
        source: str = "-",
        status: str = "-",
        duration_ms: Optional[float] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        stage_name = stage.value if isinstance(stage, Stage) else str(stage)
        record_extra = {
            "stage": stage_name,
            "account": account,
            "source": source,
            "status": status,
            "duration_ms": duration_ms,
        }
        if extra:
            record_extra.update(extra)
        self.logger.log(level, message, extra=record_extra)

    def info(self, message: str, stage: Union[Stage, str] = Stage.INGEST, account: str = "-", source: str = "-", status: str = "-", duration_ms: Optional[float] = None, **kwargs) -> None:
        self.log(logging.INFO, message, stage=stage, account=account, source=source, status=status, duration_ms=duration_ms, extra=kwargs)

    def warning(self, message: str, stage: Union[Stage, str] = Stage.INGEST, account: str = "-", source: str = "-", status: str = "-", duration_ms: Optional[float] = None, **kwargs) -> None:
        self.log(logging.WARNING, message, stage=stage, account=account, source=source, status=status, duration_ms=duration_ms, extra=kwargs)

    def error(self, message: str, stage: Union[Stage, str] = Stage.INGEST, account: str = "-", source: str = "-", status: str = "-", duration_ms: Optional[float] = None, **kwargs) -> None:
        self.log(logging.ERROR, message, stage=stage, account=account, source=source, status=status, duration_ms=duration_ms, extra=kwargs)

    def debug(self, message: str, stage: Union[Stage, str] = Stage.INGEST, account: str = "-", source: str = "-", status: str = "-", duration_ms: Optional[float] = None, **kwargs) -> None:
        self.log(logging.DEBUG, message, stage=stage, account=account, source=source, status=status, duration_ms=duration_ms, extra=kwargs)
