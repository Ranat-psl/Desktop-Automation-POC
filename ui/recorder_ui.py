"""Recorder UI — tkinter desktop application for Day 7.

Entry point::

    python -m ui.recorder_ui

This module is a thin UI layer over the existing Day 6 recorder.
All recording logic lives in :class:`~framework.recorder.recorder_service.RecorderService`
and the underlying :class:`~framework.recorder.recorder.Recorder`.

No business logic is implemented here.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import ttk

from framework.recorder.recorder_service import RecorderService, RecorderState, RecorderStatus

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UI constants
# ---------------------------------------------------------------------------

_TITLE = "Desktop Automation — Recorder"
_PAD = {"padx": 10, "pady": 5}
_DEFAULT_DIR = "recordings"

_COLOR_IDLE = "#555555"
_COLOR_RECORDING = "#cc0000"
_COLOR_SAVED = "#007700"
_COLOR_ERROR = "#cc6600"


class RecorderUI(tk.Tk):
    """Main tkinter window for controlling recordings.

    Wires UI events to :class:`RecorderService` without embedding
    any recording logic in this class.
    """

    def __init__(self) -> None:
        super().__init__()
        self.title(_TITLE)
        self.resizable(False, False)

        self._service = RecorderService(on_status_change=self._on_status_change)

        self._build_ui()
        self._apply_state(RecorderState.IDLE, action_count=0, saved_path=None, error=None)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create and lay out all widgets."""
        main = ttk.Frame(self, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        # --- Row 0: Recording Name ------------------------------------
        ttk.Label(main, text="Recording Name:").grid(
            row=0, column=0, sticky="w", **_PAD
        )
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(main, textvariable=self._name_var, width=35)
        self._name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", **_PAD)

        # --- Row 1: Recording Directory -------------------------------
        ttk.Label(main, text="Recording Directory:").grid(
            row=1, column=0, sticky="w", **_PAD
        )
        self._dir_var = tk.StringVar(value=_DEFAULT_DIR)
        self._dir_entry = ttk.Entry(main, textvariable=self._dir_var, width=35)
        self._dir_entry.grid(row=1, column=1, columnspan=2, sticky="ew", **_PAD)

        # --- Row 2: Buttons -------------------------------------------
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=2, column=0, columnspan=3, **_PAD)

        self._start_btn = ttk.Button(
            btn_frame, text="Start Recording", command=self._on_start
        )
        self._start_btn.grid(row=0, column=0, padx=5)

        self._stop_btn = ttk.Button(
            btn_frame, text="Stop Recording", command=self._on_stop
        )
        self._stop_btn.grid(row=0, column=1, padx=5)

        # --- Row 3: Status --------------------------------------------
        ttk.Label(main, text="Status:").grid(row=3, column=0, sticky="w", **_PAD)
        self._status_var = tk.StringVar(value="Idle")
        self._status_label = tk.Label(
            main,
            textvariable=self._status_var,
            fg=_COLOR_IDLE,
            font=("TkDefaultFont", 10, "bold"),
            anchor="w",
            width=40,
        )
        self._status_label.grid(row=3, column=1, columnspan=2, sticky="w", **_PAD)

        # --- Row 4: Action Count --------------------------------------
        ttk.Label(main, text="Actions captured:").grid(
            row=4, column=0, sticky="w", **_PAD
        )
        self._count_var = tk.StringVar(value="—")
        ttk.Label(main, textvariable=self._count_var, anchor="w").grid(
            row=4, column=1, columnspan=2, sticky="w", **_PAD
        )

        # --- Row 5: Saved Path ----------------------------------------
        ttk.Label(main, text="Saved to:").grid(row=5, column=0, sticky="w", **_PAD)
        self._path_var = tk.StringVar(value="—")
        ttk.Label(
            main,
            textvariable=self._path_var,
            anchor="w",
            wraplength=320,
        ).grid(row=5, column=1, columnspan=2, sticky="w", **_PAD)

        # --- Row 6: Error / message area ------------------------------
        self._error_var = tk.StringVar(value="")
        self._error_label = tk.Label(
            main,
            textvariable=self._error_var,
            fg=_COLOR_ERROR,
            anchor="w",
            wraplength=400,
        )
        self._error_label.grid(
            row=6, column=0, columnspan=3, sticky="w", **_PAD
        )

        # Separator
        ttk.Separator(main, orient="horizontal").grid(
            row=7, column=0, columnspan=3, sticky="ew", pady=4
        )

        # --- Row 8: Quit button ---------------------------------------
        ttk.Button(main, text="Quit", command=self._on_quit).grid(
            row=8, column=2, sticky="e", **_PAD
        )

        main.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        """Handle 'Start Recording' button click."""
        self._clear_error()
        name = self._name_var.get()
        directory = self._dir_var.get()

        # Run service call in a background thread so the UI stays responsive
        # while pynput hooks are being set up.
        threading.Thread(
            target=self._start_recording,
            args=(name, directory),
            daemon=True,
        ).start()

    def _start_recording(self, name: str, directory: str) -> None:
        status = self._service.start(name=name, recordings_dir=directory)
        self.after(0, lambda: self._handle_status(status))

    def _on_stop(self) -> None:
        """Handle 'Stop Recording' button click."""
        self._clear_error()
        threading.Thread(
            target=self._stop_recording,
            daemon=True,
        ).start()

    def _stop_recording(self) -> None:
        status = self._service.stop()
        self.after(0, lambda: self._handle_status(status))

    def _on_quit(self) -> None:
        if self._service.is_recording:
            self._service.stop()
        self.destroy()

    # ------------------------------------------------------------------
    # Status handling
    # ------------------------------------------------------------------

    def _on_status_change(self, status: RecorderStatus) -> None:
        """Called from RecorderService (possibly a background thread)."""
        self.after(0, lambda: self._handle_status(status))

    def _handle_status(self, status: RecorderStatus) -> None:
        """Apply a :class:`RecorderStatus` to the UI (must run on main thread)."""
        if status.error:
            self._show_error(status.error)
        self._apply_state(
            state=status.state,
            action_count=status.action_count,
            saved_path=status.saved_path,
            error=status.error,
        )

    def _apply_state(
        self,
        state: RecorderState,
        action_count: int,
        saved_path,
        error: str | None,
    ) -> None:
        if state == RecorderState.IDLE:
            self._status_var.set("Idle")
            self._status_label.config(fg=_COLOR_IDLE)
            self._start_btn.config(state="normal")
            self._stop_btn.config(state="disabled")
            self._name_entry.config(state="normal")
            self._dir_entry.config(state="normal")

        elif state == RecorderState.RECORDING:
            self._status_var.set("Recording…")
            self._status_label.config(fg=_COLOR_RECORDING)
            self._start_btn.config(state="disabled")
            self._stop_btn.config(state="normal")
            self._name_entry.config(state="disabled")
            self._dir_entry.config(state="disabled")
            self._count_var.set("—")
            self._path_var.set("—")

        elif state == RecorderState.STOPPED:
            self._status_var.set("Saved / Stopped")
            self._status_label.config(fg=_COLOR_SAVED)
            self._start_btn.config(state="normal")
            self._stop_btn.config(state="disabled")
            self._name_entry.config(state="normal")
            self._dir_entry.config(state="normal")
            self._count_var.set(str(action_count))
            if saved_path is not None:
                self._path_var.set(str(saved_path))
            # Reset service for next recording
            self._service.reset()

        if error and state not in (RecorderState.RECORDING,):
            # Re-enable inputs so the user can fix the error
            self._start_btn.config(state="normal")
            self._stop_btn.config(state="disabled")
            self._name_entry.config(state="normal")
            self._dir_entry.config(state="normal")

    def _show_error(self, message: str) -> None:
        self._error_var.set(f"Error: {message}")

    def _clear_error(self) -> None:
        self._error_var.set("")


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.DEBUG)
    app = RecorderUI()
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
