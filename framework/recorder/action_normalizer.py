from __future__ import annotations

import logging
from typing import Any

from pywinauto import Desktop

from framework.core.models import Action, ActionType, Locator
from framework.driver.screen_info import get_screen_size

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key classification tables
# ---------------------------------------------------------------------------

# Modifier keys — tracked in _held_modifiers but never produce standalone actions.
# When held + another key is pressed → HOTKEY action.
_MODIFIER_KEYS = frozenset({
    "shift", "shift_l", "shift_r",
    "ctrl", "ctrl_l", "ctrl_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "cmd", "cmd_l", "cmd_r",
})

# Canonical short names for modifier keys (used in HOTKEY value strings).
_MODIFIER_CANONICAL = {
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd",
}

# Preferred modifier ordering in HOTKEY value strings.
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "cmd")

# Keys that produce a standalone KEY action (and flush any text buffer first).
# Everything not in _MODIFIER_KEYS and not printable ends up here.
_STANDALONE_KEYS = frozenset({
    "enter", "return",
    "escape",
    "tab",
    "backspace",
    "delete",
    "f1", "f2", "f3", "f4", "f5", "f6",
    "f7", "f8", "f9", "f10", "f11", "f12",
    "left", "right", "up", "down",
    "home", "end",
    "page_up", "page_down",
    "insert",
    "print_screen",
    "pause",
    "caps_lock", "num_lock", "scroll_lock",
    "space",
    "media_play_pause", "media_volume_up", "media_volume_down",
    "media_previous", "media_next",
})


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

        screen_w, screen_h = get_screen_size()
        action = Action(
            action_type=ActionType.CLICK,
            locator=locator,
            metadata={
                "recorded_x": x,
                "recorded_y": y,
                "screen_width": screen_w,
                "screen_height": screen_h,
            },
        )
        self._actions.append(action)
        _log.debug("Recorded click: locator=%s  coords=(%d,%d)  screen=%dx%d", locator, x, y, screen_w, screen_h)

    def _handle_key_press(self, event: dict[str, Any]) -> None:
        key: str = event.get("key", "")
        if not key:
            return

        # --- Modifier key down: track and wait for the combination ----
        if key in _MODIFIER_KEYS:
            self._held_modifiers.add(_MODIFIER_CANONICAL[key])
            return

        # --- Any modifier is currently held → HOTKEY action -----------
        if self._held_modifiers:
            self._flush_text_buffer()
            combo = _build_hotkey_value(self._held_modifiers, key)
            self._actions.append(
                Action(
                    action_type=ActionType.HOTKEY,
                    value=combo,
                )
            )
            _log.debug("Recorded hotkey: %r", combo)
            return

        # --- Standalone special key (Enter, Esc, F5, arrows …) -------
        if key in _STANDALONE_KEYS:
            self._flush_text_buffer()
            # Normalise "return" → "enter" for consistency.
            canonical_key = "enter" if key == "return" else key
            self._actions.append(
                Action(
                    action_type=ActionType.KEY,
                    value=canonical_key,
                )
            )
            _log.debug("Recorded key: %r", canonical_key)
            return

        # --- Printable character: accumulate into text buffer ---------
        self._text_buffer.append(key)

    def _handle_key_release(self, event: dict[str, Any]) -> None:
        key: str = event.get("key", "")
        canonical = _MODIFIER_CANONICAL.get(key)
        if canonical:
            self._held_modifiers.discard(canonical)

    def _flush_text_buffer(self) -> None:
        if not self._text_buffer:
            return
        text = "".join(self._text_buffer)
        self._text_buffer.clear()
        action = Action(
            action_type=ActionType.TYPE,
            locator=self._last_click_locator,  # may be None — target-independent typing
            value=text,
            metadata={"target_independent": True} if self._last_click_locator is None else {},
        )
        self._actions.append(action)
        _log.debug("Flushed typed text: %r (locator=%s)", text, self._last_click_locator)


# ---------------------------------------------------------------------------
# Hotkey helper
# ---------------------------------------------------------------------------

def _build_hotkey_value(held_modifiers: set[str], key: str) -> str:
    """Build a canonical hotkey string, e.g. 'ctrl+c', 'cmd+r', 'ctrl+shift+s'.

    Modifier order is always: ctrl → alt → shift → cmd → key.
    The key itself is lower-cased.
    """
    parts = [m for m in _MODIFIER_ORDER if m in held_modifiers]
    parts.append(key.lower())
    return "+".join(parts)


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

        # Walk down to the deepest UIA element whose bounding rect contains
        # (x, y).  from_point() often returns a container Pane rather than the
        # specific child control the user actually clicked on.
        element = _deepest_element_at(element, x, y)

        return _locator_from_element(element)

    except Exception as exc:
        _log.debug("Locator resolution failed at (%d, %d): %s", x, y, exc)
        return None


_GENERIC_LABELS = frozenset(
    {"pane", "window", "desktop", "", "application", "dialog", "frame"}
)


def _locator_from_element(element: Any) -> Locator | None:
    """Extract the best available Locator from a resolved UIA element."""
    # 1. AutomationId — most stable across sessions
    auto_id = _safe_get(element, "automation_id")
    if auto_id:
        return Locator(by="auto_id", value=auto_id)

    # 2. Accessible name / window_text — meaningful label before structural type
    for attr in ("name", "window_text"):
        label = _safe_get(element, attr)
        if label and len(label) <= 80 and label.lower() not in _GENERIC_LABELS:
            return Locator(by="title", value=label)

    # 3. Structural control type — last meaningful identifier
    ctrl_type = _safe_get(element, "friendly_class_name") or _safe_get(element, "class_name")
    if ctrl_type and ctrl_type.lower() not in _GENERIC_LABELS:
        return Locator(by="control_type", value=ctrl_type)

    return None


def _deepest_element_at(start: Any, x: int, y: int) -> Any:
    """Walk UIA children to find the most-specific element whose rect contains (x, y).

    Returns *start* if no deeper child contains the point (safe fallback).
    """
    try:
        children = start.children()
    except Exception:
        return start

    for child in children:
        try:
            rect = child.rectangle()
            if rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
                return _deepest_element_at(child, x, y)
        except Exception:
            continue

    return start


def _safe_get(element: Any, attr: str) -> str:
    """Call element.attr() and return a non-empty stripped string, or ''."""
    try:
        val = getattr(element, attr)()
        return val.strip() if isinstance(val, str) else ""
    except Exception:
        return ""
