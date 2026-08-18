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
