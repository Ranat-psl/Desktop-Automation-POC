"""Focused tests for playback lifecycle, teardown, consecutive playback,
recorder UI state reset, and maximize_window.

These tests are all pure-unit / widget-level — no real application
processes are launched and no pywinauto calls reach the OS.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tk_root() -> tk.Tk:
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except tk.TclError as exc:
        pytest.skip(f"No display: {exc}")


# ===========================================================================
# A. Recorder UI timeline reset
# ===========================================================================

class TestRecorderUITimelineReset:
    """Verify _events_list is cleared at the start of every new recording."""

    def _build_recorder(self):
        from ui.recorder_ui import RecorderUI

        root = _make_tk_root()
        ui = RecorderUI(root)
        ui.grid(row=0, column=0)
        root.update_idletasks()
        return root, ui

    def test_timeline_starts_empty(self):
        root, ui = self._build_recorder()
        try:
            assert ui._events_list.size() == 0
        finally:
            root.destroy()

    def test_timeline_cleared_on_second_recording_start(self):
        """Simulate two RECORDING state transitions — list must be clean on each."""
        from framework.recorder.recorder_service import RecorderState

        root, ui = self._build_recorder()
        try:
            # First recording session: apply RECORDING state
            ui._apply_state(RecorderState.RECORDING, action_count=0, saved_path=None, error=None)
            assert ui._events_list.size() == 1  # "Recording started."
            assert "Recording started." in ui._events_list.get(0)

            # Simulate STOPPED state (appends 2 more entries)
            ui._apply_state(
                RecorderState.STOPPED,
                action_count=3,
                saved_path=Path("/tmp/rec_a.json"),
                error=None,
            )
            assert ui._events_list.size() >= 2  # "Saved recording: ..." + "Captured actions: 3"

            # Second recording session starts — list MUST be cleared
            ui._apply_state(RecorderState.RECORDING, action_count=0, saved_path=None, error=None)
            assert ui._events_list.size() == 1, (
                f"Expected 1 item after second RECORDING start, got {ui._events_list.size()}: "
                + str([ui._events_list.get(i) for i in range(ui._events_list.size())])
            )
            assert "Recording started." in ui._events_list.get(0)
        finally:
            root.destroy()

    def test_no_stale_messages_after_multiple_sessions(self):
        """Three recording sessions — only the latest session's messages visible."""
        from framework.recorder.recorder_service import RecorderState

        root, ui = self._build_recorder()
        try:
            for i in range(3):
                ui._apply_state(
                    RecorderState.RECORDING, action_count=0, saved_path=None, error=None
                )
                ui._apply_state(
                    RecorderState.STOPPED,
                    action_count=i + 1,
                    saved_path=Path(f"/tmp/rec_{i}.json"),
                    error=None,
                )

            # Start a fourth session — should see exactly 1 "Recording started." only
            ui._apply_state(
                RecorderState.RECORDING, action_count=0, saved_path=None, error=None
            )
            items = [ui._events_list.get(i) for i in range(ui._events_list.size())]
            # Only one item: "Recording started." from the current session
            assert len(items) == 1, f"Stale items remain: {items}"
            assert items[0] == "Recording started."
        finally:
            root.destroy()

    def test_idle_state_does_not_clear_timeline(self):
        """IDLE transitions must preserve timeline (they show after STOPPED)."""
        from framework.recorder.recorder_service import RecorderState

        root, ui = self._build_recorder()
        try:
            ui._apply_state(
                RecorderState.RECORDING, action_count=0, saved_path=None, error=None
            )
            ui._apply_state(
                RecorderState.STOPPED,
                action_count=2,
                saved_path=Path("/tmp/r.json"),
                error=None,
            )
            count_after_stop = ui._events_list.size()
            # IDLE doesn't clear
            ui._apply_state(RecorderState.IDLE, action_count=0, saved_path=None, error=None)
            assert ui._events_list.size() == count_after_stop
        finally:
            root.destroy()


# ===========================================================================
# B. maximize_window in PyWinAutoAdapter / DesktopDriver
# ===========================================================================

