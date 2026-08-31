from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from framework.assertions.validators import assert_exists, assert_text_equals
from framework.core.exceptions import PlaybackExecutionError
from framework.core.models import Action, ActionType
from framework.driver.desktop_driver import DesktopDriver
from framework.driver.screen_info import scale_coords
from framework.playback.retry_policy import run_with_retry
from framework.reporting.screenshot import SCREENSHOT_DIR, capture_failure_screenshot
from framework.safety.approval_gate import ApprovalGate
from framework.safety.policy import is_sensitive_action

_log = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result for a single executed action."""
    action_index: int          # 0-based
    action_type: str
    value: str | None
    locator_str: str | None
    status: str                # "passed" | "failed"
    duration_seconds: float
    error_message: str | None = None
    screenshot_path: str | None = None


@dataclass
class PlaybackResult:
    """Aggregated result for a complete recording playback."""
    recording_name: str | None
    status: str                # "passed" | "failed"
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    action_results: list[ActionResult] = field(default_factory=list)
    error_message: str | None = None


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
        self.result: PlaybackResult | None = None

    def run(self, actions: list[Action], retry_attempts: int = 2, retry_delay_seconds: float = 0.5, inter_action_delay_seconds: float = 1.0) -> PlaybackResult:
        """Execute *actions* in sequence.

        Collects per-action results and returns a :class:`PlaybackResult`.
        The result is also available via ``self.result`` after the call.

        Raises :class:`PlaybackExecutionError` on the first failed action (after
        recording the failure in the result).
        """
        started_at = datetime.now(timezone.utc)
        action_results: list[ActionResult] = []
        overall_error: str | None = None

        try:
            for action_index, action in enumerate(actions):
                if is_sensitive_action(action) and self.approval_gate is not None:
                    self.approval_gate.require_approval(action)

                action_start = time.monotonic()
                screenshot_path: str | None = None
                try:
                    _log.debug("Action start: %s", action.action_type.value)
                    run_with_retry(
                        lambda a=action: self._execute(a),
                        attempts=retry_attempts,
                        delay_seconds=retry_delay_seconds,
                    )
                    _log.debug("Action success: %s", action.action_type.value)
                    action_results.append(ActionResult(
                        action_index=action_index,
                        action_type=action.action_type.value,
                        value=action.value,
                        locator_str=f"{action.locator.by}:{action.locator.value}" if action.locator else None,
                        status="passed",
                        duration_seconds=time.monotonic() - action_start,
                    ))
                except Exception as exc:  # noqa: BLE001
                    _log.warning("Action failed: %s — %s", action.action_type.value, exc)
                    screenshot_path = self._try_capture_screenshot(action_index, action)
                    err_msg = self._build_error_message(action_index, action, exc, screenshot_path)
                    action_results.append(ActionResult(
                        action_index=action_index,
                        action_type=action.action_type.value,
                        value=action.value,
                        locator_str=f"{action.locator.by}:{action.locator.value}" if action.locator else None,
                        status="failed",
                        duration_seconds=time.monotonic() - action_start,
                        error_message=str(exc).split("\n")[0][:300],
                        screenshot_path=screenshot_path,
                    ))
                    overall_error = err_msg
                    finished_at = datetime.now(timezone.utc)
                    self.result = PlaybackResult(
                        recording_name=self.recording_name,
                        status="failed",
                        started_at=started_at,
                        finished_at=finished_at,
                        duration_seconds=(finished_at - started_at).total_seconds(),
                        action_results=action_results,
                        error_message=overall_error,
                    )
                    raise PlaybackExecutionError(err_msg) from exc

                # Pause between actions so opened windows / UI transitions can settle.
                if inter_action_delay_seconds > 0 and action_index < len(actions) - 1:
                    time.sleep(inter_action_delay_seconds)

        except PlaybackExecutionError:
            raise
        except Exception as exc:
            # Unexpected error outside action loop
            finished_at = datetime.now(timezone.utc)
            self.result = PlaybackResult(
                recording_name=self.recording_name,
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                action_results=action_results,
                error_message=str(exc),
            )
            raise

        finished_at = datetime.now(timezone.utc)
        self.result = PlaybackResult(
            recording_name=self.recording_name,
            status="passed",
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            action_results=action_results,
        )
        return self.result

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
            # Give the OS a moment for the window to appear, then try to maximize.
            time.sleep(0.5)
            try:
                self.driver.maximize_window()
            except Exception:  # noqa: BLE001
                pass
            return

        if action.action_type is ActionType.CLICK:
            x = action.metadata.get("recorded_x") if action.metadata else None
            y = action.metadata.get("recorded_y") if action.metadata else None
            coords: tuple[int, int] | None = None
            if x is not None and y is not None:
                # Scale coordinates from recorded resolution to current resolution
                # when the recording stored screen dimensions.
                rec_w = int(action.metadata.get("screen_width", 0) or 0)
                rec_h = int(action.metadata.get("screen_height", 0) or 0)
                coords = scale_coords(int(x), int(y), rec_w, rec_h)
            if action.locator is not None:
                self.driver.click(action.locator, coords=coords)
            elif coords is not None:
                # locator=None but coordinates recorded — coordinate-only click
                _log.debug(
                    "CLICK: locator=None, using coordinate fallback (%d, %d)",
                    coords[0], coords[1],
                )
                self.driver.click(action.locator, coords=coords)
            else:
                raise PlaybackExecutionError(
                    "CLICK action has neither a locator nor recorded coordinates."
                )
            return

        if action.action_type is ActionType.TYPE:
            if action.locator is not None:
                self.driver.type_text(action.locator, action.value or "")
            else:
                # Target-independent typing (e.g. into Win+R run dialog)
                _log.debug("TYPE: locator=None — using global keyboard input")
                self.driver.type_text_global(action.value or "")
            return

        if action.action_type is ActionType.KEY:
            if not action.value:
                raise PlaybackExecutionError("KEY action requires a non-empty value.")
            _log.debug("KEY: pressing %r", action.value)
            self.driver.press_key(action.value)
            return

        if action.action_type is ActionType.HOTKEY:
            if not action.value:
                raise PlaybackExecutionError("HOTKEY action requires a non-empty value.")
            _log.debug("HOTKEY: executing %r", action.value)
            self.driver.hotkey(action.value)
            return

        if action.action_type is ActionType.ASSERT_EXISTS:
            if action.locator is None:
                raise PlaybackExecutionError("ASSERT_EXISTS requires a locator.")
            assert_exists(self.driver, action.locator, timeout_seconds=action.timeout_seconds or 5.0)
            return

        if action.action_type is ActionType.ASSERT_TEXT:
            if action.locator is None:
                raise PlaybackExecutionError("ASSERT_TEXT requires a locator.")
            assert_text_equals(self.driver, action.locator, action.value or "")
            return

        raise PlaybackExecutionError(f"Unsupported action: {action.action_type}")
