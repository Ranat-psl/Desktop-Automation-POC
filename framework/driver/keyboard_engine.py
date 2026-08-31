"""Keyboard Engine — executes all keyboard-related automation actions.

Responsibility:
    TYPE  — type a string into a resolved editable UI control (or globally).
    KEY   — press and release a single named key (Enter, F5, arrow keys, …).
    HOTKEY — simultaneously hold modifier keys then release (Ctrl+C, Shift+A, …).

The Keyword Engine (executor.py) routes ActionType.TYPE / KEY / HOTKEY here.
Mouse actions (CLICK) are handled by PyWinAutoAdapter directly.

Architecture:
    executor.py  (Keyword Engine)
        └──► KeyboardEngine
                 ├── type_into(control, text)      — TYPE with locator
                 ├── type_global(text)              — TYPE without locator
                 ├── press_key(key_name)            — KEY
                 └── hotkey(hotkey_str)             — HOTKEY

    PyWinAutoAdapter owns a KeyboardEngine instance and exposes the same
    public interface (type_text / type_text_global / press_key / hotkey) so
    that nothing above the adapter layer needs to change.
"""
from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Semantic Element Resolution — which controls accept keyboard input
# ---------------------------------------------------------------------------

# UIA / Win32 class names (lower-cased) that are known to accept typed text.
_TYPEABLE_CONTROL_TYPES = frozenset({
    "edit",
    "document",
    "richedit",
    "richedit20a",
    "richedit20w",
    "scintilla",
    "combobox",
    "comboboxex32",
})


def _safe_control_type(control) -> str:
    """Return a lower-cased control-type string, or '' on failure."""
    for attr in ("friendly_class_name", "class_name"):
        try:
            val = getattr(control, attr)()
            if isinstance(val, str) and val.strip():
                return val.strip().lower()
        except Exception:
            pass
    return ""


def is_typeable(control) -> bool:
    """Return True if *control* is a known text-input control type.

    Accepts pywinauto wrapper objects and MagicMocks that quack-like one.
    """
    ct = _safe_control_type(control)
    if ct in _TYPEABLE_CONTROL_TYPES:
        return True
    # pywinauto may wrap Notepad's RichEdit as 'RichEditControl' or similar.
    return "edit" in ct


def find_typeable_child(window) -> object | None:
    """Search *window* for the first typeable (Edit / Document) descendant.

    Resolution order:
      1. Currently keyboard-focused element (if typeable).
      2. First typeable element in the descendant z-order.

    Returns None if no typeable child is found, or if *window* is None.
    """
    if window is None:
        return None

    # Priority 1: keyboard-focused element.
    try:
        focused = window.get_focus()
        if focused is not None and is_typeable(focused):
            _log.debug(
                "find_typeable_child: focused element is typeable (%s)",
                _safe_control_type(focused),
            )
            return focused
    except Exception:
        pass

    # Priority 2: first typeable descendant in z-order.
    try:
        for elem in window.descendants():
            if is_typeable(elem):
                _log.debug(
                    "find_typeable_child: found typeable descendant (%s)",
                    _safe_control_type(elem),
                )
                return elem
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Key-name resolution (pynput)
# ---------------------------------------------------------------------------

def resolve_pynput_key(name: str):
    """Map a canonical key name string to a pynput Key member or character.

    Examples:
        "enter"  → Key.enter
        "ctrl"   → Key.ctrl
        "f5"     → Key.f5
        "a"      → "a"   (single printable character, passed directly)
    """
    from pynput.keyboard import Key

    _ALIASES: dict[str, str] = {
        "ctrl": "ctrl", "ctrl_l": "ctrl_l", "ctrl_r": "ctrl_r",
        "alt": "alt", "alt_l": "alt_l", "alt_r": "alt_r",
        "shift": "shift", "shift_l": "shift_l", "shift_r": "shift_r",
        "cmd": "cmd", "win": "cmd",
        "enter": "enter", "return": "enter",
        "esc": "esc", "escape": "esc",
        "tab": "tab", "backspace": "backspace", "delete": "delete",
        "space": "space", "home": "home", "end": "end",
        "page_up": "page_up", "page_down": "page_down",
        "left": "left", "right": "right", "up": "up", "down": "down",
        "insert": "insert", "caps_lock": "caps_lock",
        "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
        "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
        "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
        "print_screen": "print_screen", "pause": "pause",
        "num_lock": "num_lock", "scroll_lock": "scroll_lock",
    }
    pynput_name = _ALIASES.get(name.lower())
    if pynput_name:
        try:
            return getattr(Key, pynput_name)
        except AttributeError:
            pass
    return name if len(name) == 1 else name