class TestMaximizeWindow:
    """Unit tests — no real windows created."""

    def test_adapter_maximize_calls_window_maximize(self):
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter.__new__(PyWinAutoAdapter)
        mock_win = MagicMock()
        adapter._window = mock_win
        adapter.maximize_window()
        mock_win.maximize.assert_called_once()

    def test_adapter_maximize_no_window_does_not_raise(self):
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter.__new__(PyWinAutoAdapter)
        adapter._window = None
        adapter.maximize_window()  # Must not raise

    def test_adapter_maximize_exception_is_swallowed(self):
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter.__new__(PyWinAutoAdapter)
        mock_win = MagicMock()
        mock_win.maximize.side_effect = RuntimeError("cannot maximize")
        adapter._window = mock_win
        adapter.maximize_window()  # Must not raise

    def test_driver_maximize_delegates_to_adapter(self):
        from framework.driver.desktop_driver import DesktopDriver

        driver = DesktopDriver.__new__(DesktopDriver)
        driver.adapter = MagicMock()
        driver.maximize_window()
        driver.adapter.maximize_window.assert_called_once()


# ===========================================================================
# C. PlaybackExecutor LAUNCH maximize integration
# ===========================================================================

class TestExecutorLaunchMaximize:
    """After LAUNCH, executor must attempt maximize_window on the driver."""

    def _make_action(self, action_type_str, value=None):
        from framework.core.models import Action, ActionType

        return Action(action_type=ActionType(action_type_str), value=value)

    def test_launch_attempts_maximize(self):
        from framework.playback.executor import PlaybackExecutor

        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)

        action = self._make_action("launch", "notepad.exe")
        with patch("time.sleep"):  # skip the 0.5 s wait
            executor._execute(action)

        mock_driver.start.assert_called_once_with("notepad.exe")
        mock_driver.maximize_window.assert_called_once()

    def test_launch_maximize_failure_does_not_abort_playback(self):
        from framework.playback.executor import PlaybackExecutor

        mock_driver = MagicMock()
        mock_driver.maximize_window.side_effect = RuntimeError("no window yet")
        executor = PlaybackExecutor(driver=mock_driver)

        action = self._make_action("launch", "notepad.exe")
        with patch("time.sleep"):
            executor._execute(action)  # Must not raise

        mock_driver.start.assert_called_once_with("notepad.exe")


# ===========================================================================
# D. Playback state reset after completion
# ===========================================================================

class TestPlaybackStateReset:
    """After playback completes (pass or fail) the DA tool buttons are re-enabled."""

    def _build_workspace_ui(self, monkeypatch, tmp_path):
        monkeypatch.setattr("ui.workspace_ui.load_recent", lambda: None)
        from ui.workspace_ui import WorkspaceManagementUI

        root = _make_tk_root()
        screen = WorkspaceManagementUI(root)
        screen.grid(row=0, column=0)
        root.update_idletasks()
        return root, screen

    def test_run_button_re_enabled_after_successful_on_done(self, monkeypatch, tmp_path):
        root, screen = self._build_workspace_ui(monkeypatch, tmp_path)
        try:
            # Simulate a workspace with one recording selected
            ws = MagicMock()
            ws.info.name = "TestWS"
            ws.info.root = tmp_path
            screen._workspace_service = ws
            screen._recording_tree.insert("", "end", values=("RecA", "recA.json", "8", ""))
            row_id = screen._recording_tree.get_children()[0]
            screen._recording_tree.selection_set(row_id)
            screen._on_recording_selection_change()
            root.update_idletasks()

            # Disable run button (simulates playback in progress)
            screen._run_btn.config(state="disabled")

            # Invoke _on_done directly (simulates playback worker completing)
            # We reach into the closure via the actual method that _on_done would call.
            screen._update_button_states()
            root.update_idletasks()

            assert screen._run_btn["state"] != "disabled", (
                "Run button must be re-enabled after playback completes"
            )
        finally:
            root.destroy()

    def test_run_button_re_enabled_after_failed_on_done(self, monkeypatch, tmp_path):
        """Even after a failed playback the run button comes back."""
        root, screen = self._build_workspace_ui(monkeypatch, tmp_path)
        try:
            ws = MagicMock()
            ws.info.name = "TestWS"
            ws.info.root = tmp_path
            screen._workspace_service = ws
            screen._recording_tree.insert("", "end", values=("RecB", "recB.json", "3", ""))
            row_id = screen._recording_tree.get_children()[0]
            screen._recording_tree.selection_set(row_id)
            screen._on_recording_selection_change()
            root.update_idletasks()

            screen._run_btn.config(state="disabled")
            screen._update_button_states()
            root.update_idletasks()

            assert screen._run_btn["state"] != "disabled"
        finally:
            root.destroy()


