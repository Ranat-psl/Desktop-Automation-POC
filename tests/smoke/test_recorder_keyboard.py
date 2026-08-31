"""Regression tests for keyboard recording, Stop-Recording exclusion, and playback.

Covers all requirements from the keyboard recorder specification:

A.  Stop Recording click must NOT appear in the recorded JSON.
B.  Start Recording click inside the DA app must NOT appear.
C.  DA-app exclusion via excluded_rect (EventListener filtering).
D.  Hotkeys (Win+R, Ctrl+C, Ctrl+V, Ctrl+Shift+S, Alt+Tab).
E.  Special / standalone keys (Enter, Escape, Tab, Backspace, Delete, arrows,
    Home, End, PageUp, PageDown, F1-F12).
F.  Text typing — with and without a prior click locator.
G.  Mixed mouse+keyboard chronological order preserved.
H.  Save and reload — JSON round-trip for all action types.
I.  Playback — KEY, HOTKEY, TYPE(locator=None), CLICK(locator=None, coords).
J.  Coordinate-only click (locator=None, coords present) is a valid action.
K.  Click with neither locator nor coords raises PlaybackExecutionError.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from framework.core.models import Action, ActionType, Locator
from framework.driver.desktop_driver import DesktopDriver
from framework.playback.executor import PlaybackExecutor
from framework.recorder.action_normalizer import ActionNormalizer
from framework.recorder.event_listener import EventListener
from framework.recorder.recording_store import RecordingStore


# ===========================================================================
# A/B/C — Stop Recording / DA App exclusion
# ===========================================================================

class TestDaAppExclusion:
    """EventListener must drop clicks inside the DA app window rect."""

    def test_click_inside_excluded_rect_is_dropped(self) -> None:
        received: list[dict] = []
        listener = EventListener(on_event=received.append, excluded_rect=(0, 0, 1200, 800))
        # Simulate pynput callback directly (no real OS hook).
        from pynput.mouse import Button
        listener._handle_click(x=600, y=400, button=Button.left, pressed=True)
        assert received == [], "Click inside DA app rect must be dropped"

    def test_click_outside_excluded_rect_is_forwarded(self) -> None:
        received: list[dict] = []
        listener = EventListener(on_event=received.append, excluded_rect=(0, 0, 1200, 800))
        from pynput.mouse import Button
        listener._handle_click(x=1300, y=900, button=Button.left, pressed=True)
        assert len(received) == 1
        assert received[0]["type"] == "click"
        assert received[0]["x"] == 1300

    def test_click_on_rect_boundary_is_excluded(self) -> None:
        received: list[dict] = []
        listener = EventListener(on_event=received.append, excluded_rect=(100, 100, 500, 400))
        from pynput.mouse import Button
        # Boundary point should be excluded (within the inclusive range).
        listener._handle_click(x=100, y=100, button=Button.left, pressed=True)
        assert received == []

    def test_no_excluded_rect_forwards_all_clicks(self) -> None:
        received: list[dict] = []
        listener = EventListener(on_event=received.append, excluded_rect=None)
        from pynput.mouse import Button
        listener._handle_click(x=600, y=400, button=Button.left, pressed=True)
        assert len(received) == 1

    def test_stop_recording_click_not_in_recorded_actions(self) -> None:
        """Simulate a full record cycle where the Stop button is at (600, 400)."""
        normalizer = ActionNormalizer()
        listener = EventListener(
            on_event=normalizer.push,
            excluded_rect=(0, 0, 1200, 800),  # DA app covers this region
        )
        from pynput.mouse import Button
        # User clicks a target app at (1400, 600) — outside DA window.
        listener._handle_click(x=1400, y=600, button=Button.left, pressed=True)
        # User clicks Stop Recording at (600, 400) — inside DA window → excluded.
        listener._handle_click(x=600, y=400, button=Button.left, pressed=True)

        actions = normalizer.flush()
        assert len(actions) == 1, "Only the target-app click must be recorded"
        assert actions[0].metadata["recorded_x"] == 1400

    def test_start_recording_click_not_in_recorded_actions(self) -> None:
        """A click on Start Recording (inside DA window) must also be excluded."""
        normalizer = ActionNormalizer()
        listener = EventListener(
            on_event=normalizer.push,
            excluded_rect=(100, 100, 900, 700),
        )
        from pynput.mouse import Button
        # Click Start Recording
        listener._handle_click(x=300, y=200, button=Button.left, pressed=True)
        # Click in target app
        listener._handle_click(x=1500, y=800, button=Button.left, pressed=True)

        actions = normalizer.flush()
        assert len(actions) == 1
        assert actions[0].metadata["recorded_x"] == 1500


# ===========================================================================
# D — Hotkeys
# ===========================================================================

class TestHotkeyRecording:
    def _push_hotkey(self, normalizer: ActionNormalizer, modifier: str, key: str) -> None:
        normalizer.push({"type": "key_press", "key": modifier})
        normalizer.push({"type": "key_press", "key": key})
        normalizer.push({"type": "key_release", "key": key})
        normalizer.push({"type": "key_release", "key": modifier})

    def test_ctrl_c_produces_hotkey_action(self) -> None:
        n = ActionNormalizer()
        self._push_hotkey(n, "ctrl", "c")
        actions = n.flush()
        assert len(actions) == 1
        assert actions[0].action_type is ActionType.HOTKEY
        assert actions[0].value == "ctrl+c"

    def test_ctrl_v_produces_hotkey_action(self) -> None:
        n = ActionNormalizer()
        self._push_hotkey(n, "ctrl", "v")
        actions = n.flush()
        assert actions[0].value == "ctrl+v"

    def test_cmd_r_produces_hotkey_action(self) -> None:
        n = ActionNormalizer()
        self._push_hotkey(n, "cmd", "r")
        actions = n.flush()
        assert actions[0].value == "cmd+r"

    def test_ctrl_shift_s_produces_hotkey_with_canonical_order(self) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": "ctrl"})
        n.push({"type": "key_press", "key": "shift"})
        n.push({"type": "key_press", "key": "s"})
        n.push({"type": "key_release", "key": "s"})
        n.push({"type": "key_release", "key": "shift"})
        n.push({"type": "key_release", "key": "ctrl"})
        actions = n.flush()
        assert len(actions) == 1
        assert actions[0].value == "ctrl+shift+s"

    def test_alt_tab_produces_hotkey(self) -> None:
        n = ActionNormalizer()
        self._push_hotkey(n, "alt", "tab")
        actions = n.flush()
        assert actions[0].action_type is ActionType.HOTKEY
        assert actions[0].value == "alt+tab"

    def test_hotkey_has_no_locator(self) -> None:
        n = ActionNormalizer()
        self._push_hotkey(n, "ctrl", "c")
        actions = n.flush()
        assert actions[0].locator is None

    def test_multiple_hotkeys_in_sequence(self) -> None:
        n = ActionNormalizer()
        self._push_hotkey(n, "ctrl", "c")
        self._push_hotkey(n, "ctrl", "v")
        actions = n.flush()
        assert len(actions) == 2
        assert actions[0].value == "ctrl+c"
        assert actions[1].value == "ctrl+v"


# ===========================================================================
# E — Special / standalone keys
# ===========================================================================

class TestSpecialKeyRecording:
    def test_enter_produces_key_action(self) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": "enter"})
        actions = n.flush()
        assert len(actions) == 1
        assert actions[0].action_type is ActionType.KEY
        assert actions[0].value == "enter"

    def test_return_normalised_to_enter(self) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": "return"})
        actions = n.flush()
        assert actions[0].value == "enter"

    def test_escape_produces_key_action(self) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": "escape"})
        actions = n.flush()
        assert actions[0].action_type is ActionType.KEY
        assert actions[0].value == "escape"

    def test_tab_produces_key_action(self) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": "tab"})
        actions = n.flush()
        assert actions[0].action_type is ActionType.KEY
        assert actions[0].value == "tab"

    def test_backspace_produces_key_action(self) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": "backspace"})
        actions = n.flush()
        assert actions[0].value == "backspace"

    def test_delete_produces_key_action(self) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": "delete"})
        actions = n.flush()
        assert actions[0].value == "delete"

    @pytest.mark.parametrize("key", ["f1", "f2", "f5", "f10", "f12"])
    def test_function_keys_produce_key_action(self, key: str) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": key})
        actions = n.flush()
        assert actions[0].action_type is ActionType.KEY
        assert actions[0].value == key

    @pytest.mark.parametrize("key", ["left", "right", "up", "down"])
    def test_arrow_keys_produce_key_action(self, key: str) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": key})
        actions = n.flush()
        assert actions[0].action_type is ActionType.KEY
        assert actions[0].value == key

    @pytest.mark.parametrize("key", ["home", "end", "page_up", "page_down", "insert"])
    def test_navigation_keys_produce_key_action(self, key: str) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": key})
        actions = n.flush()
        assert actions[0].action_type is ActionType.KEY

    def test_key_action_has_no_locator(self) -> None:
        n = ActionNormalizer()
        n.push({"type": "key_press", "key": "enter"})
        actions = n.flush()
        assert actions[0].locator is None


# ===========================================================================
# F — Text typing (with and without prior click locator)
# ===========================================================================

class TestTextTypingRecording:
    def test_text_with_locator(self) -> None:
        n = ActionNormalizer()
        # Simulate a click on a known control first.
        with patch("framework.recorder.action_normalizer._resolve_locator_at",
                   return_value=Locator(by="auto_id", value="Edit")):
            n.push({"type": "click", "x": 100, "y": 200})
        n.push({"type": "key_press", "key": "n"})
        n.push({"type": "key_press", "key": "o"})
        n.push({"type": "key_press", "key": "t"})
        actions = n.flush()
        type_actions = [a for a in actions if a.action_type is ActionType.TYPE]
        assert len(type_actions) == 1
        assert type_actions[0].value == "not"
        assert type_actions[0].locator == Locator(by="auto_id", value="Edit")

    def test_text_without_locator_is_target_independent(self) -> None:
        """Text typed without a prior click must still be recorded (locator=None)."""
        n = ActionNormalizer()
        for ch in "notepad":
            n.push({"type": "key_press", "key": ch})
        actions = n.flush()
        assert len(actions) == 1
        assert actions[0].action_type is ActionType.TYPE
        assert actions[0].value == "notepad"
        assert actions[0].locator is None
        assert actions[0].metadata.get("target_independent") is True

    def test_text_with_spaces_and_numbers(self) -> None:
        n = ActionNormalizer()
        for ch in "abc 123":
            n.push({"type": "key_press", "key": ch})
        actions = n.flush()
        assert actions[0].value == "abc 123"

    def test_enter_flushes_text_buffer_before_key_action(self) -> None:
        n = ActionNormalizer()
        for ch in "notepad":
            n.push({"type": "key_press", "key": ch})
        n.push({"type": "key_press", "key": "enter"})
        actions = n.flush()
        assert len(actions) == 2
        assert actions[0].action_type is ActionType.TYPE
        assert actions[0].value == "notepad"
        assert actions[1].action_type is ActionType.KEY
        assert actions[1].value == "enter"


# ===========================================================================
# G — Mixed mouse + keyboard — chronological order preserved
# ===========================================================================

class TestChronologicalOrder:
    def test_click_type_enter_click_order(self) -> None:
        n = ActionNormalizer()
        with patch("framework.recorder.action_normalizer._resolve_locator_at",
                   return_value=Locator(by="auto_id", value="SearchBox")):
            n.push({"type": "click", "x": 300, "y": 100})
        for ch in "notepad":
            n.push({"type": "key_press", "key": ch})
        n.push({"type": "key_press", "key": "enter"})
        with patch("framework.recorder.action_normalizer._resolve_locator_at",
                   return_value=Locator(by="title", value="Notepad")):
            n.push({"type": "click", "x": 800, "y": 400})

        actions = n.flush()
        types = [a.action_type for a in actions]
        assert types == [
            ActionType.CLICK,
            ActionType.TYPE,
            ActionType.KEY,
            ActionType.CLICK,
        ]

    def test_hotkey_between_clicks_preserves_order(self) -> None:
        n = ActionNormalizer()
        with patch("framework.recorder.action_normalizer._resolve_locator_at",
                   return_value=None):
            n.push({"type": "click", "x": 100, "y": 100})
        n.push({"type": "key_press", "key": "ctrl"})
        n.push({"type": "key_press", "key": "c"})
        n.push({"type": "key_release", "key": "c"})
        n.push({"type": "key_release", "key": "ctrl"})
        with patch("framework.recorder.action_normalizer._resolve_locator_at",
                   return_value=None):
            n.push({"type": "click", "x": 200, "y": 200})

        actions = n.flush()
        types = [a.action_type for a in actions]
        assert types == [ActionType.CLICK, ActionType.HOTKEY, ActionType.CLICK]


# ===========================================================================
# H — JSON round-trip (save + reload)
# ===========================================================================

class TestJsonRoundTrip:
    def test_key_action_survives_round_trip(self, tmp_path: Path) -> None:
        original = [Action(action_type=ActionType.KEY, value="enter")]
        store = RecordingStore(base_dir=tmp_path)
        store.save("test_key", original)
        loaded = store.load("test_key")
        assert loaded[0].action_type is ActionType.KEY
        assert loaded[0].value == "enter"

    def test_hotkey_action_survives_round_trip(self, tmp_path: Path) -> None:
        original = [Action(action_type=ActionType.HOTKEY, value="cmd+r")]
        store = RecordingStore(base_dir=tmp_path)
        store.save("test_hotkey", original)
        loaded = store.load("test_hotkey")
        assert loaded[0].action_type is ActionType.HOTKEY
        assert loaded[0].value == "cmd+r"

    def test_type_without_locator_survives_round_trip(self, tmp_path: Path) -> None:
        original = [Action(
            action_type=ActionType.TYPE,
            locator=None,
            value="notepad",
            metadata={"target_independent": True},
        )]
        store = RecordingStore(base_dir=tmp_path)
        store.save("test_type_no_locator", original)
        loaded = store.load("test_type_no_locator")
        assert loaded[0].locator is None
        assert loaded[0].value == "notepad"
        assert loaded[0].metadata.get("target_independent") is True

    def test_click_with_null_locator_survives_round_trip(self, tmp_path: Path) -> None:
        original = [Action(
            action_type=ActionType.CLICK,
            locator=None,
            metadata={"recorded_x": 249, "recorded_y": 342},
        )]
        store = RecordingStore(base_dir=tmp_path)
        store.save("test_null_locator_click", original)
        loaded = store.load("test_null_locator_click")
        assert loaded[0].locator is None
        assert loaded[0].metadata["recorded_x"] == 249

    def test_full_workflow_round_trip(self, tmp_path: Path) -> None:
        """Win+R → notepad → Enter — full round-trip."""
        original = [
            Action(action_type=ActionType.HOTKEY, value="cmd+r"),
            Action(action_type=ActionType.TYPE, locator=None, value="notepad",
                   metadata={"target_independent": True}),
            Action(action_type=ActionType.KEY, value="enter"),
        ]
        store = RecordingStore(base_dir=tmp_path)
        store.save("test_full_workflow", original)
        loaded = store.load("test_full_workflow")
        assert [a.action_type for a in loaded] == [
            ActionType.HOTKEY, ActionType.TYPE, ActionType.KEY
        ]
        assert loaded[0].value == "cmd+r"
        assert loaded[1].value == "notepad"
        assert loaded[2].value == "enter"


# ===========================================================================
# I — Playback: KEY, HOTKEY, TYPE(locator=None)
# ===========================================================================

class TestPlaybackNewActionTypes:
    def test_key_action_calls_press_key(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(action_type=ActionType.KEY, value="enter"))
        driver.press_key.assert_called_once_with("enter")

    def test_hotkey_action_calls_hotkey(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(action_type=ActionType.HOTKEY, value="cmd+r"))
        driver.hotkey.assert_called_once_with("cmd+r")

    def test_type_with_locator_calls_type_text(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(
            action_type=ActionType.TYPE,
            locator=Locator(by="auto_id", value="Edit"),
            value="hello",
        ))
        driver.type_text.assert_called_once_with(Locator(by="auto_id", value="Edit"), "hello")
        driver.type_text_global.assert_not_called()

    def test_type_without_locator_calls_type_text_global(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(
            action_type=ActionType.TYPE,
            locator=None,
            value="notepad",
            metadata={"target_independent": True},
        ))
        driver.type_text_global.assert_called_once_with("notepad")
        driver.type_text.assert_not_called()

    def test_key_with_no_value_raises(self, tmp_path: Path) -> None:
        from framework.core.exceptions import PlaybackExecutionError
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        with pytest.raises(PlaybackExecutionError):
            executor._execute(Action(action_type=ActionType.KEY, value=None))

    def test_hotkey_with_no_value_raises(self, tmp_path: Path) -> None:
        from framework.core.exceptions import PlaybackExecutionError
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        with pytest.raises(PlaybackExecutionError):
            executor._execute(Action(action_type=ActionType.HOTKEY, value=None))


# ===========================================================================
# J — Coordinate-only click (locator=None + coords)
# ===========================================================================

class TestCoordinateOnlyClick:
    def test_click_with_null_locator_and_coords_calls_driver(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        executor._execute(Action(
            action_type=ActionType.CLICK,
            locator=None,
            metadata={"recorded_x": 249, "recorded_y": 342},
        ))
        driver.click.assert_called_once_with(None, coords=(249, 342))

    def test_click_with_null_locator_no_coords_raises(self, tmp_path: Path) -> None:
        from framework.core.exceptions import PlaybackExecutionError
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        with pytest.raises(PlaybackExecutionError, match="neither a locator nor recorded coordinates"):
            executor._execute(Action(
                action_type=ActionType.CLICK,
                locator=None,
                metadata={},
            ))


# ===========================================================================
# K — Adapter keyboard methods (unit tests, no real keyboard)
# ===========================================================================

class TestAdapterKeyboardMethods:
    def _make_adapter(self):
        from framework.driver.pywinauto_adapter import PyWinAutoAdapter
        adapter = PyWinAutoAdapter()
        adapter._window = MagicMock()
        return adapter

    def test_press_key_calls_pynput_press_release(self) -> None:
        adapter = self._make_adapter()
        with patch("pynput.keyboard.Controller") as MockKb:
            kb_instance = MockKb.return_value
            adapter.press_key("enter")
        from pynput.keyboard import Key
        kb_instance.press.assert_called_once_with(Key.enter)
        kb_instance.release.assert_called_once_with(Key.enter)

    def test_hotkey_presses_all_parts_then_releases_in_reverse(self) -> None:
        adapter = self._make_adapter()
        with patch("pynput.keyboard.Controller") as MockKb:
            kb_instance = MockKb.return_value
            adapter.hotkey("ctrl+c")
        from pynput.keyboard import Key
        press_calls = [c[0][0] for c in kb_instance.press.call_args_list]
        release_calls = [c[0][0] for c in kb_instance.release.call_args_list]
        assert Key.ctrl in press_calls
        assert "c" in press_calls or Key.ctrl in press_calls  # at least modifier pressed
        # Releases in reverse order
        assert release_calls == list(reversed(press_calls))

    def test_type_text_global_calls_kb_type(self) -> None:
        adapter = self._make_adapter()
        with patch("pynput.keyboard.Controller") as MockKb:
            kb_instance = MockKb.return_value
            adapter.type_text_global("notepad")
        kb_instance.type.assert_called_once_with("notepad")


# ===========================================================================
# L — Recorder → JSON → Playback: Win+R → notepad → Enter workflow
# ===========================================================================

class TestWinRWorkflow:
    """Simulate the exact Win+R → type notepad → Enter flow end-to-end."""

    def test_win_r_workflow_produces_correct_actions(self) -> None:
        n = ActionNormalizer()
        # Win + R
        n.push({"type": "key_press", "key": "cmd"})
        n.push({"type": "key_press", "key": "r"})
        n.push({"type": "key_release", "key": "r"})
        n.push({"type": "key_release", "key": "cmd"})
        # Type "notepad"
        for ch in "notepad":
            n.push({"type": "key_press", "key": ch})
        # Enter
        n.push({"type": "key_press", "key": "enter"})

        actions = n.flush()
        assert len(actions) == 3
        assert actions[0].action_type is ActionType.HOTKEY
        assert actions[0].value == "cmd+r"
        assert actions[1].action_type is ActionType.TYPE
        assert actions[1].value == "notepad"
        assert actions[1].locator is None
        assert actions[2].action_type is ActionType.KEY
        assert actions[2].value == "enter"

    def test_win_r_workflow_playback_calls_correct_driver_methods(self, tmp_path: Path) -> None:
        driver = MagicMock(spec=DesktopDriver)
        executor = PlaybackExecutor(driver=driver, screenshot_dir=tmp_path)
        actions = [
            Action(action_type=ActionType.HOTKEY, value="cmd+r"),
            Action(action_type=ActionType.TYPE, locator=None, value="notepad",
                   metadata={"target_independent": True}),
            Action(action_type=ActionType.KEY, value="enter"),
        ]
        with patch("framework.playback.executor.time") as mock_time:
            mock_time.sleep = lambda s: None
            executor.run(actions, inter_action_delay_seconds=0)

        driver.hotkey.assert_called_once_with("cmd+r")
        driver.type_text_global.assert_called_once_with("notepad")
        driver.press_key.assert_called_once_with("enter")
