"""Recent workspace persistence.

Saves and restores the most-recently-used workspace path across application
launches.  The state file lives in a platform-safe user-data directory and
is independent from workspace content.

Usage::

    from framework.workspace.recent_workspace import save_recent, load_recent

    save_recent(Path("C:/workspaces/MyWorkspace"))
    path = load_recent()   # returns Path or None
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)

# Platform-safe user data directory: ~/.da-poc/
_STATE_DIR = Path.home() / ".da-poc"
_STATE_FILE = _STATE_DIR / "recent_workspace.json"

_KEY = "recent_workspace_path"


def save_recent(path: Path) -> None:
    """Persist *path* as the most-recently-used workspace.

    Silently ignores I/O errors so a persistence failure never prevents
    normal application operation.
    """
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        data = {_KEY: str(path.resolve())}
        _STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _log.debug("Saved recent workspace: %s", path)
    except Exception as exc:  # noqa: BLE001
        _log.debug("Could not save recent workspace: %s", exc)


def load_recent() -> Path | None:
    """Return the most-recently-used workspace path, or None.

    Returns None if no state has been saved, the state file is corrupt, or
    the saved path no longer exists on disk.
    """
    try:
        if not _STATE_FILE.exists():
            return None
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        raw = data.get(_KEY)
        if not raw:
            return None
        p = Path(raw)
        if p.exists() and p.is_dir():
            _log.debug("Loaded recent workspace: %s", p)
            return p
        _log.debug("Recent workspace no longer exists: %s", p)
        return None
    except Exception as exc:  # noqa: BLE001
        _log.debug("Could not load recent workspace: %s", exc)
        return None
