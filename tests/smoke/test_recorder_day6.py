"""Day 6 — Real Event Recorder tests.

These tests verify the recorder pipeline without requiring a live Windows
desktop session.  EventListener is tested with a fake/mock callback;
ActionNormalizer is exercised with synthetic raw-event dicts;
Recorder integration is validated with an in-memory-only path.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from framework.core.models import Action, ActionType, Locator
from framework.recorder.action_normalizer import ActionNormalizer, _resolve_locator_at
from framework.recorder.event_listener import EventListener, _key_to_str
from framework.recorder.recorder import Recorder
from framework.recorder.recording_store import RecordingStore


# ===========================================================================
# EventListener tests
# ===========================================================================


class TestEventListenerLifecycle:
    """EventListener start / stop state machine."""

    def test_initial_state_is_not_running(self) -> None:
        listener = EventListener(on_event=lambda e: None)
        assert listener.is_running is False

    def test_start_sets_running(self) -> None:
        listener = EventListener(on_event=lambda e: None)
        listener.start()
        try:
            assert listener.is_running is True
        finally:
            listener.stop()

    def test_stop_clears_running(self) -> None:
        listener = EventListener(on_event=lambda e: None)
        listener.start()
        listener.stop()
        assert listener.is_running is False

    def test_double_start_is_idempotent(self) -> None:
        listener = EventListener(on_event=lambda e: None)
        listener.start()
        listener.start()  # second call should be a no-op
        try:
            assert listener.is_running is True
        finally:
            listener.stop()

    def test_stop_on_stopped_listener_is_safe(self) -> None:
        listener = EventListener(on_event=lambda e: None)
        listener.stop()  # no-op on a listener that was never started
        assert listener.is_running is False


class TestEventListenerCallbackRouting:
    """Verify that pynput callbacks feed the user callback correctly."""

    def _make_event_catcher(self):
        events: list[dict] = []
        listener = EventListener(on_event=events.append)
        return listener, events

    def test_left_click_press_fires_callback(self) -> None:
        from pynput.mouse import Button

        listener, events = self._make_event_catcher()
        # Simulate pynput calling our internal click handler directly
        listener._handle_click(x=100, y=200, button=Button.left, pressed=True)
        assert len(events) == 1
        assert events[0]["type"] == "click"
        assert events[0]["x"] == 100
        assert events[0]["y"] == 200

    def test_left_click_release_does_not_fire_callback(self) -> None:
        from pynput.mouse import Button

        listener, events = self._make_event_catcher()
        listener._handle_click(x=100, y=200, button=Button.left, pressed=False)
        assert events == []

    def test_right_click_does_not_fire_callback(self) -> None:
        from pynput.mouse import Button

        listener, events = self._make_event_catcher()
        listener._handle_click(x=50, y=50, button=Button.right, pressed=True)
        assert events == []

    def test_key_press_fires_callback(self) -> None:
        from pynput.keyboard import KeyCode

        listener, events = self._make_event_catcher()
        listener._handle_key_press(KeyCode.from_char("a"))
        assert len(events) == 1
        assert events[0]["type"] == "key_press"
        assert events[0]["key"] == "a"

    def test_key_release_fires_callback(self) -> None:
        from pynput.keyboard import KeyCode

        listener, events = self._make_event_catcher()
        listener._handle_key_release(KeyCode.from_char("a"))
        assert len(events) == 1
        assert events[0]["type"] == "key_release"

    def test_callback_exception_does_not_crash_listener(self) -> None:
        def bad_callback(event):
            raise RuntimeError("callback error")

        listener = EventListener(on_event=bad_callback)
        from pynput.mouse import Button

        # Must not raise
        listener._handle_click(x=0, y=0, button=Button.left, pressed=True)


class TestKeyToStr:
    def test_printable_char(self) -> None:
        from pynput.keyboard import KeyCode

        assert _key_to_str(KeyCode.from_char("z")) == "z"

    def test_special_key_enter(self) -> None:
        from pynput.keyboard import Key

        assert _key_to_str(Key.enter) == "enter"

    def test_special_key_shift(self) -> None:
        from pynput.keyboard import Key

        assert _key_to_str(Key.shift) == "shift"


# ===========================================================================
# ActionNormalizer tests
# ===========================================================================


class TestActionNormalizerClickEvents:
    """Clicks should produce CLICK actions."""

    def test_click_with_no_locator_resolution(self) -> None:
        """When pywinauto cannot resolve a locator, click action has None locator."""
        norm = ActionNormalizer()
        with patch("framework.recorder.action_normalizer._resolve_locator_at", return_value=None):
            norm.push({"type": "click", "x": 50, "y": 50, "button": "left"})
            actions = norm.flush()

        assert len(actions) == 1
        assert actions[0].action_type is ActionType.CLICK
        assert actions[0].locator is None
        assert actions[0].metadata["recorded_x"] == 50

    def test_click_with_resolved_locator(self) -> None:
        fake_locator = Locator(by="auto_id", value="OKButton")
        norm = ActionNormalizer()
        with patch(
            "framework.recorder.action_normalizer._resolve_locator_at",
            return_value=fake_locator,
        ):
            norm.push({"type": "click", "x": 100, "y": 200, "button": "left"})
            actions = norm.flush()

        assert actions[0].locator == fake_locator

    def test_click_flushes_pending_text(self) -> None:
        norm = ActionNormalizer()
        with patch("framework.recorder.action_normalizer._resolve_locator_at", return_value=None):
            norm.push({"type": "key_press", "key": "H"})
            norm.push({"type": "key_press", "key": "i"})
            norm.push({"type": "click", "x": 0, "y": 0, "button": "left"})
            actions = norm.flush()

        # First action = TYPE for buffered "Hi", second = CLICK
        assert len(actions) == 2
        assert actions[0].action_type is ActionType.TYPE
        assert actions[0].value == "Hi"
        assert actions[1].action_type is ActionType.CLICK

    def test_multiple_clicks_produce_multiple_actions(self) -> None:
        norm = ActionNormalizer()
        with patch("framework.recorder.action_normalizer._resolve_locator_at", return_value=None):
            norm.push({"type": "click", "x": 10, "y": 10, "button": "left"})
            norm.push({"type": "click", "x": 20, "y": 20, "button": "left"})
            actions = norm.flush()

        assert len(actions) == 2
        assert all(a.action_type is ActionType.CLICK for a in actions)


class TestActionNormalizerKeyEvents:
    """Keyboard events accumulate and flush as TYPE actions."""

    def test_printable_chars_accumulate(self) -> None:
        norm = ActionNormalizer()
        for ch in "Hello":
            norm.push({"type": "key_press", "key": ch})
        actions = norm.flush()
        assert len(actions) == 1
        assert actions[0].action_type is ActionType.TYPE
        assert actions[0].value == "Hello"

    def test_flush_returns_empty_when_no_events(self) -> None:
        norm = ActionNormalizer()
        actions = norm.flush()
        assert actions == []

    def test_modifier_keys_are_ignored(self) -> None:
        norm = ActionNormalizer()
        for key in ("shift", "ctrl", "alt", "caps_lock"):
            norm.push({"type": "key_press", "key": key})
        actions = norm.flush()
        assert actions == []

    def test_enter_key_flushes_text_and_records_special(self) -> None:
        norm = ActionNormalizer()
        for ch in "ok":
            norm.push({"type": "key_press", "key": ch})
        norm.push({"type": "key_press", "key": "enter"})
        actions = norm.flush()
        # Expect TYPE "ok", then TYPE "<enter>"
        assert len(actions) == 2
        assert actions[0].value == "ok"
        assert actions[1].value == "<enter>"
        assert actions[1].metadata.get("special_key") is True

    def test_tab_key_flushes_text(self) -> None:
        norm = ActionNormalizer()
        norm.push({"type": "key_press", "key": "a"})
        norm.push({"type": "key_press", "key": "tab"})
        actions = norm.flush()
        assert actions[0].value == "a"
        assert actions[1].value == "<tab>"

    def test_key_release_events_are_ignored(self) -> None:
        norm = ActionNormalizer()
        norm.push({"type": "key_release", "key": "a"})
        actions = norm.flush()
        assert actions == []

    def test_typed_text_uses_last_click_locator(self) -> None:
        fake_locator = Locator(by="auto_id", value="TextArea")
        norm = ActionNormalizer()
        with patch(
            "framework.recorder.action_normalizer._resolve_locator_at",
            return_value=fake_locator,
        ):
            norm.push({"type": "click", "x": 0, "y": 0, "button": "left"})
        for ch in "abc":
            norm.push({"type": "key_press", "key": ch})
        actions = norm.flush()

        type_action = next(a for a in actions if a.action_type is ActionType.TYPE and not a.metadata.get("special_key"))
        assert type_action.locator == fake_locator


class TestCommandModifierSuppression:
    """Characters typed while ctrl/alt/cmd is held must never reach the buffer.

    This covers the recorder-stop shortcut (Ctrl+C) and similar chorded
    combinations that must not appear in saved actions.
    """

    def test_ctrl_c_produces_no_actions(self) -> None:
        """Ctrl+C (the stop shortcut) must not generate any TYPE action."""
        norm = ActionNormalizer()
        norm.push({"type": "key_press", "key": "ctrl"})
        norm.push({"type": "key_press", "key": "c"})
        norm.push({"type": "key_release", "key": "c"})
        norm.push({"type": "key_release", "key": "ctrl"})
        actions = norm.flush()
        assert actions == [], f"Expected no actions but got: {actions}"

    def test_ctrl_c_variant_ctrl_l(self) -> None:
        """ctrl_l (left Control key) also suppresses characters."""
        norm = ActionNormalizer()
        norm.push({"type": "key_press", "key": "ctrl_l"})
        norm.push({"type": "key_press", "key": "c"})
        norm.push({"type": "key_release", "key": "c"})
        norm.push({"type": "key_release", "key": "ctrl_l"})
        actions = norm.flush()
        assert actions == []

    def test_ctrl_r_suppresses_character(self) -> None:
        norm = ActionNormalizer()
        norm.push({"type": "key_press", "key": "ctrl_r"})
        norm.push({"type": "key_press", "key": "r"})
        norm.push({"type": "key_release", "key": "r"})
        norm.push({"type": "key_release", "key": "ctrl_r"})
        actions = norm.flush()
        assert actions == []

    def test_alt_f4_produces_no_type_action(self) -> None:
        norm = ActionNormalizer()
        norm.push({"type": "key_press", "key": "alt"})
        norm.push({"type": "key_press", "key": "f4"})  # f4 is in _MODIFIER_KEYS already
        norm.push({"type": "key_release", "key": "f4"})
        norm.push({"type": "key_release", "key": "alt"})
        actions = norm.flush()
        assert actions == []

    def test_cmd_q_produces_no_action(self) -> None:
        norm = ActionNormalizer()
        norm.push({"type": "key_press", "key": "cmd"})
        norm.push({"type": "key_press", "key": "q"})
        norm.push({"type": "key_release", "key": "q"})
        norm.push({"type": "key_release", "key": "cmd"})
        actions = norm.flush()
        assert actions == []

    def test_characters_after_modifier_released_are_recorded(self) -> None:
        """Once ctrl is released, subsequent characters must be recorded normally."""
        norm = ActionNormalizer()
        norm.push({"type": "key_press", "key": "ctrl"})
        norm.push({"type": "key_press", "key": "c"})       # suppressed
        norm.push({"type": "key_release", "key": "c"})
        norm.push({"type": "key_release", "key": "ctrl"})  # modifier released
        norm.push({"type": "key_press", "key": "h"})       # should be recorded
        norm.push({"type": "key_press", "key": "i"})
        actions = norm.flush()
        assert len(actions) == 1
        assert actions[0].action_type is ActionType.TYPE
        assert actions[0].value == "hi"

    def test_text_before_ctrl_c_is_preserved(self) -> None:
        """Text typed before the stop shortcut must not be lost."""
        norm = ActionNormalizer()
        for ch in "hello":
            norm.push({"type": "key_press", "key": ch})
        norm.push({"type": "key_press", "key": "ctrl"})
        norm.push({"type": "key_press", "key": "c"})       # suppressed — stop shortcut
        norm.push({"type": "key_release", "key": "c"})
        norm.push({"type": "key_release", "key": "ctrl"})
        actions = norm.flush()
        # The buffered "hello" is flushed; Ctrl+C contributes nothing.
        assert len(actions) == 1
        assert actions[0].value == "hello"

    def test_ctrl_chord_in_middle_of_typing_session(self) -> None:
        """Ctrl+S (save shortcut) mid-session must not corrupt surrounding text."""
        norm = ActionNormalizer()
        for ch in "foo":
            norm.push({"type": "key_press", "key": ch})
        norm.push({"type": "key_press", "key": "ctrl"})
        norm.push({"type": "key_press", "key": "s"})       # suppressed
        norm.push({"type": "key_release", "key": "s"})
        norm.push({"type": "key_release", "key": "ctrl"})
        for ch in "bar":
            norm.push({"type": "key_press", "key": ch})
        actions = norm.flush()
        # "foo" flushed at click boundary; Ctrl+S suppressed; "bar" accumulates
        # Both survive as separate TYPE actions because the ctrl press flushes
        # the buffer (modifier press doesn't flush, only click/terminator does).
        # "foo" and "bar" end up in a single buffer since no flush boundary hit.
        # Actually: ctrl press triggers nothing special — buffer continues.
        # After ctrl release, "bar" appends to same buffer, so result is "foobar".
        assert len(actions) == 1
        assert actions[0].value == "foobar"

    def test_flush_clears_held_modifiers(self) -> None:
        """flush() must reset modifier tracking so the next session starts clean."""
        norm = ActionNormalizer()
        norm.push({"type": "key_press", "key": "ctrl"})  # hold ctrl
        norm.flush()  # reset state
        norm.push({"type": "key_press", "key": "c"})     # ctrl no longer held after flush
        actions = norm.flush()
        assert len(actions) == 1
        assert actions[0].value == "c"


class TestActionNormalizerNormalizeCompat:
    """normalize() backward-compatibility method."""

    def test_normalize_click_returns_single_action(self) -> None:
        norm = ActionNormalizer()
        with patch("framework.recorder.action_normalizer._resolve_locator_at", return_value=None):
            action = norm.normalize({"type": "click", "x": 1, "y": 2, "button": "left"})
        assert action.action_type is ActionType.CLICK

    def test_normalize_unknown_event_raises(self) -> None:
        norm = ActionNormalizer()
        with pytest.raises(ValueError):
            norm.normalize({"type": "unknown_event"})


# ===========================================================================
# Recorder orchestrator tests
# ===========================================================================


class TestRecorderLifecycle:
    def test_initial_state_not_running(self, tmp_path: Path) -> None:
        rec = Recorder(name="test", recordings_dir=tmp_path)
        assert rec.is_running is False

    def test_start_stop_changes_state(self, tmp_path: Path) -> None:
        rec = Recorder(name="test", recordings_dir=tmp_path)
        rec.start()
        try:
            assert rec.is_running is True
        finally:
            rec.stop()
        assert rec.is_running is False

    def test_double_start_is_safe(self, tmp_path: Path) -> None:
        rec = Recorder(name="test", recordings_dir=tmp_path)
        rec.start()
        rec.start()  # should be a no-op
        try:
            assert rec.is_running is True
        finally:
            rec.stop()


class TestRecorderEventCapture:
    """End-to-end: raw events → Recorder → persisted actions."""

    def test_recorder_routes_events_to_normalizer(self, tmp_path: Path) -> None:
        rec = Recorder(name="flow", recordings_dir=tmp_path)
        rec.start()

        with patch("framework.recorder.action_normalizer._resolve_locator_at", return_value=None):
            rec._on_raw_event({"type": "click", "x": 5, "y": 5, "button": "left"})
            rec._on_raw_event({"type": "key_press", "key": "a"})
            rec._on_raw_event({"type": "key_press", "key": "b"})

        rec.stop()
        actions = rec.actions()

        assert len(actions) == 2  # CLICK + TYPE "ab"
        assert actions[0].action_type is ActionType.CLICK
        assert actions[1].action_type is ActionType.TYPE
        assert actions[1].value == "ab"

    def test_recorder_save_persists_to_disk(self, tmp_path: Path) -> None:
        rec = Recorder(name="my_flow", recordings_dir=tmp_path)
        rec.start()

        with patch("framework.recorder.action_normalizer._resolve_locator_at", return_value=None):
            rec._on_raw_event({"type": "click", "x": 1, "y": 1, "button": "left"})

        rec.stop()
        path = rec.save()

        assert path.exists()
        assert path.name == "my_flow.json"

    def test_recorded_actions_round_trip_through_store(self, tmp_path: Path) -> None:
        """Actions saved by Recorder can be reloaded via RecordingStore."""
        rec = Recorder(name="rt_flow", recordings_dir=tmp_path)
        rec.start()

        fake_locator = Locator(by="auto_id", value="Submit")
        with patch(
            "framework.recorder.action_normalizer._resolve_locator_at",
            return_value=fake_locator,
        ):
            rec._on_raw_event({"type": "click", "x": 10, "y": 20, "button": "left"})

        rec.stop()
        rec.save()

        store = RecordingStore(base_dir=tmp_path)
        loaded = store.load("rt_flow")

        assert len(loaded) == 1
        assert loaded[0].action_type is ActionType.CLICK
        assert loaded[0].locator is not None
        assert loaded[0].locator.by == "auto_id"
        assert loaded[0].locator.value == "Submit"

    def test_recorder_empty_session_saves_empty_list(self, tmp_path: Path) -> None:
        rec = Recorder(name="empty", recordings_dir=tmp_path)
        rec.start()
        rec.stop()
        path = rec.save()

        store = RecordingStore(base_dir=tmp_path)
        actions = store.load("empty")
        assert actions == []


# ===========================================================================
# Locator resolution unit tests (mocked pywinauto)
# ===========================================================================


class TestResolveLocatorAt:
    """_resolve_locator_at with mocked Desktop to avoid real UI dependency."""

    def _make_mock_element(self, auto_id="", class_name="", window_text=""):
        element = MagicMock()
        element.automation_id.return_value = auto_id
        element.friendly_class_name.return_value = class_name
        element.class_name.return_value = class_name
        element.window_text.return_value = window_text
        return element

    def test_prefers_auto_id_over_class_name(self) -> None:
        mock_element = self._make_mock_element(auto_id="OKButton", class_name="Button")
        mock_control = MagicMock()
        mock_control.wrapper_object.return_value = mock_element

        with patch("framework.recorder.action_normalizer.Desktop") as MockDesktop:
            MockDesktop.return_value.from_point.return_value = mock_control
            locator = _resolve_locator_at(50, 50)

        assert locator is not None
        assert locator.by == "auto_id"
        assert locator.value == "OKButton"

    def test_falls_back_to_class_name_when_no_auto_id(self) -> None:
        mock_element = self._make_mock_element(auto_id="", class_name="Edit")
        mock_control = MagicMock()
        mock_control.wrapper_object.return_value = mock_element

        with patch("framework.recorder.action_normalizer.Desktop") as MockDesktop:
            MockDesktop.return_value.from_point.return_value = mock_control
            locator = _resolve_locator_at(50, 50)

        assert locator is not None
        assert locator.by == "control_type"
        assert locator.value == "Edit"

    def test_falls_back_to_title(self) -> None:
        mock_element = self._make_mock_element(auto_id="", class_name="", window_text="Save")
        mock_control = MagicMock()
        mock_control.wrapper_object.return_value = mock_element

        with patch("framework.recorder.action_normalizer.Desktop") as MockDesktop:
            MockDesktop.return_value.from_point.return_value = mock_control
            locator = _resolve_locator_at(50, 50)

        assert locator is not None
        assert locator.by == "title"
        assert locator.value == "Save"

    def test_returns_none_when_no_control_found(self) -> None:
        with patch("framework.recorder.action_normalizer.Desktop") as MockDesktop:
            MockDesktop.return_value.from_point.return_value = None
            locator = _resolve_locator_at(50, 50)
        assert locator is None

    def test_returns_none_on_pywinauto_exception(self) -> None:
        with patch("framework.recorder.action_normalizer.Desktop") as MockDesktop:
            MockDesktop.return_value.from_point.side_effect = Exception("COM error")
            locator = _resolve_locator_at(50, 50)
        assert locator is None
