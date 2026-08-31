"""Phase 1 regression tests — workspace/recording integration and Open Report fix.

Tests:
  TEST 1  Create/select workspace → recordings directory exists.
  TEST 2  Start/stop/save recording → JSON saved inside selected workspace.
  TEST 3  Load workspace → saved recording appears in discovery.
  TEST 4  Refresh workspace → recording remains visible.
  TEST 5  Persisted workspace path survives a reload (WorkspaceService.load).
  TEST 6  Open valid HTML report → webbrowser.open is invoked (not Notepad).
  TEST 7  Open report when report.html missing → graceful error, no exception.
  TEST 8  Recording with no workspace selected → start is refused.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from framework.workspace.workspace_service import WorkspaceService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_workspace_screen(root):
    """Create a WorkspaceManagementUI without display errors, or skip."""
    from ui.workspace_ui import WorkspaceManagementUI
    try:
        screen = WorkspaceManagementUI(root)
        screen.grid(row=0, column=0)
        root.update_idletasks()
        return screen
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")


def _make_tk():
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")


def _mock_pynput():
    """Patch pynput so no real OS hooks are registered."""
    listener_mock = MagicMock(
        return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock())
    )
    return (
        patch("framework.recorder.event_listener.mouse.Listener", listener_mock),
        patch("framework.recorder.event_listener.keyboard.Listener", listener_mock),
    )


# ===========================================================================
# TEST 1 — workspace creation ensures recordings directory exists
# ===========================================================================

class TestWorkspaceRecordingsDirectory:
    def test_create_workspace_recordings_dir_exists(self, tmp_path: Path) -> None:
        """TEST 1: Creating a workspace creates the recordings sub-directory."""
        ws = WorkspaceService.create(root=tmp_path / "ws1", name="ws1")
        recordings_dir = ws.recordings_dir_for()
        assert recordings_dir.is_dir(), (
            "recordings/ must exist after workspace creation"
        )
        assert recordings_dir == (tmp_path / "ws1" / "recordings").resolve()

    def test_open_workspace_recordings_dir_exists(self, tmp_path: Path) -> None:
        """TEST 1 (open): Opening an existing workspace still exposes recordings dir."""
        WorkspaceService.create(root=tmp_path / "ws2", name="ws2")
        ws = WorkspaceService.load(root=tmp_path / "ws2")
        recordings_dir = ws.recordings_dir_for()
        assert recordings_dir.is_dir()


# ===========================================================================
# TEST 2 — recorder saves inside selected workspace
# ===========================================================================

class TestRecorderSavesInsideWorkspace:
    def test_recording_saved_in_workspace_recordings_dir(self, tmp_path: Path) -> None:
        """TEST 2: RecorderService saves to the workspace recordings directory."""
        from framework.recorder.recorder_service import RecorderService, RecorderState

        ws = WorkspaceService.create(root=tmp_path / "ws3", name="ws3")
        workspace_recordings = ws.recordings_dir_for()

        svc = RecorderService()
        mouse_mock, kb_mock = _mock_pynput()
        with mouse_mock, kb_mock:
            status = svc.start(
                name="Demo_Login_Test",
                recordings_dir=str(workspace_recordings),
            )
            assert status.state == RecorderState.RECORDING
            assert status.error is None

            stop_status = svc.stop()

        assert stop_status.error is None
        assert stop_status.saved_path is not None

        expected = workspace_recordings / "Demo_Login_Test.json"
        assert expected.exists(), f"Expected recording at {expected}"
        assert stop_status.saved_path.resolve() == expected.resolve()

    def test_recording_not_saved_to_project_root(self, tmp_path: Path) -> None:
        """TEST 2 (negative): Recording is NOT saved to the project-root recordings/."""
        from framework.recorder.recorder_service import RecorderService

        ws = WorkspaceService.create(root=tmp_path / "ws4", name="ws4")
        workspace_recordings = ws.recordings_dir_for()

        svc = RecorderService()
        project_root_recordings = Path("recordings")  # relative, would be cwd/recordings

        mouse_mock, kb_mock = _mock_pynput()
        with mouse_mock, kb_mock:
            svc.start(name="flow", recordings_dir=str(workspace_recordings))
            svc.stop()

        # The recording must NOT appear at the project-root recordings path.
        project_file = project_root_recordings / "flow.json"
        assert not project_file.exists(), (
            f"Recording must not be saved to project root: {project_file}"
        )


# ===========================================================================
# TEST 3 — workspace discovery finds saved recording
# ===========================================================================

class TestWorkspaceDiscovery:
    def test_saved_recording_discovered_after_save(self, tmp_path: Path) -> None:
        """TEST 3: A recording saved inside the workspace is found by discovery."""
        ws = WorkspaceService.create(root=tmp_path / "ws5", name="ws5")
        rec_dir = ws.recordings_dir_for()

        # Simulate a saved recording.
        (rec_dir / "my_flow.json").write_text("[]", encoding="utf-8")

        # Reload workspace and discover.
        ws2 = WorkspaceService.load(root=tmp_path / "ws5")
        discovered = list(ws2.recordings_dir_for().glob("*.json"))

        names = [f.stem for f in discovered]
        assert "my_flow" in names, f"Expected 'my_flow' in {names}"


# ===========================================================================
# TEST 4 — refresh workspace keeps recordings visible
# ===========================================================================

class TestWorkspaceRefresh:
    def test_refresh_preserves_recordings(self, tmp_path: Path) -> None:
        """TEST 4: Refreshing workspace does not delete or hide existing recordings."""
        ws = WorkspaceService.create(root=tmp_path / "ws6", name="ws6")
        rec_dir = ws.recordings_dir_for()
        (rec_dir / "keep_me.json").write_text("[]", encoding="utf-8")

        # Simulate refresh (reload + ensure_dirs).
        ws2 = WorkspaceService.load(root=tmp_path / "ws6")
        ws2.ensure_dirs()

        still_there = (rec_dir / "keep_me.json").exists()
        assert still_there, "Refresh must not delete existing recordings"

        refreshed_recordings = list(ws2.recordings_dir_for().glob("*.json"))
        names = [f.stem for f in refreshed_recordings]
        assert "keep_me" in names


# ===========================================================================
# TEST 5 — workspace persistence: load from saved path
# ===========================================================================

class TestWorkspacePersistence:
    def test_workspace_reloads_correctly_from_path(self, tmp_path: Path) -> None:
        """TEST 5: A workspace created at a known path can be reloaded from that path."""
        ws_root = tmp_path / "persisted_ws"
        ws = WorkspaceService.create(root=ws_root, name="persisted_ws")
        (ws.recordings_dir_for() / "existing_test.json").write_text("[]", encoding="utf-8")

        # Simulate a relaunch: reload from the same path.
        ws_reloaded = WorkspaceService.load(root=ws_root)
        assert ws_reloaded.name == "persisted_ws"
        assert ws_reloaded.root == ws_root.resolve()
        recordings = list(ws_reloaded.recordings_dir_for().glob("*.json"))
        assert any(f.stem == "existing_test" for f in recordings)

    def test_missing_workspace_raises_not_found(self, tmp_path: Path) -> None:
        """TEST 5 (robustness): Loading a non-existent workspace raises WorkspaceNotFoundError."""
        from framework.workspace.workspace_service import WorkspaceNotFoundError
        with pytest.raises(WorkspaceNotFoundError):
            WorkspaceService.load(root=tmp_path / "does_not_exist")


# ===========================================================================
# TEST 6 — Open Report opens HTML via default browser
# ===========================================================================

class TestOpenReportDefaultBrowser:
    def test_html_report_opened_via_webbrowser(self, tmp_path: Path) -> None:
        """TEST 6: Opening an HTML file invokes webbrowser.open, not Notepad."""
        from ui.editor_manager import EditorProcessManager

        html_file = tmp_path / "report.html"
        html_file.write_text("<html><body>Report</body></html>", encoding="utf-8")

        manager = EditorProcessManager()
        with patch("ui.editor_manager.webbrowser.open") as mock_open:
            mock_open.return_value = True
            manager.open_file(html_file)

        mock_open.assert_called_once()
        called_url = mock_open.call_args[0][0]
        assert "report.html" in called_url, f"Expected report.html in URL, got: {called_url}"

    def test_html_report_does_not_launch_notepad(self, tmp_path: Path) -> None:
        """TEST 6 (negative): HTML files must NOT launch Notepad."""
        from ui.editor_manager import EditorProcessManager

        html_file = tmp_path / "report.html"
        html_file.write_text("<html></html>", encoding="utf-8")

        manager = EditorProcessManager()
        with patch("ui.editor_manager.webbrowser.open", return_value=True):
            with patch("subprocess.Popen") as mock_popen:
                manager.open_file(html_file)
                # Notepad must NOT have been launched.
                for call in mock_popen.call_args_list:
                    cmd = call[0][0] if call[0] else []
                    assert "notepad" not in str(cmd).lower(), (
                        f"HTML file must not open in Notepad, but Popen was called with: {cmd}"
                    )

    def test_json_file_still_opens_in_editor(self, tmp_path: Path) -> None:
        """TEST 6 (compatibility): Non-HTML files still use the editor (Notepad on Windows)."""
        import platform
        if platform.system().lower() != "windows":
            pytest.skip("Notepad check is Windows-specific")

        from ui.editor_manager import EditorProcessManager

        json_file = tmp_path / "recording.json"
        json_file.write_text("[]", encoding="utf-8")

        manager = EditorProcessManager()
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(poll=MagicMock(return_value=None))
            manager.open_file(json_file)

        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "notepad" in str(cmd).lower(), f"Expected notepad in {cmd}"


# ===========================================================================
# TEST 7 — Open Report missing → graceful error
# ===========================================================================

class TestOpenReportMissing:
    def test_missing_report_raises_file_not_found(self, tmp_path: Path) -> None:
        """TEST 7: EditorProcessManager raises FileNotFoundError for missing files."""
        from ui.editor_manager import EditorProcessManager

        missing = tmp_path / "no_report.html"
        manager = EditorProcessManager()

        with pytest.raises(FileNotFoundError):
            manager.open_file(missing)

    def test_workspace_ui_missing_report_shows_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """TEST 7 (UI): WorkspaceManagementUI shows a status message if no report exists."""
        monkeypatch.setenv("DESKTOP_AUTOMATION_WORKSPACE_ROOT", str(tmp_path / "ws_root"))
        root = _make_tk()
        screen = _build_workspace_screen(root)
        try:
            # No workspace opened, no report exists.
            screen._on_open_report()
            status = screen._status_var.get()
            assert status, "Expected a status message when no report is found"
            # Must not be an empty string or crash
        finally:
            root.destroy()


# ===========================================================================
# TEST 8 — Recording without workspace is refused
# ===========================================================================

class TestRecordingRequiresWorkspace:
    def test_recorder_ui_refuses_start_without_workspace(self) -> None:
        """TEST 8: RecorderUI refuses to start recording when no workspace is selected."""
        root = _make_tk()
        try:
            from ui.recorder_ui import RecorderUI

            # app_controller returns None workspace (no workspace selected)
            mock_controller = MagicMock()
            mock_controller.get_active_workspace.return_value = None

            recorder = RecorderUI(root, app_controller=mock_controller)
            recorder.grid(row=0, column=0)
            root.update_idletasks()

            # Attempt to start with a name set.
            recorder._name_var.set("should_not_start")

            # Directly call _on_start and verify error state.
            from framework.recorder.recorder_service import RecorderState
            recorder._on_start()
            root.update_idletasks()

            # Must still be IDLE.
            assert recorder._service.status.state == RecorderState.IDLE
            # Error must be shown in UI.
            error_text = recorder._error_var.get()
            assert error_text, "Expected an error message when no workspace selected"
            assert "workspace" in error_text.lower(), (
                f"Error should mention 'workspace', got: {error_text!r}"
            )
        finally:
            root.destroy()

    def test_recorder_ui_allows_start_with_workspace(self, tmp_path: Path) -> None:
        """TEST 8 (positive): RecorderUI starts recording when a workspace is available."""
        root = _make_tk()
        try:
            from ui.recorder_ui import RecorderUI
            from framework.recorder.recorder_service import RecorderState

            ws = WorkspaceService.create(root=tmp_path / "ws_for_rec", name="ws_for_rec")

            mock_controller = MagicMock()
            mock_controller.get_active_workspace.return_value = ws

            recorder = RecorderUI(root, app_controller=mock_controller)
            recorder.grid(row=0, column=0)
            root.update_idletasks()

            recorder._name_var.set("test_recording")

            mouse_mock, kb_mock = _mock_pynput()
            with mouse_mock, kb_mock:
                recorder._on_start()
                # Allow the thread to complete.
                import time; time.sleep(0.3)
                root.update()

            # Service should be in RECORDING state (or have transitioned).
            # No workspace-missing error.
            assert recorder._error_var.get() == "" or "workspace" not in recorder._error_var.get().lower()
        finally:
            try:
                # Clean up: stop any active recording before destroying.
                if root.winfo_exists():
                    root.destroy()
            except Exception:
                pass
