"""Workspace root resolution helpers.

Resolves a portable default root for user-created workspaces and supports an
environment-variable override for future deployment scenarios.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Mapping

WORKSPACE_ROOT_ENV_VAR = "DESKTOP_AUTOMATION_WORKSPACE_ROOT"


def resolve_default_workspace_root(
    *,
    env: Mapping[str, str] | None = None,
    platform_system: str | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve the default parent directory used for workspace creation.

    Resolution order:
    1. ``DESKTOP_AUTOMATION_WORKSPACE_ROOT`` environment variable override.
    2. Platform-specific per-user application data location.
    """
    env_map: Mapping[str, str] = os.environ if env is None else env

    override = env_map.get(WORKSPACE_ROOT_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser().resolve()

    system_name = (platform_system or platform.system()).lower()
    home_path = (home or Path.home()).expanduser()

    if system_name == "windows":
        local_app_data = env_map.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            base = Path(local_app_data).expanduser()
        else:
            base = home_path / "AppData" / "Local"
        return (base / "Persistent" / "DesktopAutomation" / "workspaces").resolve()

    if system_name == "darwin":
        return (
            home_path
            / "Library"
            / "Application Support"
            / "Persistent"
            / "DesktopAutomation"
            / "workspaces"
        ).resolve()

    return (
        home_path
        / ".local"
        / "share"
        / "persistent"
        / "desktop_automation"
        / "workspaces"
    ).resolve()
