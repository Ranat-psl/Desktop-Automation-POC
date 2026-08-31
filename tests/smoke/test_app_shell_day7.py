"""Smoke tests for the single-root application shell."""
from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_tk_mainloop(monkeypatch):
    monkeypatch.setattr(tk.Tk, "mainloop", lambda self: None)


def _build_shell(default_screen: str = "workspace"):
    from ui.app_shell import AppShell

    try:
        app = AppShell(default_screen=default_screen)
        app.withdraw()
        app.update_idletasks()
        return app
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")


class TestAppShellSingleRootFlow:
    def test_shell_constructs_and_mounts_screens(self) -> None:
        app = _build_shell(default_screen="workspace")
        try:
            assert app._current_screen_name == "workspace"
            assert set(app._screens.keys()) == {"workspace", "recorder"}

            workspace = app._screens["workspace"]
            recorder = app._screens["recorder"]

            assert workspace.winfo_toplevel() is app
            assert recorder.winfo_toplevel() is app
            assert workspace.master is app._content
            assert recorder.master is app._content
        finally:
            app.destroy()

    def test_navigation_workspace_to_recorder_and_back(self) -> None:
        app = _build_shell(default_screen="workspace")
        try:
            app.show_screen("recorder")
            assert app._current_screen_name == "recorder"

            app.show_screen("workspace")
            assert app._current_screen_name == "workspace"
        finally:
            app.destroy()

    def test_open_testcases_routes_to_workspace_focus_recordings(self) -> None:
        app = _build_shell(default_screen="recorder")
        try:
            workspace = app._screens["workspace"]
            workspace.focus_recordings = MagicMock()  # type: ignore[attr-defined]

            app._open_test_cases()

            assert app._current_screen_name == "workspace"
            workspace.focus_recordings.assert_called_once()
        finally:
            app.destroy()

    def test_exit_respects_recorder_guard(self) -> None:
        app = _build_shell(default_screen="recorder")
        try:
            recorder = app._screens["recorder"]
            recorder.handle_exit_request = MagicMock(return_value=False)  # type: ignore[attr-defined]
            app.destroy = MagicMock()

            app._on_exit()

            recorder.handle_exit_request.assert_called_once()
            app.destroy.assert_not_called()
        finally:
            tk.Tk.destroy(app)

    def test_exit_destroys_when_guard_allows(self) -> None:
        app = _build_shell(default_screen="workspace")
        try:
            recorder = app._screens["recorder"]
            recorder.handle_exit_request = MagicMock(return_value=True)  # type: ignore[attr-defined]
            app.destroy = MagicMock()

            app._on_exit()

            recorder.handle_exit_request.assert_called_once()
            app.destroy.assert_called_once()
        finally:
            tk.Tk.destroy(app)
