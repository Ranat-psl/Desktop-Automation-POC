from __future__ import annotations

import logging
import time

from framework.assertions.validators import assert_exists, assert_text_equals
from framework.core.exceptions import PlaybackExecutionError
from framework.core.models import Action, ActionType
from framework.driver.desktop_driver import DesktopDriver
from framework.playback.retry_policy import run_with_retry
from framework.safety.approval_gate import ApprovalGate
from framework.safety.policy import is_sensitive_action

_log = logging.getLogger(__name__)


class PlaybackExecutor:
    def __init__(self, driver: DesktopDriver, approval_gate: ApprovalGate | None = None) -> None:
        self.driver = driver
        self.approval_gate = approval_gate

    def run(self, actions: list[Action], retry_attempts: int = 2, retry_delay_seconds: float = 0.5) -> None:
        for action in actions:
            if is_sensitive_action(action) and self.approval_gate is not None:
                self.approval_gate.require_approval(action)

            try:
                _log.debug("Action start: %s", action.action_type.value)
                run_with_retry(
                    lambda: self._execute(action),
                    attempts=retry_attempts,
                    delay_seconds=retry_delay_seconds,
                )
                _log.debug("Action success: %s", action.action_type.value)
            except Exception as exc:  # noqa: BLE001
                _log.warning("Action failed: %s — %s", action.action_type.value, exc)
                raise PlaybackExecutionError(f"Failed action {action.action_type}") from exc

    def _execute(self, action: Action) -> None:
        if action.action_type is ActionType.WAIT:
            time.sleep(action.timeout_seconds or 0)
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
