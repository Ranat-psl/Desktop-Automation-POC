"""Recorder — high-level orchestrator for capturing desktop automation sessions.

Usage (programmatic)::

    from framework.recorder.recorder import Recorder

    recorder = Recorder(name="my_flow")
    recorder.start()
    # ... user interacts with the desktop ...
    recorder.stop()
    path = recorder.save()          # persists to recordings/<name>.json
    actions = recorder.actions()    # list[Action] — available immediately

Usage (CLI)::

    python -m framework.recorder.recorder --name my_flow

    Press CTRL+C to stop recording.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from framework.core.models import Action
from framework.recorder.action_normalizer import ActionNormalizer
from framework.recorder.event_listener import EventListener
from framework.recorder.recording_store import RecordingStore

_log = logging.getLogger(__name__)


class Recorder:
    """Orchestrates EventListener → ActionNormalizer → RecordingStore.

    The recorder is intentionally lightweight:
    - It does NOT require the application under test to be launched through
      the framework — just start the recorder and interact normally.
    - Recording is only required during test creation; regression runs use
      the saved JSON artefacts produced by :meth:`save`.
    - Thread-safe start/stop via the underlying EventListener.
    """

    def __init__(
        self,
        name: str,
        recordings_dir: str | Path = "recordings",
        excluded_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        self.name = name
        self._excluded_rect = excluded_rect
        self._store = RecordingStore(base_dir=recordings_dir)
        self._normalizer = ActionNormalizer()
        self._listener = EventListener(
            on_event=self._on_raw_event,
            excluded_rect=excluded_rect,
        )
        self._start_time: float | None = None
        self._stop_time: float | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin capturing desktop events."""
        if self._listener.is_running:
            _log.warning("Recorder.start() called while already running — ignoring")
            return
        self._normalizer = ActionNormalizer()  # fresh state each recording
        self._start_time = time.monotonic()
        self._listener = EventListener(
            on_event=self._on_raw_event,
            excluded_rect=self._excluded_rect,
        )
        self._listener.start()
        _log.info("Recording started — name=%r", self.name)

    def stop(self) -> None:
        """Stop capturing events and flush the normalizer buffer."""
        self._listener.stop()
        self._stop_time = time.monotonic()
        _log.info(
            "Recording stopped — name=%r  duration=%.1fs",
            self.name,
            (self._stop_time - self._start_time) if self._start_time else 0.0,
        )

    def actions(self) -> list[Action]:
        """Return all accumulated (and flushed) actions captured so far.

        Safe to call after :meth:`stop`.  Flushes any remaining buffered
        keystrokes from the normalizer before returning.
        """
        return self._normalizer.flush()

    def save(self, name: str | None = None) -> Path:
        """Persist the recorded actions to disk and return the file path.

        Calls :meth:`actions` internally, so partial buffered text will be
        flushed.
        """
        recording_name = name or self.name
        captured = self._normalizer.flush()
        path = self._store.save(recording_name, captured)
        _log.info("Recording saved: %s  (%d action(s))", path, len(captured))
        return path

    @property
    def is_running(self) -> bool:
        return self._listener.is_running

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_raw_event(self, event: dict[str, Any]) -> None:
        self._normalizer.push(event)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:  # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(description="Record desktop automation session")
    parser.add_argument("--name", default="recording", help="Recording name (used as filename)")
    parser.add_argument("--dir", default="recordings", help="Directory to save recordings")
    args = parser.parse_args()

    recorder = Recorder(name=args.name, recordings_dir=args.dir)
    recorder.start()
    print(f"Recording '{args.name}'  —  press CTRL+C to stop.\n")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()
        path = recorder.save()
        actions = recorder.actions()
        print(f"\nSaved {len(actions)} action(s) → {path}")


if __name__ == "__main__":
    _cli()
