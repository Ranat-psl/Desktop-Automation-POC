"""Focused tests for portable workspace-root resolution."""
from __future__ import annotations

from pathlib import Path

from framework.workspace.root_resolver import WORKSPACE_ROOT_ENV_VAR, resolve_default_workspace_root


def test_workspace_root_env_override_takes_priority(tmp_path: Path) -> None:
    env = {
        WORKSPACE_ROOT_ENV_VAR: str(tmp_path / "custom_root"),
        "LOCALAPPDATA": str(tmp_path / "local_app_data"),
    }

    resolved = resolve_default_workspace_root(
        env=env,
        platform_system="Windows",
        home=tmp_path / "home",
    )

    assert resolved == (tmp_path / "custom_root").resolve()


def test_workspace_root_defaults_to_localappdata_on_windows(tmp_path: Path) -> None:
    local_app_data = tmp_path / "LocalAppData"
    env = {"LOCALAPPDATA": str(local_app_data)}

    resolved = resolve_default_workspace_root(
        env=env,
        platform_system="Windows",
        home=tmp_path / "home",
    )

    expected = local_app_data / "Persistent" / "DesktopAutomation" / "workspaces"
    assert resolved == expected.resolve()


def test_workspace_root_windows_fallback_without_localappdata(tmp_path: Path) -> None:
    home = tmp_path / "home"

    resolved = resolve_default_workspace_root(
        env={},
        platform_system="Windows",
        home=home,
    )

    expected = home / "AppData" / "Local" / "Persistent" / "DesktopAutomation" / "workspaces"
    assert resolved == expected.resolve()
