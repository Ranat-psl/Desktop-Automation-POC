"""Regression tests for Semantic Element Resolution v1.

Covers the KeyboardTest8 defect: TYPE action recorded with an application-level
AutomationId (e.g. Notepad's root app node) must still deliver text to the
actual edit/document control during playback.

Test plan
---------
A. Direct KEY actions (Enter, Backspace) still work unaffected.
B. Direct HOTKEY (Shift+A equivalent) still works unaffected.
C. TYPE with a proper Edit locator resolves directly — no fallback needed.
D. TYPE with an app-level AutomationId falls through to the typeable child.
E. TYPE with a title-based window locator falls through to the typeable child.
F. TYPE "rana" — the exact KeyboardTest8 scenario.
G. TYPE "hello123" — digits and letters.
H. TYPE "Hello World" — spaces.
I. TYPE followed by Enter — chronological order preserved.
J. _is_typeable correctly classifies control types.
K. _find_typeable_child prefers focused element, then first Edit descendant.
L. _resolve_typeable_control returns directly when control is typeable.
M. _resolve_typeable_control falls back when control is non-typeable.
N. _resolve_typeable_control falls back when resolution raises entirely.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from framework.core.models import Action, ActionType, Locator
from framework.driver.desktop_driver import DesktopDriver
from framework.driver.keyboard_engine import (
    is_typeable,
    find_typeable_child,
    _safe_control_type,
)
from framework.driver.pywinauto_adapter import PyWinAutoAdapter
from framework.playback.executor import PlaybackExecutor
from framework.recorder.action_normalizer import ActionNormalizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_adapter(window=None) -> PyWinAutoAdapter:
    adapter = PyWinAutoAdapter()
    adapter._window = window or MagicMock()
    return adapter


def _make_control(friendly_class: str) -> MagicMock:
    ctrl = MagicMock()
    ctrl.friendly_class_name.return_value = friendly_class
    ctrl.class_name.return_value = friendly_class
    return ctrl


# ===========================================================================
# A — Direct KEY actions are unaffected
# ===========================================================================

class TestDirectKeyActionsUnaffected:
    def test_enter_key_dispatches_to_press_key(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(action_type=ActionType.KEY, value="enter"))
        driver.press_key.assert_called_once_with("enter")
        driver.type_text.assert_not_called()
        driver.type_text_global.assert_not_called()

    def test_backspace_key_dispatches_to_press_key(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(action_type=ActionType.KEY, value="backspace"))
        driver.press_key.assert_called_once_with("backspace")


# ===========================================================================
# B — Hotkey (Shift+A) is unaffected
# ===========================================================================

class TestHotkeyUnaffected:
    def test_shift_a_dispatches_to_hotkey(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(action_type=ActionType.HOTKEY, value="shift+a"))
        driver.hotkey.assert_called_once_with("shift+a")
        driver.type_text.assert_not_called()

    def test_ctrl_c_dispatches_to_hotkey(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(action_type=ActionType.HOTKEY, value="ctrl+c"))
        driver.hotkey.assert_called_once_with("ctrl+c")


# ===========================================================================
# C — TYPE with proper Edit locator resolves directly
# ===========================================================================

class TestTypeWithProperEditLocator:
    def test_type_with_edit_locator_calls_type_text(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        locator = Locator(by="auto_id", value="TextBox1")
        executor._execute(Action(action_type=ActionType.TYPE, locator=locator, value="rana"))
        driver.type_text.assert_called_once_with(locator, "rana")
        driver.type_text_global.assert_not_called()

    def test_type_resolves_and_types_when_control_is_edit(self) -> None:
        """_resolve_typeable_control returns the edit control directly."""
        adapter = _mock_adapter()
        edit_ctrl = _make_control("Edit")
        locator = Locator(by="auto_id", value="TextBox1")

        with patch.object(adapter, "_resolve_control", return_value=edit_ctrl):
            result = adapter._resolve_typeable_control(locator)

        assert result is edit_ctrl


# ===========================================================================
# D/F — TYPE with app-level AutomationId falls through to typeable child
# (the KeyboardTest8 / "rana" scenario)
# ===========================================================================

class TestTypeWithAppLevelLocatorFallback:
    def _setup_adapter_with_notepad_appid(self):
        """Adapter whose _resolve_control raises (app-level ID not found as child)."""
        adapter = _mock_adapter()
        locator = Locator(
            by="auto_id",
            value="Appid: Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
        )
        # Simulate the resolution failure that KeyboardTest8 hits.
        from framework.core.exceptions import LocatorResolutionError
        adapter._resolve_control = MagicMock(
            side_effect=LocatorResolutionError("Control not found")
        )
        edit_ctrl = _make_control("Edit")
        adapter._window.get_focus.side_effect = Exception("no focus API")
        adapter._window.descendants.return_value = [edit_ctrl]
        return adapter, locator, edit_ctrl

    def test_rana_fallback_reaches_edit_control(self) -> None:
        """KeyboardTest8: TYPE 'rana' with Notepad AppId locator reaches Edit."""
        adapter, locator, edit_ctrl = self._setup_adapter_with_notepad_appid()
        result = adapter._resolve_typeable_control(locator)
        assert result is edit_ctrl

    def test_type_text_delivers_text_via_pynput(self) -> None:
        """type_text() must deliver text via pynput, not pywinauto type_keys."""
        adapter, locator, edit_ctrl = self._setup_adapter_with_notepad_appid()
        with patch("pynput.keyboard.Controller") as mock_kb:
            adapter.type_text(locator, "rana")
        mock_kb.return_value.type.assert_called_once_with("rana")
        edit_ctrl.type_keys.assert_not_called()

    def test_hello123_delivered_via_pynput(self) -> None:
        adapter, locator, edit_ctrl = self._setup_adapter_with_notepad_appid()
        with patch("pynput.keyboard.Controller") as mock_kb:
            adapter.type_text(locator, "hello123")
        mock_kb.return_value.type.assert_called_once_with("hello123")

    def test_hello_world_with_space_delivered_via_pynput(self) -> None:
        adapter, locator, edit_ctrl = self._setup_adapter_with_notepad_appid()
        with patch("pynput.keyboard.Controller") as mock_kb:
            adapter.type_text(locator, "Hello World")
        mock_kb.return_value.type.assert_called_once_with("Hello World")


# ===========================================================================
# E — TYPE with window title locator also falls through
# ===========================================================================

class TestTypeWithWindowTitleFallback:
    def test_window_level_locator_falls_back_to_edit_child(self) -> None:
        adapter = _mock_adapter()
        locator = Locator(by="title", value="Untitled - Notepad")
        # resolve_control returns the window wrapper (non-typeable).
        window_ctrl = _make_control("Window")
        adapter._resolve_control = MagicMock(return_value=window_ctrl)
        edit_ctrl = _make_control("Edit")
        adapter._window.get_focus.side_effect = Exception("no focus")
        adapter._window.descendants.return_value = [edit_ctrl]

        result = adapter._resolve_typeable_control(locator)
        assert result is edit_ctrl


# ===========================================================================
# G/H — TYPE "hello123" and "Hello World" via executor + mock driver
# ===========================================================================

class TestTypeValueVariants:
    @pytest.mark.parametrize("text", ["rana", "hello123", "Hello World", "Rana123"])
    def test_type_value_reaches_driver(self, text: str, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        locator = Locator(by="auto_id", value="SomeEdit")
        executor._execute(Action(action_type=ActionType.TYPE, locator=locator, value=text))
        driver.type_text.assert_called_once_with(locator, text)


# ===========================================================================
# I — TYPE followed by Enter: chronological order preserved
# ===========================================================================

class TestTypeFollowedByEnter:
    def test_type_then_enter_recorded_in_order(self) -> None:
        n = ActionNormalizer()
        with patch("framework.recorder.action_normalizer._resolve_locator_at",
                   return_value=Locator(by="auto_id", value="Edit")):
            n.push({"type": "click", "x": 100, "y": 200})
        for ch in "rana":
            n.push({"type": "key_press", "key": ch})
        n.push({"type": "key_press", "key": "enter"})
        actions = n.flush()

        types = [a.action_type for a in actions]
        assert types == [ActionType.CLICK, ActionType.TYPE, ActionType.KEY]
        assert actions[1].value == "rana"
        assert actions[2].value == "enter"

    def test_type_then_enter_playback_order(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        locator = Locator(by="auto_id", value="Edit")
        actions = [
            Action(action_type=ActionType.TYPE, locator=locator, value="rana"),
            Action(action_type=ActionType.KEY, value="enter"),
        ]
        # Calling run() should invoke type_text then press_key in order.
        driver.type_text = MagicMock()
        driver.press_key = MagicMock()
        executor.run(actions, retry_attempts=1, inter_action_delay_seconds=0)
        driver.type_text.assert_called_once_with(locator, "rana")
        driver.press_key.assert_called_once_with("enter")
        # Verify order: type_text must come before press_key.
        assert driver.method_calls.index(call.type_text(locator, "rana")) < \
               driver.method_calls.index(call.press_key("enter"))


# ===========================================================================
# J — _is_typeable classifies control types correctly
# ===========================================================================

class TestIsTypeable:
    @pytest.mark.parametrize("friendly_class", [
        "Edit", "edit", "Document", "RichEdit", "RichEdit20A", "RichEdit20W",
        "Scintilla", "ComboBox", "ComboBoxEx32",
    ])
    def test_typeable_controls_return_true(self, friendly_class: str) -> None:
        ctrl = _make_control(friendly_class)
        assert is_typeable(ctrl) is True

    @pytest.mark.parametrize("friendly_class", [
        "Window", "Pane", "Button", "Dialog", "Static", "GroupBox",
        "TreeView", "ListView", "StatusBar", "ToolBar",
    ])
    def test_non_typeable_controls_return_false(self, friendly_class: str) -> None:
        ctrl = _make_control(friendly_class)
        assert is_typeable(ctrl) is False

    def test_class_containing_edit_returns_true(self) -> None:
        ctrl = _make_control("RichEditCtrl")
        assert is_typeable(ctrl) is True


# ===========================================================================
# K — _find_typeable_child: prefers focused element, then first Edit descendant
# ===========================================================================

class TestFindTypeableChild:
    def test_returns_focused_element_when_typeable(self) -> None:
        window = MagicMock()
        focused = _make_control("Edit")
        window.get_focus.return_value = focused
        result = find_typeable_child(window)
        assert result is focused

    def test_skips_non_typeable_focused_element(self) -> None:
        window = MagicMock()
        focused = _make_control("Window")
        edit = _make_control("Edit")
        window.get_focus.return_value = focused
        window.descendants.return_value = [focused, edit]
        result = find_typeable_child(window)
        assert result is edit

    def test_returns_first_descendant_when_focus_raises(self) -> None:
        window = MagicMock()
        window.get_focus.side_effect = Exception("not supported")
        edit = _make_control("Edit")
        window.descendants.return_value = [_make_control("Pane"), edit]
        result = find_typeable_child(window)
        assert result is edit

    def test_returns_none_when_no_typeable_child(self) -> None:
        window = MagicMock()
        window.get_focus.side_effect = Exception("not supported")
        window.descendants.return_value = [_make_control("Button"), _make_control("Pane")]
        result = find_typeable_child(window)
        assert result is None

    def test_returns_none_for_none_window(self) -> None:
        assert find_typeable_child(None) is None


# ===========================================================================
# L — _resolve_typeable_control: direct path when control is already typeable
# ===========================================================================

class TestResolveTypeableControlDirectPath:
    def test_direct_edit_control_returned_without_fallback(self) -> None:
        adapter = _mock_adapter()
        edit = _make_control("Edit")
        locator = Locator(by="auto_id", value="TextBox1")
        with patch.object(adapter, "_resolve_control", return_value=edit) as mock_rc:
            result = adapter._resolve_typeable_control(locator)
        mock_rc.assert_called_once_with(locator)
        # Because _is_typeable(edit) is True, no descendant search needed.
        assert result is edit
        adapter._window.descendants.assert_not_called()


# ===========================================================================
# M — _resolve_typeable_control: fallback when control is non-typeable
# ===========================================================================

class TestResolveTypeableControlFallbackNonTypeable:
    def test_window_control_triggers_fallback_to_edit_child(self) -> None:
        adapter = _mock_adapter()
        window_ctrl = _make_control("Window")
        edit = _make_control("Edit")
        locator = Locator(by="title", value="Notepad")

        with patch.object(adapter, "_resolve_control", return_value=window_ctrl):
            adapter._window.get_focus.side_effect = Exception("no focus")
            adapter._window.descendants.return_value = [window_ctrl, edit]
            result = adapter._resolve_typeable_control(locator)

        assert result is edit


# ===========================================================================
# N — _resolve_typeable_control: fallback when resolution raises
# ===========================================================================

class TestResolveTypeableControlFallbackOnError:
    def test_resolution_error_triggers_child_search(self) -> None:
        adapter = _mock_adapter()
        from framework.core.exceptions import LocatorResolutionError
        locator = Locator(by="auto_id", value="BadId")
        edit = _make_control("Edit")

        with patch.object(adapter, "_resolve_control",
                          side_effect=LocatorResolutionError("not found")):
            adapter._window.get_focus.side_effect = Exception("no focus")
            adapter._window.descendants.return_value = [edit]
            result = adapter._resolve_typeable_control(locator)

        assert result is edit

    def test_no_typeable_child_falls_back_to_window(self) -> None:
        """When all else fails, the active window itself is returned."""
        adapter = _mock_adapter()
        from framework.core.exceptions import LocatorResolutionError
        locator = Locator(by="auto_id", value="BadId")
        sentinel_window = MagicMock()
        adapter._window = sentinel_window

        with patch.object(adapter, "_resolve_control",
                          side_effect=LocatorResolutionError("not found")):
            sentinel_window.get_focus.side_effect = Exception("no focus")
            sentinel_window.descendants.return_value = []  # no typeable children
            result = adapter._resolve_typeable_control(locator)

        # Falls through to the active window itself.
        assert result is sentinel_window


# ===========================================================================
# O — KeyboardEngine.type_into uses pynput, not pywinauto type_keys
#     (the critical fix for Win11 Notepad / WinUI3 apps)
# ===========================================================================

class TestKeyboardEngineTypeIntoPynput:
    """type_into must deliver text via pynput — not pywinauto type_keys.

    pywinauto type_keys uses Win32 message delivery which silently fails on
    WinUI3 / XAML-Island controls (e.g. Win11 Notepad).  pynput sends OS-level
    SendInput events that work across Win32, UIA, and WinUI3.
    """

    def _engine_and_ctrl(self):
        from framework.driver.keyboard_engine import KeyboardEngine
        engine = KeyboardEngine()
        ctrl = MagicMock()
        return engine, ctrl

    @pytest.mark.parametrize("text", [
        "rana",
        "Rana",
        "rana123",
        "Hello World",
        "Rana@123",
        "hello123",
        "ALLCAPS",
        "mixed MiXeD 123",
    ])
    def test_type_into_uses_pynput_controller_type(self, text: str) -> None:
        """type_into must call pynput Controller().type(text) for all text values."""
        engine, ctrl = self._engine_and_ctrl()
        with patch("pynput.keyboard.Controller") as mock_kb:
            engine.type_into(ctrl, text)
        mock_kb.return_value.type.assert_called_once_with(text)

    def test_type_into_does_not_call_type_keys(self) -> None:
        """type_into must NOT call pywinauto type_keys() on the control."""
        engine, ctrl = self._engine_and_ctrl()
        with patch("pynput.keyboard.Controller"):
            engine.type_into(ctrl, "rana")
        ctrl.type_keys.assert_not_called()

    def test_type_into_attempts_set_focus_before_typing(self) -> None:
        """type_into must call set_focus (or set_foreground) before delivering text."""
        engine, ctrl = self._engine_and_ctrl()
        with patch("pynput.keyboard.Controller") as mock_kb:
            engine.type_into(ctrl, "rana")
        # Either set_focus or set_foreground must have been called.
        focus_called = ctrl.set_focus.called or ctrl.set_foreground.called
        assert focus_called, "type_into must set focus before typing"

    def test_type_into_proceeds_even_if_set_focus_raises(self) -> None:
        """set_focus failure must not prevent text from being delivered."""
        engine, ctrl = self._engine_and_ctrl()
        ctrl.set_focus.side_effect = Exception("focus not supported")
        ctrl.set_foreground.side_effect = Exception("not supported either")
        with patch("pynput.keyboard.Controller") as mock_kb:
            engine.type_into(ctrl, "rana")  # must not raise
        mock_kb.return_value.type.assert_called_once_with("rana")

    def test_type_global_also_uses_pynput(self) -> None:
        """type_global (locator=None path) also uses pynput — consistency check."""
        from framework.driver.keyboard_engine import KeyboardEngine
        engine = KeyboardEngine()
        with patch("pynput.keyboard.Controller") as mock_kb:
            engine.type_global("rana")
        mock_kb.return_value.type.assert_called_once_with("rana")

    def test_type_into_and_type_global_use_same_pynput_method(self) -> None:
        """Both type_into and type_global must use Controller().type()."""
        from framework.driver.keyboard_engine import KeyboardEngine
        engine = KeyboardEngine()
        ctrl = MagicMock()
        ctrl.set_focus.side_effect = Exception("ok")
        ctrl.set_foreground.side_effect = Exception("ok")

        calls_into = []
        calls_global = []

        with patch("pynput.keyboard.Controller") as mk:
            engine.type_into(ctrl, "rana")
            calls_into = [str(c) for c in mk.return_value.type.call_args_list]

        with patch("pynput.keyboard.Controller") as mk:
            engine.type_global("rana")
            calls_global = [str(c) for c in mk.return_value.type.call_args_list]

        assert calls_into == calls_global == ["call('rana')"]


# ===========================================================================
# P — End-to-end: adapter.type_text() with AppId locator uses pynput
# ===========================================================================

class TestAdapterTypeTextUsesPynput:
    """adapter.type_text() must route through pynput for all text values."""

    def _setup(self):
        adapter = _mock_adapter()
        locator = Locator(
            by="auto_id",
            value="Appid: Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
        )
        from framework.core.exceptions import LocatorResolutionError
        adapter._resolve_control = MagicMock(
            side_effect=LocatorResolutionError("Control not found")
        )
        edit_ctrl = _make_control("Edit")
        adapter._window.get_focus.side_effect = Exception("no focus")
        adapter._window.descendants.return_value = [edit_ctrl]
        return adapter, locator, edit_ctrl

    @pytest.mark.parametrize("text", [
        "rana", "Rana", "rana123", "Hello World", "Rana@123",
    ])
    def test_type_text_delivers_text_via_pynput_for_appid_locator(
        self, text: str
    ) -> None:
        adapter, locator, edit_ctrl = self._setup()
        with patch("pynput.keyboard.Controller") as mock_kb:
            adapter.type_text(locator, text)
        mock_kb.return_value.type.assert_called_once_with(text)
        edit_ctrl.type_keys.assert_not_called()
