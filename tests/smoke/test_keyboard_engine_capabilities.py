"""Unit / integration tests for KeyboardEngine capability baseline.

Covers every capability group:
  Group 1 — TYPE     (type_into / type_global via pynput)
  Group 2 — KEY      (all named keys via press_key)
  Group 3 — SHIFT+x  (modifier+character via hotkey)
  Group 4 — HOTKEY   (ctrl+a/c/v/x/z/home/end via hotkey)

All tests are pure unit tests — no real Notepad, no real OS events.
pynput's Controller is mocked to capture calls.

These tests complement the real end-to-end runtime validation in
_validate_keyboard_engine.py (which was run against actual Windows 11 Notepad).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from framework.driver.keyboard_engine import (
    KeyboardEngine,
    resolve_pynput_key,
    is_typeable,
    find_typeable_child,
    _set_focus_safe,
    _TYPEABLE_CONTROL_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_controller():
    """Return a (mock_instance, mock_class) pair for pynput Controller."""
    inst = MagicMock()
    cls = MagicMock(return_value=inst)
    return inst, cls


# ===========================================================================
# resolve_pynput_key — key-name resolution
# ===========================================================================

class TestResolvePynputKey:
    """resolve_pynput_key maps canonical name strings to pynput Key values."""

    @pytest.mark.parametrize("name,expected_attr", [
        ("enter", "enter"), ("return", "enter"),
        ("esc", "esc"), ("escape", "esc"),
        ("tab", "tab"),
        ("backspace", "backspace"),
        ("delete", "delete"),
        ("space", "space"),
        ("home", "home"), ("end", "end"),
        ("left", "left"), ("right", "right"),
        ("up", "up"), ("down", "down"),
        ("page_up", "page_up"), ("page_down", "page_down"),
        ("insert", "insert"),
        ("ctrl", "ctrl"), ("ctrl_l", "ctrl_l"), ("ctrl_r", "ctrl_r"),
        ("alt", "alt"), ("alt_l", "alt_l"), ("alt_r", "alt_r"),
        ("shift", "shift"), ("shift_l", "shift_l"), ("shift_r", "shift_r"),
        ("cmd", "cmd"), ("win", "cmd"),
        ("f1", "f1"), ("f5", "f5"), ("f12", "f12"),
        ("caps_lock", "caps_lock"),
        ("print_screen", "print_screen"), ("pause", "pause"),
        ("num_lock", "num_lock"), ("scroll_lock", "scroll_lock"),
    ])
    def test_named_keys_resolve_to_pynput_Key(self, name, expected_attr):
        from pynput.keyboard import Key
        result = resolve_pynput_key(name)
        assert result == getattr(Key, expected_attr), (
            f"resolve_pynput_key({name!r}) should be Key.{expected_attr}"
        )

    @pytest.mark.parametrize("char", ["a", "b", "z", "1", "9", ".", "@", "!"])
    def test_single_chars_returned_as_is(self, char):
        assert resolve_pynput_key(char) == char

    def test_case_insensitive(self):
        from pynput.keyboard import Key
        assert resolve_pynput_key("ENTER") == Key.enter
        assert resolve_pynput_key("Enter") == Key.enter
        assert resolve_pynput_key("CTRL") == Key.ctrl

    def test_unknown_multi_char_returns_string(self):
        result = resolve_pynput_key("xyzzy")
        assert result == "xyzzy"


# ===========================================================================
# GROUP 1 — TYPE
# ===========================================================================

class TestKeyboardEngineType:
    """type_into and type_global use pynput Controller().type()."""

    @pytest.mark.parametrize("text", [
        "rana", "Rana", "rana123", "Hello World",
        "test.py", "foo@bar.com", "Rana@123",
    ])
    def test_type_global_calls_pynput_type(self, text):
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.type_global(text)
        cls.assert_called_once()
        inst.type.assert_called_once_with(text)

    @pytest.mark.parametrize("text", [
        "rana", "Rana", "rana123", "Hello World", "Rana@123",
    ])
    def test_type_into_calls_pynput_type(self, text):
        ke = KeyboardEngine()
        control = MagicMock()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.type_into(control, text)
        inst.type.assert_called_once_with(text)

    def test_type_into_does_NOT_call_type_keys(self):
        """Regression: type_into must use pynput, not pywinauto type_keys."""
        ke = KeyboardEngine()
        control = MagicMock()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.type_into(control, text="rana")
        control.type_keys.assert_not_called()

    def test_type_into_attempts_focus_before_typing(self):
        """type_into should call _set_focus_safe, then pynput.type()."""
        ke = KeyboardEngine()
        control = MagicMock()
        focus_order = []
        control.set_focus.side_effect = lambda: focus_order.append("focus")
        inst, cls = _mock_controller()
        inst.type.side_effect = lambda t: focus_order.append("type")
        with patch("pynput.keyboard.Controller", cls):
            ke.type_into(control, "test")
        assert focus_order == ["focus", "type"], (
            "set_focus must be called before pynput.type()"
        )

    def test_type_global_does_not_set_focus(self):
        """type_global has no control — focus setting is not attempted."""
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.type_global("hello")
        inst.type.assert_called_once_with("hello")

    def test_type_into_continues_if_focus_fails(self):
        """Focus failure must not block text delivery."""
        ke = KeyboardEngine()
        control = MagicMock()
        control.set_focus.side_effect = RuntimeError("no focus")
        control.set_foreground.side_effect = RuntimeError("no fg")
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.type_into(control, "abc")
        inst.type.assert_called_once_with("abc")


# ===========================================================================
# GROUP 2 — KEY (press_key)
# ===========================================================================

class TestKeyboardEngineKey:
    """press_key uses pynput press+release for each named key."""

    @pytest.mark.parametrize("key_name,expected_attr", [
        ("enter", "enter"),
        ("backspace", "backspace"),
        ("tab", "tab"),
        ("esc", "esc"),
        ("delete", "delete"),
        ("home", "home"),
        ("end", "end"),
        ("left", "left"),
        ("right", "right"),
        ("up", "up"),
        ("down", "down"),
        ("page_up", "page_up"),
        ("page_down", "page_down"),
        ("f1", "f1"),
        ("f5", "f5"),
        ("f12", "f12"),
    ])
    def test_press_key_presses_and_releases(self, key_name, expected_attr):
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.press_key(key_name)
        expected_key = getattr(Key, expected_attr)
        inst.press.assert_called_once_with(expected_key)
        inst.release.assert_called_once_with(expected_key)

    def test_press_release_order(self):
        """press() must be called before release()."""
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        call_order = []
        inst.press.side_effect = lambda k: call_order.append(("press", k))
        inst.release.side_effect = lambda k: call_order.append(("release", k))
        with patch("pynput.keyboard.Controller", cls):
            ke.press_key("enter")
        assert call_order == [("press", Key.enter), ("release", Key.enter)]

    def test_press_key_case_insensitive(self):
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.press_key("ENTER")
        inst.press.assert_called_once_with(Key.enter)


# ===========================================================================
# GROUP 3 — SHIFT + CHARACTER
# ===========================================================================

class TestKeyboardEngineShift:
    """hotkey handles SHIFT+character modifier combinations."""

    @pytest.mark.parametrize("combo,expected_keys", [
        ("shift+a", ["shift", "a"]),
        ("shift+b", ["shift", "b"]),
        ("shift+1", ["shift", "1"]),
        ("shift+2", ["shift", "2"]),
        ("shift+z", ["shift", "z"]),
    ])
    def test_shift_combo_presses_modifier_then_char(self, combo, expected_keys):
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        pressed = []
        released = []
        inst.press.side_effect = lambda k: pressed.append(k)
        inst.release.side_effect = lambda k: released.append(k)
        with patch("pynput.keyboard.Controller", cls):
            ke.hotkey(combo)
        # First key pressed is the modifier
        assert pressed[0] == Key.shift
        # Second key pressed is the character
        char = expected_keys[1]
        assert pressed[1] == char
        # Released in reverse order: char first, then modifier
        assert released[0] == char
        assert released[1] == Key.shift

    def test_shift_a_uppercase(self):
        """shift+a should produce uppercase A via OS-level modifier hold."""
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.hotkey("shift+a")
        # Verify shift is held while 'a' is pressed
        calls = inst.press.call_args_list
        assert calls[0] == call(Key.shift)
        assert calls[1] == call("a")

    def test_shift_combo_release_in_reverse(self):
        """Keys must be released in reverse press order."""
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.hotkey("shift+a")
        release_calls = inst.release.call_args_list
        assert release_calls[0] == call("a")
        assert release_calls[1] == call(Key.shift)


# ===========================================================================
# GROUP 4 — HOTKEY (ctrl+*, alt+tab, etc.)
# ===========================================================================

class TestKeyboardEngineHotkey:
    """hotkey() handles multi-key combinations correctly."""

    @pytest.mark.parametrize("combo,mod_attr,char", [
        ("ctrl+a", "ctrl", "a"),
        ("ctrl+c", "ctrl", "c"),
        ("ctrl+v", "ctrl", "v"),
        ("ctrl+x", "ctrl", "x"),
        ("ctrl+s", "ctrl", "s"),
        ("ctrl+z", "ctrl", "z"),
        ("ctrl+y", "ctrl", "y"),
    ])
    def test_ctrl_combos_press_modifier_then_char(self, combo, mod_attr, char):
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.hotkey(combo)
        mod_key = getattr(Key, mod_attr)
        assert inst.press.call_args_list[0] == call(mod_key)
        assert inst.press.call_args_list[1] == call(char)
        assert inst.release.call_args_list[0] == call(char)
        assert inst.release.call_args_list[1] == call(mod_key)

    def test_alt_tab(self):
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.hotkey("alt+tab")
        assert inst.press.call_args_list[0] == call(Key.alt)
        assert inst.press.call_args_list[1] == call(Key.tab)
        assert inst.release.call_args_list[0] == call(Key.tab)
        assert inst.release.call_args_list[1] == call(Key.alt)

    def test_ctrl_home(self):
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.hotkey("ctrl+home")
        assert inst.press.call_args_list[0] == call(Key.ctrl)
        assert inst.press.call_args_list[1] == call(Key.home)

    def test_ctrl_end(self):
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.hotkey("ctrl+end")
        assert inst.press.call_args_list[0] == call(Key.ctrl)
        assert inst.press.call_args_list[1] == call(Key.end)

    def test_three_key_hotkey_ctrl_shift_s(self):
        """Three-key combos press all then release in reverse."""
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst, cls = _mock_controller()
        with patch("pynput.keyboard.Controller", cls):
            ke.hotkey("ctrl+shift+s")
        press_calls = inst.press.call_args_list
        release_calls = inst.release.call_args_list
        assert press_calls[0] == call(Key.ctrl)
        assert press_calls[1] == call(Key.shift)
        assert press_calls[2] == call("s")
        assert release_calls[0] == call("s")
        assert release_calls[1] == call(Key.shift)
        assert release_calls[2] == call(Key.ctrl)

    def test_hotkey_lowercase_normalisation(self):
        """'CTRL+C' and 'ctrl+c' must produce identical behaviour."""
        from pynput.keyboard import Key
        ke = KeyboardEngine()
        inst1, cls1 = _mock_controller()
        inst2, cls2 = _mock_controller()
        with patch("pynput.keyboard.Controller", cls1):
            ke.hotkey("CTRL+C")
        with patch("pynput.keyboard.Controller", cls2):
            ke.hotkey("ctrl+c")
        assert inst1.press.call_args_list == inst2.press.call_args_list


# ===========================================================================
# Semantic element resolution helpers
# ===========================================================================

class TestIsTypeable:
    @pytest.mark.parametrize("ct", list(_TYPEABLE_CONTROL_TYPES))
    def test_known_types_are_typeable(self, ct):
        ctrl = MagicMock()
        ctrl.friendly_class_name.return_value = ct
        assert is_typeable(ctrl)

    def test_edit_in_name_is_typeable(self):
        ctrl = MagicMock()
        ctrl.friendly_class_name.return_value = "RichEditControl"
        assert is_typeable(ctrl)

    def test_button_is_not_typeable(self):
        ctrl = MagicMock()
        ctrl.friendly_class_name.return_value = "Button"
        assert not is_typeable(ctrl)

    def test_exception_during_name_lookup_returns_false(self):
        ctrl = MagicMock()
        ctrl.friendly_class_name.side_effect = Exception("unavailable")
        ctrl.class_name.side_effect = Exception("unavailable")
        assert not is_typeable(ctrl)


class TestFindTypeableChild:
    def test_returns_focused_if_typeable(self):
        focused = MagicMock()
        focused.friendly_class_name.return_value = "edit"
        window = MagicMock()
        window.get_focus.return_value = focused
        result = find_typeable_child(window)
        assert result is focused

    def test_falls_back_to_descendant_if_focus_not_typeable(self):
        not_typeable_focus = MagicMock()
        not_typeable_focus.friendly_class_name.return_value = "Button"
        typeable_descendant = MagicMock()
        typeable_descendant.friendly_class_name.return_value = "edit"
        window = MagicMock()
        window.get_focus.return_value = not_typeable_focus
        window.descendants.return_value = [not_typeable_focus, typeable_descendant]
        result = find_typeable_child(window)
        assert result is typeable_descendant

    def test_returns_none_if_no_typeable_child(self):
        btn = MagicMock()
        btn.friendly_class_name.return_value = "Button"
        window = MagicMock()
        window.get_focus.return_value = None
        window.descendants.return_value = [btn]
        result = find_typeable_child(window)
        assert result is None

    def test_returns_none_for_none_window(self):
        assert find_typeable_child(None) is None


class TestSetFocusSafe:
    def test_calls_set_focus_first(self):
        ctrl = MagicMock()
        _set_focus_safe(ctrl)
        ctrl.set_focus.assert_called_once()

    def test_falls_back_to_set_foreground_if_focus_fails(self):
        ctrl = MagicMock()
        ctrl.set_focus.side_effect = AttributeError("no method")
        _set_focus_safe(ctrl)
        ctrl.set_foreground.assert_called_once()

    def test_swallows_both_failures_silently(self):
        ctrl = MagicMock()
        ctrl.set_focus.side_effect = RuntimeError("no")
        ctrl.set_foreground.side_effect = RuntimeError("no")
        _set_focus_safe(ctrl)  # must not raise
