"""Integration tests for the end-to-end playback pipeline.

These tests validate the full chain:
  RecordingStore.load() → PlaybackExecutor.run() → DesktopDriver.click()
                        → PyWinAutoAdapter.click() → _sendinput_click()

No real Windows UI is launched.  The adapter's _sendinput_click and ctypes
calls are mocked so the tests run in any environment (CI, headless, etc.).

Test scenario mirrors the real-world recording reported by the user:
  [
    { action_type: "click", locator: {by:"auto_id", value:"SearchButton"},
      metadata: {recorded_x:325, recorded_y:1161} },
    { action_type: "click", locator: {by:"control_type", value:"Pane"},
      metadata: {recorded_x:191, recorded_y:356} }
  ]

Root causes verified by these tests:
  BUG-1/2  Semantic resolution is NOT attempted when coords are present —
           avoids attaching to the wrong foreground window.
  BUG-3    Inter-action delay is inserted between actions so opened windows
           can render before the next click fires.
  BUG-4    Generic locator (control_type=Pane) does not cause wrong control
           to be clicked when coords are available.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from framework.core.models import Action, ActionType, Locator
from framework.driver.desktop_driver import DesktopDriver
from framework.driver.pywinauto_adapter import PyWinAutoAdapter
from framework.playback.executor import PlaybackExecutor
from framework.recorder.recording_store import RecordingStore


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SEARCH_BUTTON_ACTION = Action(
    action_type=ActionType.CLICK,
    locator=Locator(by="auto_id", value="SearchButton"),
    metadata={"recorded_x": 325, "recorded_y": 1161},
)

PANE_ACTION = Action(
    action_type=ActionType.CLICK,
    locator=Locator(by="control_type", value="Pane"),
    metadata={"recorded_x": 191, "recorded_y": 356},
)

NOTEPAD_TYPE_ACTION = Action(
    action_type=ActionType.TYPE,
    locator=Locator(by="auto_id", value="Edit"),
    value="test automation",
)


def _make_adapter() -> PyWinAutoAdapter:
    adapter = PyWinAutoAdapter()
    adapter._window = MagicMock()
    return adapter


# ===========================================================================
# A. Adapter — coords bypass semantic resolution (BUG-1 / BUG-2 / BUG-4)
# ===========================================================================


class TestAdapterClickWithCoords:
    """When coords are provided, _resolve_control must NEVER be called."""

    def test_auto_id_locator_with_coords_uses_sendinput_not_resolve(self) -> None:
        adapter = _make_adapter()
        with patch.object(adapter, "_resolve_control") as mock_resolve, \
             patch.object(adapter, "_sendinput_click") as mock_send:
            adapter.click(SEARCH_BUTTON_ACTION.locator, coords=(325, 1161))
        mock_resolve.assert_not_called()
        mock_send.assert_called_once_with(325, 1161)

    def test_pane_locator_with_coords_uses_sendinput_not_resolve(self) -> None:
        """BUG-4 regression: control_type=Pane must not be resolved semantically."""
        adapter = _make_adapter()
        with patch.object(adapter, "_resolve_control") as mock_resolve, \
             patch.object(adapter, "_sendinput_click") as mock_send:
            adapter.click(PANE_ACTION.locator, coords=(191, 356))
        mock_resolve.assert_not_called()
        mock_send.assert_called_once_with(191, 356)

    def test_no_coords_falls_back_to_semantic(self) -> None:
        """Without coords, semantic resolution is still the path for reliable locators."""
        adapter = _make_adapter()
        mock_control = MagicMock()
        with patch.object(adapter, "_resolve_control", return_value=mock_control) as mock_resolve, \
             patch.object(adapter, "_invoke_click") as mock_invoke:
            adapter.click(Locator(by="auto_id", value="OKButton"), coords=None)
        mock_resolve.assert_called_once()
        mock_invoke.assert_called_once_with(mock_control)

    def test_sendinput_called_with_exact_recorded_coords(self) -> None:
        """Verify the precise coordinates pass through unchanged."""
        adapter = _make_adapter()
        captured: list[tuple[int, int]] = []

        def _fake_send(x, y):
            captured.append((x, y))

        with patch.object(adapter, "_sendinput_click", side_effect=_fake_send):
            adapter.click(SEARCH_BUTTON_ACTION.locator, coords=(325, 1161))
            adapter.click(PANE_ACTION.locator, coords=(191, 356))

        assert captured == [(325, 1161), (191, 356)]


# ===========================================================================
# B. Executor — coords extracted from metadata and forwarded (BUG-1)
# ===========================================================================


class TestExecutorCoordsExtraction:
    def test_click_with_metadata_forwards_coords_to_driver(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(SEARCH_BUTTON_ACTION)
        driver.click.assert_called_once_with(
            Locator(by="auto_id", value="SearchButton"),
            coords=(325, 1161),
        )

    def test_generic_pane_click_forwards_coords_to_driver(self, tmp_path: Path) -> None:
        """BUG-4 regression: Pane + coords must reach the driver as coords."""
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(PANE_ACTION)
        driver.click.assert_called_once_with(
            Locator(by="control_type", value="Pane"),
            coords=(191, 356),
        )

    def test_click_without_metadata_sends_coords_none(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        action = Action(
            action_type=ActionType.CLICK,
            locator=Locator(by="auto_id", value="OKButton"),
        )
        executor._execute(action)
        driver.click.assert_called_once_with(
            Locator(by="auto_id", value="OKButton"),
            coords=None,
        )


# ===========================================================================
# C. Executor.run — inter-action delay inserted (BUG-3)
# ===========================================================================


class TestExecutorInterActionDelay:
    def test_delay_inserted_between_actions(self, tmp_path: Path) -> None:
        """BUG-3 regression: sleep must be called between actions."""
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        actions = [SEARCH_BUTTON_ACTION, PANE_ACTION]

        sleep_calls: list[float] = []
        original_sleep = time.sleep

        def _fake_sleep(secs):
            sleep_calls.append(secs)

        with patch("framework.playback.executor.time") as mock_time:
            mock_time.sleep = _fake_sleep
            executor.run(actions, inter_action_delay_seconds=1.0)

        # One sleep between the two actions.
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 1.0

    def test_no_delay_after_last_action(self, tmp_path: Path) -> None:
        """No sleep after the final action to avoid unnecessary wait."""
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        actions = [SEARCH_BUTTON_ACTION]

        sleep_calls: list[float] = []
        with patch("framework.playback.executor.time") as mock_time:
            mock_time.sleep = lambda secs: sleep_calls.append(secs)
            executor.run(actions, inter_action_delay_seconds=1.0)

        assert sleep_calls == []

    def test_zero_delay_skips_sleep(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        actions = [SEARCH_BUTTON_ACTION, PANE_ACTION]

        sleep_calls: list[float] = []
        with patch("framework.playback.executor.time") as mock_time:
            mock_time.sleep = lambda secs: sleep_calls.append(secs)
            executor.run(actions, inter_action_delay_seconds=0)

        assert sleep_calls == []


# ===========================================================================
# D. Full pipeline — RecordingStore → Executor → Adapter (coord flow)
# ===========================================================================


class TestFullPlaybackPipeline:
    """End-to-end: load JSON → executor → adapter coord path, no real Windows."""

    def _recording_json(self, tmp_path: Path) -> Path:
        data = [
            {
                "action_type": "click",
                "locator": {"by": "auto_id", "value": "SearchButton"},
                "value": None,
                "timeout_seconds": None,
                "metadata": {"recorded_x": 325, "recorded_y": 1161},
            },
            {
                "action_type": "click",
                "locator": {"by": "control_type", "value": "Pane"},
                "value": None,
                "timeout_seconds": None,
                "metadata": {"recorded_x": 191, "recorded_y": 356},
            },
        ]
        p = tmp_path / "ATestRecord1.json"
        p.write_text(json.dumps(data))
        return p

    def test_pipeline_loads_and_executes_with_coords(self, tmp_path: Path) -> None:
        """Simulate exactly what Run Recording does: load JSON, run executor."""
        json_path = self._recording_json(tmp_path)
        store = RecordingStore(base_dir=tmp_path)
        actions = store.load("ATestRecord1")

        assert len(actions) == 2
        assert actions[0].metadata["recorded_x"] == 325
        assert actions[1].metadata["recorded_x"] == 191

        adapter = PyWinAutoAdapter()
        adapter._window = MagicMock()
        driver = DesktopDriver()
        driver.adapter = adapter

        sendinput_calls: list[tuple[int, int]] = []

        def _fake_sendinput(x, y):
            sendinput_calls.append((x, y))

        resolve_calls = []

        with patch.object(adapter, "_sendinput_click", side_effect=_fake_sendinput), \
             patch.object(adapter, "_resolve_control", side_effect=lambda loc: resolve_calls.append(loc)) as mock_resolve, \
             patch("framework.playback.executor.time") as mock_time:
            mock_time.sleep = lambda s: None
            executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
            executor.run(actions, inter_action_delay_seconds=0)

        # Both coords should reach SendInput in order.
        assert sendinput_calls == [(325, 1161), (191, 356)]
        # Semantic resolution must NOT have been called for either action.
        assert mock_resolve.call_count == 0, (
            "_resolve_control was called — this means BUG-2/4 is still active"
        )

    def test_notepad_type_still_uses_semantic_resolution(self, tmp_path: Path) -> None:
        """TYPE actions have no coords; semantic resolution must still work.

        type_into now uses pynput Controller.type() instead of type_keys,
        so we verify pynput is called with the correct text after resolution.
        """
        adapter = PyWinAutoAdapter()
        adapter._window = MagicMock()
        mock_control = MagicMock()
        driver = DesktopDriver()
        driver.adapter = adapter

        with patch.object(adapter, "_resolve_control", return_value=mock_control) as mock_resolve, \
             patch("pynput.keyboard.Controller") as mock_kb:
            adapter.type_text(Locator(by="auto_id", value="Edit"), "test automation")

        mock_resolve.assert_called_once()
        # type_into now uses pynput (not type_keys) for reliable WinUI3 support.
        mock_kb.return_value.type.assert_called_once_with("test automation")
        mock_control.type_keys.assert_not_called()


# ===========================================================================
# E. Workspace UI — playback runs on a background thread (BUG-1)
# ===========================================================================


class TestWorkspaceUIPlaybackThread:
    """Verify _run_recording_async dispatches work to a daemon thread."""

    def test_playback_runs_on_background_thread_not_main(self, tmp_path: Path, monkeypatch) -> None:
        """The driver.click calls must happen on a non-main thread."""
        import tkinter as tk
        from ui.workspace_ui import WorkspaceManagementUI, RecordingItem

        root = tk.Tk()
        root.withdraw()
        try:
            screen = WorkspaceManagementUI(master=root)

            item = RecordingItem(
                test_name="ATestRecord1",
                json_path=tmp_path / "ATestRecord1.json",
                source="workspace",
            )

            actions = [SEARCH_BUTTON_ACTION]
            thread_ids: list[int] = []
            done_event = threading.Event()

            original_run = PlaybackExecutor.run

            def _spy_run(self_exec, acts, **kwargs):
                thread_ids.append(threading.get_ident())
                done_event.set()

            monkeypatch.setattr(PlaybackExecutor, "run", _spy_run)
            monkeypatch.setattr("framework.driver.desktop_driver.DesktopDriver.quit", lambda s: None)

            screen._run_recording_async(item, actions)
            done_event.wait(timeout=3.0)

            assert thread_ids, "Playback thread never ran"
            assert thread_ids[0] != threading.main_thread().ident, (
                "Playback ran on the main thread — BUG-1 is still active"
            )
        finally:
            root.destroy()
