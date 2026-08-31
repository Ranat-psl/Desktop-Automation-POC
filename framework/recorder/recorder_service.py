"""RecorderService — thin controller layer between the UI and the Recorder.

This module exists solely to keep UI-specific logic separate from the
recorder/business logic.  It delegates all real work to the existing
Day 6 :class:`~framework.recorder.recorder.Recorder` and exposes a
simple, UI-friendly API.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable

from framework.recorder.recorder import Recorder

_log = logging.getLogger(__name__)


class RecorderState(Enum):
    IDLE = auto()
    RECORDING = auto()
    STOPPED = auto()


@dataclass
class RecorderStatus:
    state: RecorderState = RecorderState.IDLE
    action_count: int = 0
    saved_path: Path | None = None
    error: str | None = None


class RecorderService:
    """Thin service layer that wraps :class:`Recorder` for the UI.

    Responsibilities:
    - Input validation (recording name, directory)
    - State tracking (IDLE / RECORDING / STOPPED)
    - Delegating start/stop/save to the underlying :class:`Recorder`
    - Exposing status via :class:`RecorderStatus`

    It does NOT create a second EventListener; the existing Recorder
    already owns one.
    """

    def __init__(
        self,
        on_status_change: Callable[[RecorderStatus], None] | None = None,
    ) -> None:
        self._recorder: Recorder | None = None
        self._status = RecorderStatus()
        self._on_status_change = on_status_change or (lambda _: None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def status(self) -> RecorderStatus:
        return self._status

    @property
    def is_recording(self) -> bool:
        return self._status.state == RecorderState.RECORDING

    def start(self, name: str, recordings_dir: str = "recordings", excluded_rect: tuple[int, int, int, int] | None = None) -> RecorderStatus:
        """Validate inputs and start the recorder.

        *excluded_rect* is an optional ``(left, top, right, bottom)`` screen
        coordinate tuple for the DA application window.  Clicks inside this
        rectangle are silently ignored so that recorder controls never pollute
        the recorded test actions.

        Returns the updated :class:`RecorderStatus`.
        """
        # --- Validation -----------------------------------------------
        name = name.strip()
        if not name:
            return self._set_error("Recording name must not be empty.")

        recordings_dir = recordings_dir.strip() or "recordings"
        dir_path = Path(recordings_dir)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return self._set_error(f"Cannot create recordings directory: {exc}")

        if self._status.state == RecorderState.RECORDING:
            return self._set_error("Already recording. Stop the current recording first.")

        # --- Delegate to Recorder -------------------------------------
        try:
            self._recorder = Recorder(
                name=name,
                recordings_dir=recordings_dir,
                excluded_rect=excluded_rect,
            )
            self._recorder.start()
        except Exception as exc:  # noqa: BLE001
            _log.exception("Recorder.start() raised an exception")
            self._recorder = None
            return self._set_error(f"Failed to start recorder: {exc}")

        self._status = RecorderStatus(state=RecorderState.RECORDING)
        self._on_status_change(self._status)
        _log.info("RecorderService: started recording %r -> %s", name, recordings_dir)
        return self._status

    def stop(self) -> RecorderStatus:
        """Stop the recorder, save the recording, and return updated status."""
        if self._status.state != RecorderState.RECORDING:
            return self._set_error("Not currently recording.")

        if self._recorder is None:
            return self._set_error("Internal error: recorder instance is missing.")

        try:
            self._recorder.stop()
            saved_path = self._recorder.save()
            action_count = len(self._recorder.actions())
        except Exception as exc:  # noqa: BLE001
            _log.exception("Recorder.stop()/save() raised an exception")
            return self._set_error(f"Failed to stop/save recording: {exc}")

        self._status = RecorderStatus(
            state=RecorderState.STOPPED,
            action_count=action_count,
            saved_path=saved_path,
        )
        self._on_status_change(self._status)
        _log.info(
            "RecorderService: stopped. %d action(s) saved to %s",
            action_count,
            saved_path,
        )
        return self._status

    def reset(self) -> None:
        """Reset to IDLE so a new recording can be started."""
        self._recorder = None
        self._status = RecorderStatus(state=RecorderState.IDLE)
        self._on_status_change(self._status)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _set_error(self, message: str) -> RecorderStatus:
        _log.warning("RecorderService error: %s", message)
        self._status = RecorderStatus(
            state=self._status.state,
            action_count=self._status.action_count,
            saved_path=self._status.saved_path,
            error=message,
        )
        self._on_status_change(self._status)
        return self._status