# ---------------------------------------------------------------------------
# Focus helper
# ---------------------------------------------------------------------------

def _set_focus_safe(control) -> None:
    """Attempt to give *control* OS keyboard focus without raising.

    Tries ``set_focus()`` first (pywinauto UIA/Win32 wrapper method), then
    ``set_foreground()`` as a fallback.  Both failures are logged and swallowed
    so that text input can still proceed via the currently focused OS element.
    """
    for method_name in ("set_focus", "set_foreground"):
        try:
            getattr(control, method_name)()
            _log.debug("_set_focus_safe: %s() succeeded", method_name)
            return
        except Exception as exc:
            _log.debug("_set_focus_safe: %s() failed (%s)", method_name, exc)


# ---------------------------------------------------------------------------
# Keyboard Engine
# ---------------------------------------------------------------------------

class KeyboardEngine:
    """Executes TYPE, KEY, and HOTKEY automation actions.

    All keyboard execution is centralised here.  The engine is stateless —
    create one per adapter instance or share a single instance; either works.

    TYPE resolution strategy
    ------------------------
    type_into(control, text):
        The caller has already resolved the element to type into.
        The engine validates that the element is typeable and enters the text.

    type_global(text):
        No target control — sends text via pynput Controller.type() which
        routes keystrokes to whatever currently has OS keyboard focus.
        Used for target-independent TYPE actions (locator=None).
    """

    # ------------------------------------------------------------------
    # TYPE
    # ------------------------------------------------------------------

    def type_into(self, control, text: str) -> None:
        """Type *text* into *control* using pynput keyboard input.

        The *control* is used to bring the correct UI element into keyboard
        focus before text is entered.  Actual text delivery uses
        ``pynput.keyboard.Controller.type()`` rather than pywinauto
        ``type_keys()`` because pynput sends OS-level input events that work
        reliably across Win32, UIA, and WinUI3 (Win11 Notepad / Store apps),
        whereas pywinauto's Win32 message-based ``type_keys`` silently fails
        on XAML-Island / WinUI3 edit controls.

        This makes TYPE consistent with KEY and HOTKEY — all three use pynput
        for actual keystroke delivery.
        """
        _log.debug("KeyboardEngine.type_into: text=%r", text)
        # Step 1: bring the resolved control to keyboard focus.
        _set_focus_safe(control)
        # Step 2: deliver text via pynput (reliable across all app types).
        from pynput.keyboard import Controller
        Controller().type(text)
        _log.debug("KeyboardEngine.type_into: completed")

    def type_global(self, text: str) -> None:
        """Send *text* to the currently focused OS element via pynput."""
        from pynput.keyboard import Controller
        _log.debug("KeyboardEngine.type_global: text=%r", text)
        Controller().type(text)
        _log.debug("KeyboardEngine.type_global: completed")

    # ------------------------------------------------------------------
    # KEY
    # ------------------------------------------------------------------

    def press_key(self, key_name: str) -> None:
        """Press and release a single named key."""
        from pynput.keyboard import Controller
        _log.debug("KeyboardEngine.press_key: %r", key_name)
        key = resolve_pynput_key(key_name)
        kb = Controller()
        kb.press(key)
        kb.release(key)
        _log.debug("KeyboardEngine.press_key: %r done", key_name)

    # ------------------------------------------------------------------
    # HOTKEY
    # ------------------------------------------------------------------

    def hotkey(self, hotkey_str: str) -> None:
        """Press all keys in *hotkey_str* simultaneously then release in reverse.

        *hotkey_str* is a '+'-separated canonical string, e.g. 'ctrl+c',
        'ctrl+shift+s', 'shift+a', 'alt+f4'.
        """
        from pynput.keyboard import Controller
        _log.debug("KeyboardEngine.hotkey: %r", hotkey_str)
        parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
        keys = [resolve_pynput_key(p) for p in parts]
        kb = Controller()
        for k in keys:
            kb.press(k)
        for k in reversed(keys):
            kb.release(k)
        _log.debug("KeyboardEngine.hotkey: %r done", hotkey_str)
