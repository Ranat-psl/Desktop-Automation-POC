from __future__ import annotations

import logging
import threading
from typing import Callable

from pynput import keyboard, mouse

_log = logging.getLogger(__name__)


class EventListener:
    """Real Windows desktop event listener using pynput global hooks.

    Captures mouse left-click and keyboard events and forwards raw event
    dicts to a registered callback for normalization.

    *excluded_rect* is an optional ``(left, top, right, bottom)`` tuple that
    describes screen coordinates of the DA application's own window.  Any
    mouse click whose coordinates fall within that rectangle is silently
    ignored so that DA-app controls (Stop Recording, Start Recording, nav
    buttons, etc.) never become recorded test actions.

    Raw event dict shapes:
        Mouse click:   {"type": "click", "x": int, "y": int, "button": str}
        Key press:     {"type": "key_press", "key": str}
        Key release:   {"type": "key_release", "key": str}
    """

    def __init__(
        self,
        on_event: Callable[[dict], None],
        excluded_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        self._on_event = on_event
        self._excluded_rect = excluded_rect  # (left, top, right, bottom)
        self._mouse_listener: mouse.Listener | None = None
        self._keyboard_listener: keyboard.Listener | None = None
        self._lock = threading.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start global mouse and keyboard listeners in background threads."""
        with self._lock:
            if self._running:
                return
            self._running = True

        self._mouse_listener = mouse.Listener(
            on_click=self._handle_click,
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._handle_key_press,
            on_release=self._handle_key_release,
        )
        self._mouse_listener.start()
        self._keyboard_listener.start()
        _log.debug("EventListener started — capturing mouse and keyboard events")

    def stop(self) -> None:
        """Stop both listeners and block until they have terminated."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener.join()
            self._mouse_listener = None

        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener.join()
            self._keyboard_listener = None

        _log.debug("EventListener stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Internal pynput callbacks
    # ------------------------------------------------------------------

    def _handle_click(
        self,
        x: int,
        y: int,
        button: mouse.Button,
        pressed: bool,
    ) -> None:
        if not pressed:
            return  # Ignore release events — we record on press only.
        if button is not mouse.Button.left:
            return  # Only record left-clicks for automation purposes.

        # Filter out clicks on the DA application's own window so that
        # recorder controls (Stop, Start, Save, nav buttons) are never
        # captured as test actions.
        if self._excluded_rect is not None:
            left, top, right, bottom = self._excluded_rect
            if left <= x <= right and top <= y <= bottom:
                _log.debug(
                    "Click at (%d, %d) is inside DA app window — ignored", x, y
                )
                return

        event = {"type": "click", "x": x, "y": y, "button": button.name}
        _log.debug("Mouse event: %s", event)
        try:
            self._on_event(event)
        except Exception:
            _log.exception("Error in event callback for mouse event")

    def _handle_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        event = {"type": "key_press", "key": _key_to_str(key)}
        _log.debug("Keyboard event: %s", event)
        try:
            self._on_event(event)
        except Exception:
            _log.exception("Error in event callback for key press")

    def _handle_key_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        event = {"type": "key_release", "key": _key_to_str(key)}
        _log.debug("Keyboard event: %s", event)
        try:
            self._on_event(event)
        except Exception:
            _log.exception("Error in event callback for key release")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _key_to_str(key: keyboard.Key | keyboard.KeyCode) -> str:
    """Convert a pynput key to a consistent string representation."""
    if isinstance(key, keyboard.KeyCode):
        # Printable character — return the character itself.
        return key.char or f"<vk={key.vk}>"
    # Special key (e.g. Key.enter, Key.shift) — use the enum name.
    return key.name
