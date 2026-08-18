from __future__ import annotations

import logging
import time
from pathlib import Path

from framework.assertions.validators import assert_exists, assert_text_equals
from framework.core.exceptions import PlaybackExecutionError
from framework.core.models import Action, ActionType
from framework.driver.desktop_driver import DesktopDriver
from framework.playback.retry_policy import run_with_retry
from framework.reporting.screenshot import SCREENSHOT_DIR, capture_failure_screenshot
from framework.safety.approval_gate import ApprovalGate
from framework.safety.policy import is_sensitive_action

_log = logging.getLogger(__name__)


class PlaybackExecutor:
    def __init__(
        self,
        driver: DesktopDriver,
        approval_gate: ApprovalGate | None = None,
        recording_name: str | None = None,
        screenshot_dir: Path | None = None,
    ) -> None:
        self.driver = driver
        self.approval_gate = approval_gate
        self.recording_name = recording_name
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else SCREENSHOT_DIR

    def run(self, actions: list[Action], retry_attempts: int = 2, retry_delay_seconds: float = 0.5) -> None:
        for action_index, action in enumerate(actions):
            if is_sensitive_action(action) and self.approval_gate is not None:
                self.approval_gate.require_approval(action)

            try:
                _log.debug("Action start: %s", action.action_type.value)
                run_with_retry(
                    lambda a=action: self._execute(a),
                    attempts=retry_attempts,
                    delay_seconds=retry_delay_seconds,
                )
                _log.debug("Action success: %s", action.action_type.value)
            except Exception as exc:  # noqa: BLE001
                _log.warning("Action failed: %s — %s", action.action_type.value, exc)
                screenshot_path = self._try_capture_screenshot(action_index, action)
                raise PlaybackExecutionError(
                    self._build_error_message(action_index, action, exc, screenshot_path)
                ) from exc

    # ------------------------------------------------------------------
    # Diagnostics helpers
    # ------------------------------------------------------------------

    def _try_capture_screenshot(self, action_index: int, action: Action) -> str | None:
        """Attempt a failure screenshot.  Returns the path string or None.

        Screenshot failures are logged but never allowed to suppress the
        original playback exception.
        """
        try:
            prefix = self._make_screenshot_prefix(action_index, action)
            path = capture_failure_screenshot(output_dir=self.screenshot_dir, prefix=prefix)
            _log.info("Failure screenshot saved: %s", path)
            return str(path)
        except Exception as ss_err:  # noqa: BLE001
            _log.warning("Could not capture failure screenshot: %s", ss_err)
            return None

    def _make_screenshot_prefix(self, action_index: int, action: Action) -> str:
        parts: list[str] = []
        if self.recording_name:
            parts.append(self.recording_name)
        parts.append(f"action{action_index + 1}")
        parts.append(action.action_type.value)
        return "_".join(parts)

    def _build_error_message(
        self,
        action_index: int,
        action: Action,
        cause: Exception,
        screenshot_path: str | None,
    ) -> str:
        """Build a user-friendly, context-rich error message."""
        action_label = action.action_type.value.upper()
        locator_info = f" on '{action.locator.value}'" if action.locator else ""
        recording_info = (
            f" in recording '{self.recording_name}'" if self.recording_name else ""
        )
        short_reason = str(cause).split("\n")[0][:200]

        lines = [
            f"Playback failed at Action {action_index + 1}: "
            f"{action_label}{locator_info}{recording_info}.",
            f"Reason: {short_reason}",
        ]
        if screenshot_path:
            lines.append(f"Failure screenshot: {screenshot_path}")
        return "\n".join(lines)

    def _execute(self, action: Action) -> None:
        if action.action_type is ActionType.WAIT:
            time.sleep(action.timeout_seconds or 0)
            return

        if action.action_type is ActionType.LAUNCH:
            if not action.value:
                raise PlaybackExecutionError("LAUNCH action requires an executable path.")
            self.driver.start(action.value)
            return

        if action.locator is None:
            raise PlaybackExecutionError("Action requires a locator.")

        if action.action_type is ActionType.CLICK:
            self.driver.click(action.locator)
            return

        if action.action_type is ActionType.TYPE:
            self.driver.type_text(action.locator, action.value or "")
            return

        if action.action_type is ActionType.ASSERT_EXISTS:
            assert_exists(self.driver, action.locator, timeout_seconds=action.timeout_seconds or 5.0)
            return

        if action.action_type is ActionType.ASSERT_TEXT:
            assert_text_equals(self.driver, action.locator, action.value or "")
            return

        raise PlaybackExecutionError(f"Unsupported action: {action.action_type}")
