"""Day 7 — Recorder UI smoke tests.

These tests verify:
1. RecorderService state machine (no real event capture).
2. RecorderUI can be instantiated (headless, Tk withdrawn).
3. Day 6 compatibility — RecorderService correctly delegates to Recorder.

All tests mock pynput listeners so they run without a real desktop session.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from framework.recorder.recorder_service import (
    RecorderService,
    RecorderState,
    RecorderStatus,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_service(callback=None) -> RecorderService:
    """Return a RecorderService with pynput listeners fully mocked."""
    return RecorderService(on_status_change=callback or (lambda _: None))


def _patch_pynput():
    """Context manager: mock pynput so no real OS hooks are registered."""
    return patch(
        "framework.recorder.event_listener.mouse.Listener",
        MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock())),
    ), patch(
        "framework.recorder.event_listener.keyboard.Listener",
        MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock())),
    )


# ===========================================================================
# RecorderService — state machine
# ===========================================================================


class TestRecorderServiceInitialState:
    def test_initial_state_is_idle(self) -> None:
        svc = _make_service()
        assert svc.status.state == RecorderState.IDLE

    def test_is_recording_false_initially(self) -> None:
        svc = _make_service()
        assert svc.is_recording is False


class TestRecorderServiceValidation:
    def test_empty_name_returns_error(self) -> None:
        svc = _make_service()
        status = svc.start(name="", recordings_dir="recordings")
        assert status.error is not None
        assert "empty" in status.error.lower()
        assert status.state == RecorderState.IDLE

    def test_whitespace_name_returns_error(self) -> None:
        svc = _make_service()
        status = svc.start(name="   ", recordings_dir="recordings")
        assert status.error is not None

    def test_stop_when_not_recording_returns_error(self) -> None:
        svc = _make_service()
        status = svc.stop()
        assert status.error is not None
        assert status.state == RecorderState.IDLE

    def test_double_start_returns_error(self, tmp_path) -> None:
        svc = _make_service()
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="test_flow", recordings_dir=str(tmp_path))
            assert svc.is_recording is True
            status = svc.start(name="test_flow2", recordings_dir=str(tmp_path))
            assert status.error is not None
            assert "already recording" in status.error.lower()
            # Cleanup
            svc._recorder.stop()

    def test_invalid_directory_returns_error(self, tmp_path) -> None:
        # Use a path that cannot be created (file exists with that name)
        blocker = tmp_path / "blocked"
        blocker.write_text("I am a file, not a dir")
        svc = _make_service()
        status = svc.start(name="flow", recordings_dir=str(blocker / "subdir"))
        assert status.error is not None


class TestRecorderServiceStartStop:
    def test_start_transitions_to_recording(self, tmp_path) -> None:
        svc = _make_service()
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            status = svc.start(name="flow1", recordings_dir=str(tmp_path))
            assert status.state == RecorderState.RECORDING
            assert status.error is None
            assert svc.is_recording is True
            svc._recorder.stop()

    def test_stop_transitions_to_stopped(self, tmp_path) -> None:
        svc = _make_service()
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="flow2", recordings_dir=str(tmp_path))
            status = svc.stop()
            assert status.state == RecorderState.STOPPED
            assert status.error is None

    def test_stop_creates_json_file(self, tmp_path) -> None:
        svc = _make_service()
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="my_recording", recordings_dir=str(tmp_path))
            status = svc.stop()
            assert status.saved_path is not None
            assert status.saved_path.exists()
            assert status.saved_path.suffix == ".json"

    def test_stop_saved_path_matches_name(self, tmp_path) -> None:
        svc = _make_service()
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="my_named_flow", recordings_dir=str(tmp_path))
            status = svc.stop()
            assert "my_named_flow" in status.saved_path.name

    def test_stop_json_format_is_envelope(self, tmp_path) -> None:
        """Verify the saved JSON uses the versioned envelope format {meta, actions}.

        The format changed from a flat list (Day 6) to a dict envelope in the
        click-reliability phase so that recording-level metadata (screen resolution)
        can be stored alongside actions.  Backward-compat load still handles
        flat lists.
        """
        svc = _make_service()
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="format_check", recordings_dir=str(tmp_path))
            status = svc.stop()
            data = json.loads(status.saved_path.read_text(encoding="utf-8"))
            assert isinstance(data, dict), "New format must be an envelope dict"
            assert "actions" in data, "Envelope must contain 'actions' key"
            assert "meta" in data, "Envelope must contain 'meta' key"
            assert isinstance(data["actions"], list)

    def test_action_count_is_non_negative(self, tmp_path) -> None:
        svc = _make_service()
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="count_check", recordings_dir=str(tmp_path))
            status = svc.stop()
            assert status.action_count >= 0


class TestRecorderServiceCallback:
    def test_callback_called_on_start(self, tmp_path) -> None:
        calls: list[RecorderStatus] = []
        svc = RecorderService(on_status_change=calls.append)
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="cb_flow", recordings_dir=str(tmp_path))
            assert len(calls) >= 1
            assert calls[-1].state == RecorderState.RECORDING
            svc._recorder.stop()

    def test_callback_called_on_stop(self, tmp_path) -> None:
        calls: list[RecorderStatus] = []
        svc = RecorderService(on_status_change=calls.append)
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="cb_flow2", recordings_dir=str(tmp_path))
            calls.clear()
            svc.stop()
            assert len(calls) >= 1
            assert calls[-1].state == RecorderState.STOPPED

    def test_callback_called_on_error(self) -> None:
        calls: list[RecorderStatus] = []
        svc = RecorderService(on_status_change=calls.append)
        svc.start(name="", recordings_dir="recordings")
        assert any(c.error for c in calls)

    def test_callback_called_on_reset(self) -> None:
        calls: list[RecorderStatus] = []
        svc = RecorderService(on_status_change=calls.append)
        svc.reset()
        assert calls[-1].state == RecorderState.IDLE


class TestRecorderServiceReset:
    def test_reset_transitions_to_idle(self, tmp_path) -> None:
        svc = _make_service()
        mouse_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        kb_mock = MagicMock(return_value=MagicMock(start=MagicMock(), stop=MagicMock(), join=MagicMock()))
        with patch("framework.recorder.event_listener.mouse.Listener", mouse_mock), \
             patch("framework.recorder.event_listener.keyboard.Listener", kb_mock):
            svc.start(name="flow_r", recordings_dir=str(tmp_path))
            svc.stop()
            svc.reset()
            assert svc.status.state == RecorderState.IDLE


# ===========================================================================
# RecorderUI — headless instantiation
# ===========================================================================


class TestRecorderUIInstantiation:
    """Verify the UI can be constructed without a visible display."""

    @pytest.fixture(autouse=True)
    def _patch_tk_mainloop(self, monkeypatch):
        # Prevent mainloop from blocking tests
        monkeypatch.setattr(tk.Tk, "mainloop", lambda self: None)

    def _build_screen(self):
        from ui.recorder_ui import RecorderUI

        root = tk.Tk()
        root.withdraw()
        screen = RecorderUI(root)
        screen.grid(row=0, column=0)
        root.update_idletasks()
        return root, screen

    def test_ui_can_be_instantiated(self) -> None:
        try:
            root, screen = self._build_screen()
            assert screen.winfo_exists() == 1
            root.destroy()
        except tk.TclError as exc:
            pytest.skip(f"No display available: {exc}")

    def test_ui_default_directory_shows_workspace_prompt(self) -> None:
        """Without a workspace selected, dir field shows a prompt instead of a raw path."""
        try:
            root, screen = self._build_screen()
            # No app_controller is provided in _build_screen, so no workspace is
            # available.  The field must not silently default to the project-root
            # recordings directory; it should prompt the user to select a workspace.
            dir_val = screen._dir_var.get()
            assert dir_val != "recordings", (
                "Directory must not silently fall back to the project-root 'recordings' directory"
            )
            root.destroy()
        except tk.TclError as exc:
            pytest.skip(f"No display available: {exc}")

    def test_ui_start_btn_initially_enabled(self) -> None:
        try:
            root, screen = self._build_screen()
            assert str(screen._start_btn["state"]) == "normal"
            root.destroy()
        except tk.TclError as exc:
            pytest.skip(f"No display available: {exc}")

    def test_ui_stop_btn_initially_disabled(self) -> None:
        try:
            root, screen = self._build_screen()
            assert str(screen._stop_btn["state"]) == "disabled"
            root.destroy()
        except tk.TclError as exc:
            pytest.skip(f"No display available: {exc}")

    def test_ui_empty_name_shows_error(self) -> None:
        try:
            root, screen = self._build_screen()
            screen._name_var.set("")
            # Call _start_recording directly (bypasses thread) to keep test deterministic
            screen._clear_error()
            screen._start_recording(name="", directory="recordings")
            root.update()
            # After start with empty name, the error label should be set
            assert screen._error_var.get() != ""
            root.destroy()
        except tk.TclError as exc:
            pytest.skip(f"No display available: {exc}")
