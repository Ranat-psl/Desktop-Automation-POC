from __future__ import annotations

import logging
from typing import Any

from pywinauto import Desktop

from framework.core.models import Action, ActionType, Locator

_log = logging.getLogger(__name__)

# Special keys that are treated as text terminators — when seen, any buffered
# text is flushed as a TYPE action before handling the special key itself.
_TEXT_FLUSH_KEYS = {"enter", "tab", "escape"}

# Command modifiers: when any of these is held, character keys are suppressed
# entirely (e.g. Ctrl+C, Alt+F4 must not produce a buffered 'c' or '4').
_COMMAND_MODIFIERS = {
    "ctrl", "ctrl_l", "ctrl_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "cmd", "cmd_l", "cmd_r",
}

# Special keys that represent modifier / non-character keystrokes we ignore
# for typing accumulation (shift, ctrl, alt, etc.).
_MODIFIER_KEYS = {
    "shift", "shift_l", "shift_r",
    "ctrl", "ctrl_l", "ctrl_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "cmd", "cmd_l", "cmd_r",
    "caps_lock", "num_lock", "scroll_lock",
    "f1", "f2", "f3", "f4", "f5", "f6",
    "f7", "f8", "f9", "f10", "f11", "f12",
    "print_screen", "pause",
    "insert", "home", "end", "page_up", "page_down",
    "left", "right", "up", "down",
    "delete", "backspace",
    "media_play_pause", "media_volume_up", "media_volume_down",
}


class ActionNormalizer:
    """Convert a stream of raw input events into framework Action objects.

    Internally, keystrokes are buffered and emitted as a single TYPE action
    when a click or text-terminator key is encountered.  Mouse clicks are
    resolved to UI controls (via pywinauto) to produce clean locators.

    Usage::

        normalizer = ActionNormalizer()
        normalizer.push(raw_event)   # call per event from EventListener
        actions = normalizer.flush() # retrieve and clear all accumulated actions
    """

    def __init__(self) -> None:
        self._actions: list[Action] = []
        self._text_buffer: list[str] = []
        self._last_click_locator: Locator | None = None
        self._held_modifiers: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push(self, raw_event: dict[str, Any]) -> None:
        """Process a single raw event dict from EventListener."""
        event_type = raw_event.get("type")

        if event_type == "click":
            self._handle_click(raw_event)
        elif event_type == "key_press":
            self._handle_key_press(raw_event)
        elif event_type == "key_release":
            self._handle_key_release(raw_event)

    def flush(self) -> list[Action]:
        """Return all accumulated actions and reset internal state."""
        self._flush_text_buffer()
        actions = list(self._actions)
        self._actions.clear()
        self._last_click_locator = None
        self._held_modifiers.clear()
        return actions

    def normalize(self, raw_event: dict) -> Action:
        """Normalize a single event and return the resulting Action.

        Provided for backward-compatibility and unit testing.
        Note: buffered typing state is NOT preserved between calls.
        """
        self.push(raw_event)
        actions = self.flush()
        if not actions:
            raise ValueError(f"Event produced no Action: {raw_event}")
        return actions[0]

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _handle_click(self, event: dict[str, Any]) -> None:
        # Flush any pending typed text first — the click starts a new context.
        self._flush_text_buffer()

        x: int = event["x"]
        y: int = event["y"]

        locator = _resolve_locator_at(x, y)
        self._last_click_locator = locator

        action = Action(
            action_type=ActionType.CLICK,
            locator=locator,
            metadata={"recorded_x": x, "recorded_y": y},
        )
        self._actions.append(action)
        _log.debug("Recorded click: locator=%s", locator)

    def _handle_key_press(self, event: dict[str, Any]) -> None:
        key: str = event.get("key", "")

        if key in _TEXT_FLUSH_KEYS:
            # Flush text, then record a special-key action.
            self._flush_text_buffer()
            self._actions.append(
                Action(
                    action_type=ActionType.TYPE,
                    locator=self._last_click_locator,
                    value=f"<{key}>",
                    metadata={"special_key": True},
                )
            )
            return

        if key in _COMMAND_MODIFIERS:
            self._held_modifiers.add(key)
            return

        if key in _MODIFIER_KEYS or not key:
            return  # Ignore non-command modifiers and empty keys

        # Suppress characters typed while a command modifier (ctrl/alt/cmd) is held.
        # This prevents stop-shortcuts like Ctrl+C from leaking into saved actions.
        if self._held_modifiers:
            return

        # Printable character — accumulate in buffer
        self._text_buffer.append(key)

    def _handle_key_release(self, event: dict[str, Any]) -> None:
        key: str = event.get("key", "")
        self._held_modifiers.discard(key)

    def _flush_text_buffer(self) -> None:
        if not self._text_buffer:
            return
        text = "".join(self._text_buffer)
        self._text_buffer.clear()
        action = Action(
            action_type=ActionType.TYPE,
            locator=self._last_click_locator,
            value=text,
        )
        self._actions.append(action)
        _log.debug("Flushed typed text: %r", text)


# ---------------------------------------------------------------------------
# Locator resolution
# ---------------------------------------------------------------------------

def _resolve_locator_at(x: int, y: int) -> Locator | None:
    """Use pywinauto to find the UI control under (x, y) and extract a locator.

    Resolution priority:
      1. auto_id  — most reliable for UIA elements
      2. control_type — structural identifier
      3. title    — window/control title text (last resort)

    Returns None if no control can be resolved (e.g. desktop background).
    """
    try:
        desktop = Desktop(backend="uia")
        control = desktop.from_point(x, y)

        if control is None:
            return None

        # Try to get element properties — from_point may return a
        # WindowSpecification; call wrapper() to get the real element.
        try:
            element = control.wrapper_object()
        except Exception:
            element = control

        auto_id = _safe_get(element, "automation_id")
        if auto_id:
            return Locator(by="auto_id", value=auto_id)

        ctrl_type = _safe_get(element, "friendly_class_name") or _safe_get(element, "class_name")
        if ctrl_type:
            return Locator(by="control_type", value=ctrl_type)

        title = _safe_get(element, "window_text")
        if title:
            return Locator(by="title", value=title)

        return None

    except Exception as exc:
        _log.debug("Locator resolution failed at (%d, %d): %s", x, y, exc)
        return None


def _safe_get(element: Any, attr: str) -> str:
    """Call element.attr() and return a non-empty stripped string, or ''."""
    try:
        val = getattr(element, attr)()
        return val.strip() if isinstance(val, str) else ""
    except Exception:
        return ""