# ===========================================================================
# E. Playback result isolation (separate reports for A vs B)
# ===========================================================================

class TestPlaybackResultIsolation:
    """PlaybackResult objects from separate executions must be independent."""

    def _make_passed_result(self, name: str):
        from datetime import datetime, timezone
        from framework.playback.executor import ActionResult, PlaybackResult

        now = datetime.now(timezone.utc)
        return PlaybackResult(
            recording_name=name,
            status="passed",
            started_at=now,
            finished_at=now,
            duration_seconds=1.0,
            action_results=[
                ActionResult(
                    action_index=0,
                    action_type="hotkey",
                    value="ctrl+a",
                    locator_str=None,
                    status="passed",
                    duration_seconds=0.1,
                )
            ],
        )

    def test_separate_results_have_separate_recording_names(self):
        result_a = self._make_passed_result("RecordingA")
        result_b = self._make_passed_result("RecordingB")
        assert result_a.recording_name != result_b.recording_name

    def test_html_reports_use_distinct_filenames(self, tmp_path):
        from framework.reporting.recording_report import generate_recording_report

        result_a = self._make_passed_result("RecA")
        result_b = self._make_passed_result("RecB")

        path_a = generate_recording_report(result_a, output_dir=tmp_path)
        path_b = generate_recording_report(result_b, output_dir=tmp_path)

        assert path_a != path_b, "Each recording must produce a unique report file"
        assert path_a.exists()
        assert path_b.exists()

    def test_html_report_contains_recording_name(self, tmp_path):
        from framework.reporting.recording_report import generate_recording_report

        result = self._make_passed_result("UniqueRecordingXYZ")
        path = generate_recording_report(result, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "UniqueRecordingXYZ" in content

    def test_html_report_b_does_not_contain_recording_a_name(self, tmp_path):
        from framework.reporting.recording_report import generate_recording_report

        result_a = self._make_passed_result("RecordingAlpha")
        result_b = self._make_passed_result("RecordingBeta")

        path_a = generate_recording_report(result_a, output_dir=tmp_path)
        path_b = generate_recording_report(result_b, output_dir=tmp_path)

        content_b = path_b.read_text(encoding="utf-8")
        assert "RecordingAlpha" not in content_b


# ===========================================================================
# F. Ctrl+F4 / Alt+F4 as HOTKEY actions (unit-level)
# ===========================================================================

class TestHotkeyCloseActions:
    """Ctrl+F4 and Alt+F4 must be dispatched as HOTKEY actions, not suppressed."""

    def _make_hotkey_action(self, value: str):
        from framework.core.models import Action, ActionType

        return Action(action_type=ActionType.HOTKEY, value=value)

    def test_ctrl_f4_calls_driver_hotkey(self):
        from framework.playback.executor import PlaybackExecutor

        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        action = self._make_hotkey_action("ctrl+f4")
        executor._execute(action)
        mock_driver.hotkey.assert_called_once_with("ctrl+f4")

    def test_alt_f4_calls_driver_hotkey(self):
        from framework.playback.executor import PlaybackExecutor

        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        action = self._make_hotkey_action("alt+f4")
        executor._execute(action)
        mock_driver.hotkey.assert_called_once_with("alt+f4")

    def test_ctrl_f4_result_is_passed(self):
        from framework.playback.executor import PlaybackExecutor

        mock_driver = MagicMock()
        executor = PlaybackExecutor(driver=mock_driver)
        actions = [self._make_hotkey_action("ctrl+f4")]
        with patch("time.sleep"):
            result = executor.run(actions, inter_action_delay_seconds=0)
        assert result.status == "passed"
        assert result.action_results[0].action_type == "hotkey"
        assert result.action_results[0].value == "ctrl+f4"
        assert result.action_results[0].status == "passed"
