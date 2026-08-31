"""Focused tests for workspace management screen under single-root shell."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from framework.workspace.workspace_service import WorkspaceService


def _build_screen():
    from ui.workspace_ui import WorkspaceManagementUI

    try:
        root = tk.Tk()
        root.withdraw()
        screen = WorkspaceManagementUI(root)
        screen.grid(row=0, column=0)
        root.update_idletasks()
        return root, screen
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")


def _select_row_by_test_name(screen, test_name: str) -> None:
    for row_id in screen._recording_tree.get_children():
        values = screen._recording_tree.item(row_id, "values")
        if values and values[0] == test_name:
            screen._recording_tree.selection_set(row_id)
            screen._on_recording_selection_change()
            return
    raise AssertionError(f"Row not found for test name: {test_name}")


class TestWorkspaceManagementUIConstructionAndBrowse:
    def test_ui_constructs_with_tooltips_and_default_status(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DESKTOP_AUTOMATION_WORKSPACE_ROOT", str(tmp_path / "ws_root"))
        # Prevent recent-workspace restore from affecting initial status message.
        monkeypatch.setattr("ui.workspace_ui.load_recent", lambda: None)

        root, screen = _build_screen()
        try:
            assert "No workspace selected" in screen._status_var.get()
            assert screen._workspace_path_var.get() == str((tmp_path / "ws_root").resolve())
            assert screen._workspace_name_help is not None
            assert screen._workspace_path_help is not None
            assert len(screen._tooltips) >= 2
        finally:
            root.destroy()

    def test_browse_uses_single_root_owner_context(self, monkeypatch, tmp_path: Path) -> None:
        root, screen = _build_screen()
        try:
            current = tmp_path / "current"
            current.mkdir()
            screen._workspace_path_var.set(str(current))

            seen: dict[str, object] = {}

            class _FakePicker:
                def __init__(self, root_tk=None, initial_dir=None, title="", on_complete=None):
                    seen["initial_dir"] = initial_dir
                    seen["title"] = title
                    seen["callback"] = on_complete
                    # Simulate immediate async completion by calling the callback.
                    if on_complete:
                        root_tk.after(0, lambda: on_complete(""))

            monkeypatch.setattr("ui.workspace_ui.FolderPickerAsync", _FakePicker)
            screen._on_browse()
            root.update()  # Process all pending events including after(0, ...) callbacks

            assert seen["initial_dir"] is not None
            assert isinstance(seen["initial_dir"], Path)
        finally:
            root.destroy()

    def test_browse_cancel_keeps_existing_path(self, monkeypatch, tmp_path: Path) -> None:
        root, screen = _build_screen()
        try:
            original = str(tmp_path / "existing")
            screen._workspace_path_var.set(original)

            class _FakePicker:
                def __init__(self, root_tk=None, initial_dir=None, title="", on_complete=None):
                    # Simulate cancel by passing empty string to callback.
                    if on_complete:
                        root_tk.after(0, lambda: on_complete(""))

            monkeypatch.setattr("ui.workspace_ui.FolderPickerAsync", _FakePicker)
            screen._on_browse()
            root.update()  # Process all pending events including after(0, ...) callbacks

            assert screen._workspace_path_var.get() == original
        finally:
            root.destroy()

    def test_browse_selected_directory_updates_path(self, monkeypatch, tmp_path: Path) -> None:
        root, screen = _build_screen()
        try:
            chosen = tmp_path / "chosen_dir"
            chosen.mkdir()
            chosen_str = str(chosen)

            class _FakePicker:
                def __init__(self, root_tk=None, initial_dir=None, title="", on_complete=None):
                    # Simulate successful selection by passing path to callback.
                    if on_complete:
                        root_tk.after(0, lambda path=chosen_str: on_complete(path))

            monkeypatch.setattr("ui.workspace_ui.FolderPickerAsync", _FakePicker)
            screen._on_browse()
            root.update()  # Process all pending events including after(0, ...) callbacks

            assert screen._workspace_path_var.get() == str(chosen.resolve())
            assert "Workspace path updated" in screen._status_var.get()
        finally:
            root.destroy()


class TestWorkspaceManagementUICreateOpenFlow:
    def test_create_workspace_success_and_selection(self, tmp_path: Path) -> None:
        root, screen = _build_screen()
        try:
            base_root = tmp_path / "roots"
            screen._workspace_name_var.set("PhaseOne")
            screen._workspace_path_var.set(str(base_root))

            screen._on_create_workspace()

            expected_root = (base_root / "PhaseOne").resolve()
            assert screen._workspace_service is not None
            assert screen._workspace_service.info.root == expected_root
            assert screen._selected_workspace_var.get() == str(expected_root)
            assert expected_root.is_dir()
        finally:
            root.destroy()

    def test_open_workspace_success_from_existing_root(self, tmp_path: Path) -> None:
        base_root = tmp_path / "workspace_parent"
        created = WorkspaceService.create(root=base_root / "Openable", name="Openable")

        root, screen = _build_screen()
        try:
            screen._workspace_name_var.set("Openable")
            screen._workspace_path_var.set(str(base_root))

            screen._on_open_workspace()

            assert screen._workspace_service is not None
            assert screen._workspace_service.info.root == created.info.root
            assert "opened successfully" in screen._status_var.get().lower()
        finally:
            root.destroy()


class TestWorkspaceManagementUIRecordingsAndExecution:
    def test_json_discovery_shows_actual_json_file_column(self, tmp_path: Path) -> None:
        ws = WorkspaceService.create(root=tmp_path / "ws" / "Discover", name="Discover")
        (ws.recordings_dir_for() / "workspace_flow.json").write_text("[]", encoding="utf-8")
        (ws.recordings_dir_for("smoke") / "smoke_flow.json").write_text("[]", encoding="utf-8")

        root, screen = _build_screen()
        try:
            screen._workspace_path_var.set(str(ws.info.root))
            screen._on_open_workspace()

            rows = screen._recording_tree.get_children()
            assert len(rows) == 2

            values = [screen._recording_tree.item(row, "values") for row in rows]
            assert any(v[0] == "workspace/workspace_flow" for v in values)
            assert any(v[0] == "smoke/smoke_flow" for v in values)
            assert any(str(v[1]).endswith("workspace_flow.json") for v in values)
            assert any(str(v[1]).endswith("smoke_flow.json") for v in values)
        finally:
            root.destroy()

    def test_run_and_open_buttons_enable_only_after_selection(self, tmp_path: Path) -> None:
        ws = WorkspaceService.create(root=tmp_path / "ws" / "SelectRun", name="SelectRun")
        (ws.recordings_dir_for() / "first.json").write_text("[]", encoding="utf-8")

        root, screen = _build_screen()
        try:
            screen._workspace_path_var.set(str(ws.info.root))
            screen._on_open_workspace()

            assert str(screen._run_btn["state"]) == "disabled"
            assert str(screen._open_json_btn["state"]) == "disabled"

            _select_row_by_test_name(screen, "workspace/first")

            assert str(screen._run_btn["state"]) == "normal"
            assert str(screen._open_json_btn["state"]) == "normal"
        finally:
            root.destroy()

    def test_run_selected_executes_only_selected_recording_path(self, tmp_path: Path, monkeypatch) -> None:
        ws = WorkspaceService.create(root=tmp_path / "ws" / "Exec", name="Exec")
        (ws.recordings_dir_for() / "first.json").write_text("[]", encoding="utf-8")
        (ws.recordings_dir_for() / "second.json").write_text("[]", encoding="utf-8")

        loaded_names: list[str] = []
        executor_runs: list[list] = []

        class _FakeStore:
            def __init__(self, base_dir):
                self.base_dir = Path(base_dir)

            def load(self, name: str):
                loaded_names.append(name)
                return [MagicMock()]

        class _FakeDriver:
            def quit(self):
                return None

        class _FakeExecutor:
            def __init__(self, driver, recording_name=None):
                self.driver = driver
                self.recording_name = recording_name

            def run(self, actions, **kwargs):
                executor_runs.append(list(actions))

        monkeypatch.setattr("ui.workspace_ui.RecordingStore", _FakeStore)
        monkeypatch.setattr("ui.workspace_ui.DesktopDriver", _FakeDriver)
        monkeypatch.setattr("ui.workspace_ui.PlaybackExecutor", _FakeExecutor)

        root, screen = _build_screen()
        try:
            screen._workspace_path_var.set(str(ws.info.root))
            screen._on_open_workspace()

            _select_row_by_test_name(screen, "workspace/second")

            # _on_run_selected now runs async (background thread + self.after()).
            # In a headless test without a mainloop, verify the synchronous state
            # (status set to "Running...") and that the store was consulted.
            screen._on_run_selected()

            assert loaded_names == ["second"], "Only the selected recording must be loaded"
            # Status is set synchronously to the "running" message before the thread starts.
            assert "second" in screen._status_var.get().lower()
        finally:
            root.destroy()
