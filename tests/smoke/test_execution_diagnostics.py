"""Day 9 — Execution Diagnostics focused tests.

Tests for:
- Failure screenshot is created when a playback action fails.
- Original exception is preserved when screenshot capture itself fails.
- User-friendly error message contains full action context.
- HTML report configuration does not break existing pytest execution.

All tests mock ``_capture_via_powershell`` so no real PowerShell or desktop
session is required.  The driver is mocked so no Windows UI is launched.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from framework.core.exceptions import PlaybackExecutionError
from framework.core.models import Action, ActionType, Locator
from framework.playback.executor import PlaybackExecutor


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _failing_driver(exc: Exception | None = None) -> MagicMock:
    """Return a MagicMock driver whose click/type_text raise *exc*."""
    driver = MagicMock()
    error = exc if exc is not None else RuntimeError("target element not found")
    driver.click.side_effect = error
    driver.type_text.side_effect = error
    return driver


def _click_action(target: str = "SaveButton") -> Action:
    return Action(action_type=ActionType.CLICK, locator=Locator(by="auto_id", value=target))


def _type_action(target: str = "Editor", text: str = "hello") -> Action:
    return Action(action_type=ActionType.TYPE, locator=Locator(by="auto_id", value=target), value=text)


def _fake_powershell_capture(output_path: Path) -> None:
    """Simulate a successful screenshot by writing a minimal fake PNG."""
    output_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes


# ===========================================================================
# A. Failure Screenshot
# ===========================================================================


class TestFailureScreenshot:
    """Screenshot file is created and stored correctly on playback failure."""

    def test_screenshot_created_in_expected_directory(self, tmp_path: Path) -> None:
        ss_dir = tmp_path / "screenshots"

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            executor = PlaybackExecutor(
                driver=_failing_driver(),
                recording_name="my_recording",
                screenshot_dir=ss_dir,
            )
            with pytest.raises(PlaybackExecutionError):
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

        screenshots = list(ss_dir.glob("*.png"))
        assert len(screenshots) == 1, f"Expected 1 screenshot, found: {screenshots}"

    def test_screenshot_filename_contains_recording_and_action_type(
        self, tmp_path: Path
    ) -> None:
        ss_dir = tmp_path / "screenshots"

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            executor = PlaybackExecutor(
                driver=_failing_driver(),
                recording_name="login_flow",
                screenshot_dir=ss_dir,
            )
            with pytest.raises(PlaybackExecutionError):
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

        names = [f.name for f in ss_dir.glob("*.png")]
        assert names, "No screenshots created"
        assert "login_flow" in names[0], f"Recording name missing from filename: {names[0]}"
        assert "click" in names[0].lower(), f"Action type missing from filename: {names[0]}"
        assert "action1" in names[0].lower(), f"Action index missing from filename: {names[0]}"

    def test_screenshot_contains_data(self, tmp_path: Path) -> None:
        ss_dir = tmp_path / "screenshots"

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            executor = PlaybackExecutor(driver=_failing_driver(), screenshot_dir=ss_dir)
            with pytest.raises(PlaybackExecutionError):
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

        screenshot = next(ss_dir.glob("*.png"))
        assert screenshot.stat().st_size > 0, "Screenshot file is empty"

    def test_screenshot_dir_created_automatically(self, tmp_path: Path) -> None:
        deep_dir = tmp_path / "a" / "b" / "c" / "screenshots"
        assert not deep_dir.exists()

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            executor = PlaybackExecutor(driver=_failing_driver(), screenshot_dir=deep_dir)
            with pytest.raises(PlaybackExecutionError):
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

        assert deep_dir.exists()


# ===========================================================================
# B. Exception Preservation
# ===========================================================================


class TestExceptionPreservation:
    """Original exception must survive regardless of screenshot outcome."""

    def test_original_exception_chained_as_cause(self, tmp_path: Path) -> None:
        original = RuntimeError("specific original failure")

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            executor = PlaybackExecutor(
                driver=_failing_driver(exc=original),
                screenshot_dir=tmp_path / "ss",
            )
            with pytest.raises(PlaybackExecutionError) as exc_info:
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

        assert exc_info.value.__cause__ is original

    def test_playback_error_raised_when_screenshot_capture_fails(
        self, tmp_path: Path
    ) -> None:
        """PlaybackExecutionError is raised even when the screenshot subsystem fails."""
        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=RuntimeError("PowerShell unavailable"),
        ):
            executor = PlaybackExecutor(
                driver=_failing_driver(),
                screenshot_dir=tmp_path / "ss",
            )
            with pytest.raises(PlaybackExecutionError):
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

    def test_no_screenshot_when_capture_fails(self, tmp_path: Path) -> None:
        ss_dir = tmp_path / "ss"

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=RuntimeError("PowerShell unavailable"),
        ):
            executor = PlaybackExecutor(driver=_failing_driver(), screenshot_dir=ss_dir)
            with pytest.raises(PlaybackExecutionError):
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

        assert not ss_dir.exists() or not list(ss_dir.glob("*.png"))

    def test_original_cause_is_chained_even_when_screenshot_fails(
        self, tmp_path: Path
    ) -> None:
        original = ValueError("the real root cause")

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=RuntimeError("screenshot system down"),
        ):
            executor = PlaybackExecutor(
                driver=_failing_driver(exc=original),
                screenshot_dir=tmp_path / "ss",
            )
            with pytest.raises(PlaybackExecutionError) as exc_info:
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

        assert exc_info.value.__cause__ is original


# ===========================================================================
# C. User-Friendly Error Message
# ===========================================================================


class TestUserFriendlyErrorMessage:
    """The raised PlaybackExecutionError carries human-readable context."""

    def _run_and_get_message(
        self,
        tmp_path: Path,
        action: Action,
        recording_name: str | None = None,
        driver: MagicMock | None = None,
    ) -> str:
        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            executor = PlaybackExecutor(
                driver=driver or _failing_driver(),
                recording_name=recording_name,
                screenshot_dir=tmp_path / "ss",
            )
            with pytest.raises(PlaybackExecutionError) as exc_info:
                executor.run([action], retry_attempts=1, retry_delay_seconds=0)
        return str(exc_info.value)

    def test_message_contains_action_number(self, tmp_path: Path) -> None:
        msg = self._run_and_get_message(tmp_path, _click_action())
        assert "Action 1" in msg

    def test_message_contains_action_type_uppercase(self, tmp_path: Path) -> None:
        msg = self._run_and_get_message(tmp_path, _click_action())
        assert "CLICK" in msg

    def test_message_contains_locator_target(self, tmp_path: Path) -> None:
        msg = self._run_and_get_message(tmp_path, _click_action("ConfirmButton"))
        assert "ConfirmButton" in msg

    def test_message_contains_recording_name(self, tmp_path: Path) -> None:
        msg = self._run_and_get_message(tmp_path, _click_action(), recording_name="checkout_flow")
        assert "checkout_flow" in msg

    def test_message_contains_failure_reason(self, tmp_path: Path) -> None:
        driver = _failing_driver(exc=RuntimeError("element not found in UI tree"))
        msg = self._run_and_get_message(tmp_path, _click_action(), driver=driver)
        assert "element not found in UI tree" in msg

    def test_message_contains_screenshot_path(self, tmp_path: Path) -> None:
        msg = self._run_and_get_message(tmp_path, _click_action())
        assert "Failure screenshot:" in msg

    def test_message_no_screenshot_when_capture_fails(self, tmp_path: Path) -> None:
        """When screenshot fails, message omits the screenshot line gracefully."""
        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=RuntimeError("no capture"),
        ):
            executor = PlaybackExecutor(
                driver=_failing_driver(),
                screenshot_dir=tmp_path / "ss",
            )
            with pytest.raises(PlaybackExecutionError) as exc_info:
                executor.run([_click_action()], retry_attempts=1, retry_delay_seconds=0)

        msg = str(exc_info.value)
        assert "Action 1" in msg
        assert "CLICK" in msg
        assert "Failure screenshot:" not in msg

    def test_message_without_recording_name_still_structured(self, tmp_path: Path) -> None:
        msg = self._run_and_get_message(tmp_path, _click_action(), recording_name=None)
        assert "Action 1" in msg
        assert "CLICK" in msg
        assert "Reason:" in msg

    def test_message_second_action_shows_action_2(self, tmp_path: Path) -> None:
        """Action index increments correctly for the second action in the list."""
        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            driver = MagicMock()
            driver.click.return_value = None  # first action succeeds
            driver.type_text.side_effect = RuntimeError("field locked")

            executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path / "ss")
            with pytest.raises(PlaybackExecutionError) as exc_info:
                executor.run(
                    [_click_action(), _type_action()],
                    retry_attempts=1,
                    retry_delay_seconds=0,
                )

        assert "Action 2" in str(exc_info.value)


# ===========================================================================
# D. Screenshot module unit tests
# ===========================================================================


class TestScreenshotModule:
    """Unit tests for framework.reporting.screenshot standalone functions."""

    def test_capture_returns_path_object(self, tmp_path: Path) -> None:
        from framework.reporting.screenshot import capture_failure_screenshot

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            result = capture_failure_screenshot(output_dir=tmp_path, prefix="testrun")

        assert isinstance(result, Path)

    def test_capture_uses_prefix_in_filename(self, tmp_path: Path) -> None:
        from framework.reporting.screenshot import capture_failure_screenshot

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            result = capture_failure_screenshot(output_dir=tmp_path, prefix="myprefix")

        assert "myprefix" in result.name

    def test_capture_creates_png_extension(self, tmp_path: Path) -> None:
        from framework.reporting.screenshot import capture_failure_screenshot

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            result = capture_failure_screenshot(output_dir=tmp_path, prefix="p")

        assert result.suffix == ".png"

    def test_capture_creates_nested_directory(self, tmp_path: Path) -> None:
        from framework.reporting.screenshot import capture_failure_screenshot

        nested = tmp_path / "a" / "b" / "shots"

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=_fake_powershell_capture,
        ):
            capture_failure_screenshot(output_dir=nested, prefix="x")

        assert nested.exists()

    def test_capture_raises_on_powershell_failure(self, tmp_path: Path) -> None:
        from framework.reporting.screenshot import capture_failure_screenshot

        with patch(
            "framework.reporting.screenshot._capture_via_powershell",
            side_effect=RuntimeError("PS failed"),
        ):
            with pytest.raises(RuntimeError):
                capture_failure_screenshot(output_dir=tmp_path, prefix="fail")

    def test_sanitise_removes_special_chars(self) -> None:
        from framework.reporting.screenshot import _sanitise

        result = _sanitise("my recording/flow:test 1")
        assert "/" not in result
        assert ":" not in result
        assert " " not in result

    def test_sanitise_truncates_to_64(self) -> None:
        from framework.reporting.screenshot import _sanitise

        long_name = "a" * 100
        result = _sanitise(long_name)
        assert len(result) <= 64


# ===========================================================================
# E. Adapter process lifecycle safety
# ===========================================================================


class TestAdapterQuitOwnershipGuard:
    def test_quit_does_not_kill_when_only_connected(self) -> None:
        """Regression: connected foreground window must not be force-killed."""
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter()
        adapter._app = MagicMock()
        adapter._window = MagicMock()
        adapter._window_pid = 1234
        adapter._owns_app_process = False

        with patch("subprocess.run") as mock_run:
            adapter.quit()

        mock_run.assert_not_called()
        assert adapter._app is None
        assert adapter._window is None
        assert adapter._window_pid is None

    def test_quit_kills_when_process_was_started_by_adapter(self) -> None:
        """Preserve existing cleanup for processes launched by the framework."""
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter()
        app = MagicMock()
        app.process.return_value = 4321
        adapter._app = app
        adapter._window = MagicMock()
        adapter._window_pid = 4321
        adapter._owns_app_process = True

        with patch("subprocess.run") as mock_run:
            adapter.quit()

        mock_run.assert_called_once()


class TestAdapterLocatorFallback:
    def test_resolve_control_falls_back_to_desktop_windows(self) -> None:
        from framework.core.models import Locator
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter()
        adapter._window = MagicMock()

        # Active window lookup misses.
        active_spec = MagicMock()
        active_spec.wrapper_object.side_effect = RuntimeError("not found")
        adapter._window.child_window.return_value = active_spec

        # Desktop fallback lookup succeeds.
        fallback_window = MagicMock()
        fallback_window.window_text.return_value = "Search Host"
        fallback_spec = MagicMock()
        fallback_control = MagicMock()
        fallback_spec.wrapper_object.return_value = fallback_control
        fallback_window.child_window.return_value = fallback_spec

        with patch("framework.driver.pywinauto_adapter.Desktop") as MockDesktop:
            MockDesktop.return_value.windows.return_value = [fallback_window]
            resolved = adapter._resolve_control(Locator(by="auto_id", value="SearchButton"))

        assert resolved is fallback_control

    def test_resolve_control_raises_when_not_found_anywhere(self) -> None:
        from framework.core.exceptions import LocatorResolutionError
        from framework.core.models import Locator
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter()
        adapter._window = MagicMock()

        active_spec = MagicMock()
        active_spec.wrapper_object.side_effect = RuntimeError("not found")
        adapter._window.child_window.return_value = active_spec

        miss_window = MagicMock()
        miss_spec = MagicMock()
        miss_spec.wrapper_object.side_effect = RuntimeError("not found")
        miss_window.child_window.return_value = miss_spec

        with patch("framework.driver.pywinauto_adapter.Desktop") as MockDesktop:
            MockDesktop.return_value.windows.return_value = [miss_window]
            with pytest.raises(LocatorResolutionError, match="Control not found"):
                adapter._resolve_control(Locator(by="auto_id", value="DoesNotExist"))

    def test_auto_id_semantic_fallback_uses_best_match(self) -> None:
        from framework.core.models import Locator
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter()
        parent = MagicMock()
        adapter._window = parent

        def _child_window(**kwargs):
            spec = MagicMock()
            if kwargs == {"auto_id": "StartButton"}:
                spec.wrapper_object.side_effect = RuntimeError("auto_id miss")
            elif kwargs == {"title": "StartButton"}:
                spec.wrapper_object.side_effect = RuntimeError("title miss")
            elif kwargs == {"best_match": "StartButton"}:
                spec.wrapper_object.side_effect = RuntimeError("best_match raw miss")
            elif kwargs == {"best_match": "Start Button"}:
                resolved = MagicMock()
                spec.wrapper_object.return_value = resolved
            else:
                spec.wrapper_object.side_effect = RuntimeError("unexpected")
            return spec

        parent.child_window.side_effect = _child_window

        resolved = adapter._resolve_control(Locator(by="auto_id", value="StartButton"))
        assert resolved is not None

    def test_auto_id_fallback_kwargs_include_humanized_and_stem(self) -> None:
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter

        adapter = PyWinAutoAdapter()
        kwargs_list = adapter._auto_id_fallback_kwargs("StartButton")

        assert {"best_match": "StartButton"} in kwargs_list
        assert {"best_match": "Start Button"} in kwargs_list
        assert {"best_match": "Start"} in kwargs_list


# ===========================================================================
# F. Adapter click interaction — cursor-free fallback chain
# ===========================================================================


class TestAdapterInvokeClickFallback:
    def _make_adapter_with_window(self):
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter
        adapter = PyWinAutoAdapter()
        adapter._window = MagicMock()
        return adapter

    def test_invoke_used_when_available(self) -> None:
        adapter = self._make_adapter_with_window()
        control = MagicMock(spec=["invoke", "click", "click_input"])
        adapter._invoke_click(control)
        control.invoke.assert_called_once()
        control.click.assert_not_called()
        control.click_input.assert_not_called()

    def test_falls_back_to_click_when_invoke_raises(self) -> None:
        adapter = self._make_adapter_with_window()
        control = MagicMock(spec=["invoke", "click", "click_input"])
        control.invoke.side_effect = Exception("InvokePattern not supported")
        adapter._invoke_click(control)
        control.click.assert_called_once()
        control.click_input.assert_not_called()

    def test_falls_back_to_sendinput_when_invoke_and_click_fail(self) -> None:
        """When invoke() and click() both fail, SendInput is used — not click_input()."""
        adapter = self._make_adapter_with_window()
        control = MagicMock(spec=["invoke", "click", "click_input", "rectangle"])
        control.invoke.side_effect = Exception("no invoke")
        control.click.side_effect = Exception("no click")
        rect = MagicMock()
        rect.left, rect.right, rect.top, rect.bottom = 100, 200, 100, 200
        control.rectangle.return_value = rect

        with patch("ctypes.windll") as mock_windll:
            mock_windll.user32.GetSystemMetrics.return_value = 1920
            mock_windll.user32.SendInput.return_value = 3
            adapter._invoke_click(control)

        # click_input must never be reached
        control.click_input.assert_not_called()

    def test_cursor_pos_error_never_surfaces(self) -> None:
        """SetCursorPos is not called — neither by invoke nor by our fallback."""
        adapter = self._make_adapter_with_window()
        control = MagicMock(spec=["invoke", "click", "click_input"])
        control.invoke.side_effect = Exception("no invoke")
        # click() succeeds — nothing below it should run
        adapter._invoke_click(control)
        control.click_input.assert_not_called()

    def test_no_invoke_attr_falls_through_to_click(self) -> None:
        """Controls without invoke skip straight to click()."""
        adapter = self._make_adapter_with_window()
        control = MagicMock(spec=["click", "click_input"])
        adapter._invoke_click(control)
        control.click.assert_called_once()
        control.click_input.assert_not_called()


class TestRecordedCoordsThreadedThroughClick:
    """recorded_x / recorded_y in action metadata must reach the adapter."""

    def _executor_with_mock_driver(self, tmp_path):
        from framework.driver.desktop_driver import DesktopDriver
        from framework.playback.executor import PlaybackExecutor
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        return executor, driver

    def test_coords_extracted_from_metadata_and_passed_to_driver(self, tmp_path: Path) -> None:
        from framework.core.models import Action, ActionType, Locator
        executor, driver = self._executor_with_mock_driver(tmp_path)
        action = Action(
            action_type=ActionType.CLICK,
            locator=Locator(by="control_type", value="Pane"),
            metadata={"recorded_x": 539, "recorded_y": 1170},
        )
        executor._execute(action)
        driver.click.assert_called_once_with(
            Locator(by="control_type", value="Pane"),
            coords=(539, 1170),
        )

    def test_no_coords_when_metadata_missing(self, tmp_path: Path) -> None:
        from framework.core.models import Action, ActionType, Locator
        executor, driver = self._executor_with_mock_driver(tmp_path)
        action = Action(
            action_type=ActionType.CLICK,
            locator=Locator(by="auto_id", value="OKButton"),
            metadata={},
        )
        executor._execute(action)
        driver.click.assert_called_once_with(
            Locator(by="auto_id", value="OKButton"),
            coords=None,
        )
