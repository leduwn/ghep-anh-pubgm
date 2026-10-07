"""Workspace and session persistence with atomic write guarantees."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional, Union

from .constants import DEFAULT_WORKSPACE_DIR, SESSION_SCHEMA_VERSION
from .exceptions import (
    SessionCorruptError,
    SessionIncompatibleError,
)
from .models import AccountSession
from .serialization import to_json_native

ACCOUNT_ID_SAFE_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


def validate_account_id(account_id: str) -> str:
    cleaned = account_id.strip()
    if not cleaned:
        raise ValueError("Account ID cannot be empty.")
    if not ACCOUNT_ID_SAFE_REGEX.match(cleaned):
        raise ValueError(f"Invalid account ID '{cleaned}'. Only letters, numbers, hyphens, and underscores are allowed.")
    return cleaned


class WorkspaceManager:
    """Manages filesystem layout, directory hierarchy and atomic session writes."""

    def __init__(self, workspace_root: Optional[Union[str, Path]] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else DEFAULT_WORKSPACE_DIR.resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def get_account_dir(self, account_id: str) -> Path:
        safe_id = validate_account_id(account_id)
        return self.workspace_root / safe_id

    def get_session_path(self, account_id: str) -> Path:
        return self.get_account_dir(account_id) / "session.json"

    def init_account_workspace(self, account_id: str) -> dict[str, Path]:
        """Creates account workspace directories: thumbs, assets, cache."""
        account_dir = self.get_account_dir(account_id)
        thumbs_dir = account_dir / "thumbs"
        assets_dir = account_dir / "assets"
        cache_dir = account_dir / "cache"

        for d in [account_dir, thumbs_dir, assets_dir, cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

        return {
            "account": account_dir,
            "thumbs": thumbs_dir,
            "assets": assets_dir,
            "cache": cache_dir,
        }

    def session_exists(self, account_id: str) -> bool:
        return self.get_session_path(account_id).is_file()

    def save_session(self, session: AccountSession) -> Path:
        """Atomically saves session to disk using write-flush-fsync-replace pattern."""
        self.init_account_workspace(session.account_id)
        session_path = self.get_session_path(session.account_id)
        temp_path = session_path.with_suffix(".tmp")

        session.touch()
        data = to_json_native(session.to_dict())

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, session_path)
            return session_path
        except Exception as exc:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise SessionCorruptError(f"Failed to atomically write session for '{session.account_id}': {exc}") from exc

    def load_session(self, account_id: str) -> AccountSession:
        """Loads and validates a session JSON manifest."""
        session_path = self.get_session_path(account_id)
        if not session_path.is_file():
            raise FileNotFoundError(f"Session not found for account: {account_id}")

        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise SessionCorruptError(f"Corrupt JSON in session file {session_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise SessionCorruptError(f"Invalid root type in session file: expected dict, got {type(data).__name__}")

        schema_version = int(data.get("version", 0))
        if schema_version != SESSION_SCHEMA_VERSION:
            raise SessionIncompatibleError(
                f"Session schema version {schema_version} is incompatible with supported version {SESSION_SCHEMA_VERSION}."
            )

        return AccountSession.from_dict(data)

    def list_accounts(self) -> list[str]:
        """Lists all existing accounts with valid session manifests in workspace."""
        accounts = []
        if not self.workspace_root.is_dir():
            return []
        for child in self.workspace_root.iterdir():
            if child.is_dir() and (child / "session.json").is_file():
                accounts.append(child.name)
        return sorted(accounts)
