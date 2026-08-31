"""Regression tests for active-window auto-connect in PyWinAutoAdapter.

Covers:
  - _ensure_window() is a no-op when self._window is already set.
  - _ensure_window() connects to the foreground window when self._window is None.
  - _resolve_control() calls _ensure_window() before locator resolution.
  - When _ensure_window() fails, RuntimeError propagates correctly to the
    PlaybackExecutor error handler (screenshot mechanism remains intact).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from framework.core.models import Action, ActionType, Locator
from framework.driver.pywinauto_adapter import PyWinAutoAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter() -> PyWinAutoAdapter:
    """Return an adapter with the pywinauto Application constructor stubbed out."""
    return PyWinAutoAdapter(backend="uia")


def _make_window_mock(text: str = "Test Window") -> MagicMock:
    win = MagicMock()
    win.window_text.return_value = text
    win.process_id.return_value = 9999
    return win


# ---------------------------------------------------------------------------
# _ensure_window — no-op when window already set
# ---------------------------------------------------------------------------

class TestEnsureWindowNoOp:
    def test_noop_when_window_already_set(self) -> None:
        """_ensure_window must not replace an already-established window."""
        adapter = _make_adapter()
        existing_window = _make_window_mock("Existing")
        adapter._window = existing_window

        # Should return without touching _window.
        adapter._ensure_window()

        assert adapter._window is existing_window

    def test_noop_does_not_call_ctypes(self) -> None:
        adapter = _make_adapter()
        adapter._window = _make_window_mock()

        with patch("ctypes.windll") as mock_windll:
            adapter._ensure_window()
            mock_windll.user32.GetForegroundWindow.assert_not_called()


# ---------------------------------------------------------------------------
# _ensure_window — connects to foreground window when _window is None
# ---------------------------------------------------------------------------

class TestEnsureWindowAutoConnect:
    def test_connects_to_foreground_hwnd(self) -> None:
        """_ensure_window should call GetForegroundWindow and connect via hwnd."""
        adapter = _make_adapter()
        assert adapter._window is None

        mock_window = _make_window_mock("Foreground Window")
        mock_app = MagicMock()
        mock_app.top_window.return_value = mock_window

        with patch("ctypes.windll") as mock_windll, \
             patch("framework.driver.pywinauto_adapter.Application") as MockApp:
            mock_windll.user32.GetForegroundWindow.return_value = 12345
            MockApp.return_value.connect.return_value = mock_app

            adapter._ensure_window()

        assert adapter._window is mock_window
        MockApp.return_value.connect.assert_called_once_with(handle=12345)

    def test_records_window_pid(self) -> None:
        """_ensure_window should populate _window_pid from the connected window."""
        adapter = _make_adapter()

        mock_window = _make_window_mock()
        mock_window.process_id.return_value = 4242
        mock_app = MagicMock()
        mock_app.top_window.return_value = mock_window

        with patch("ctypes.windll") as mock_windll, \
             patch("framework.driver.pywinauto_adapter.Application") as MockApp:
            mock_windll.user32.GetForegroundWindow.return_value = 999
            MockApp.return_value.connect.return_value = mock_app
            adapter._ensure_window()

        assert adapter._window_pid == 4242

    def test_null_hwnd_raises_runtime_error(self) -> None:
        """_ensure_window raises RuntimeError when GetForegroundWindow returns 0."""
        adapter = _make_adapter()

        with patch("ctypes.windll") as mock_windll:
            mock_windll.user32.GetForegroundWindow.return_value = 0

            with pytest.raises(RuntimeError, match="foreground window"):
                adapter._ensure_window()

    def test_connect_failure_raises_runtime_error(self) -> None:
        """_ensure_window wraps pywinauto connect failures as RuntimeError."""
        adapter = _make_adapter()

        with patch("ctypes.windll") as mock_windll, \
             patch("framework.driver.pywinauto_adapter.Application") as MockApp:
            mock_windll.user32.GetForegroundWindow.return_value = 1
            MockApp.return_value.connect.side_effect = Exception("connect failed")

            with pytest.raises(RuntimeError, match="auto-connect"):
                adapter._ensure_window()

    def test_window_is_idempotent_on_second_call(self) -> None:
        """After first successful auto-connect, second call is a no-op."""
        adapter = _make_adapter()

        mock_window = _make_window_mock()
        mock_app = MagicMock()
        mock_app.top_window.return_value = mock_window

        with patch("ctypes.windll") as mock_windll, \
             patch("framework.driver.pywinauto_adapter.Application") as MockApp:
            mock_windll.user32.GetForegroundWindow.return_value = 1
            MockApp.return_value.connect.return_value = mock_app

            adapter._ensure_window()
            adapter._ensure_window()  # second call

        # connect should have been called exactly once.
        assert MockApp.return_value.connect.call_count == 1


# ---------------------------------------------------------------------------
# _resolve_control — calls _ensure_window before locating
# ---------------------------------------------------------------------------

class TestResolveControlEnsuresWindow:
    def test_resolve_control_calls_ensure_window(self) -> None:
        """_resolve_control must invoke _ensure_window before looking up the control."""
        adapter = _make_adapter()

        mock_control = MagicMock()
        mock_window = MagicMock()
        mock_window.window_text.return_value = "Win"
        # WindowSpecification path: has child_window.
        # Production code calls child_window(**kwargs).wrapper_object(), so the
        # mock must reflect that chain: child_window() returns a spec whose
        # wrapper_object() returns the expected control.
        mock_child_spec = MagicMock()
        mock_child_spec.wrapper_object.return_value = mock_control
        mock_window.child_window.return_value = mock_child_spec

        call_log: list[str] = []

        def _fake_ensure():
            call_log.append("ensure_window")
            adapter._window = mock_window

        adapter._ensure_window = _fake_ensure

        locator = Locator(by="auto_id", value="OkButton")
        result = adapter._resolve_control(locator)

        assert "ensure_window" in call_log
        assert result is mock_control

    def test_resolve_control_propagates_ensure_window_error(self) -> None:
        """If _ensure_window raises, _resolve_control lets the error propagate."""
        adapter = _make_adapter()
        adapter._ensure_window = MagicMock(
            side_effect=RuntimeError("No foreground window")
        )

        with pytest.raises(RuntimeError, match="No foreground window"):
            adapter._resolve_control(Locator(by="auto_id", value="X"))


# ---------------------------------------------------------------------------
# PlaybackExecutor integration — screenshot fires on window-connect failure
# ---------------------------------------------------------------------------

class TestPlaybackScreenshotOnWindowFailure:
    def test_screenshot_captured_when_ensure_window_fails(self, tmp_path: Path) -> None:
        """PlaybackExecutor must still capture a failure screenshot when the
        active-window auto-connect itself raises RuntimeError."""
        from framework.driver.desktop_driver import DesktopDriver
        from framework.playback.executor import PlaybackExecutor
        from framework.core.exceptions import PlaybackExecutionError

        driver = DesktopDriver()
        # Force _ensure_window to fail so _resolve_control raises.
        driver.adapter._ensure_window = MagicMock(
            side_effect=RuntimeError("simulated: no foreground window")
        )

        executor = PlaybackExecutor(
            driver=driver,
            recording_name="test_recording",
            screenshot_dir=tmp_path,
        )

        actions = [
            Action(
                action_type=ActionType.CLICK,
                locator=Locator(by="auto_id", value="SearchButton"),
            )
        ]

        screenshot_called: list[bool] = []

        original_try = executor._try_capture_screenshot

        def _patched_capture(idx, act):
            screenshot_called.append(True)
            return original_try(idx, act)

        executor._try_capture_screenshot = _patched_capture

        with pytest.raises(PlaybackExecutionError, match="simulated: no foreground window"):
            executor.run(actions)

        assert screenshot_called, "Screenshot capture must be attempted after action failure"
