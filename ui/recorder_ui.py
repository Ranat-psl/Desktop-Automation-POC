"""Recorder screen for the single-root desktop shell."""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import ttk

from framework.recorder.recorder_service import RecorderService, RecorderState, RecorderStatus

_log = logging.getLogger(__name__)

_TITLE = "Desktop Automation - Recorder"
_PAD = {"padx": 10, "pady": 5}

_COLOR_IDLE = "#555555"
_COLOR_RECORDING = "#cc0000"
_COLOR_SAVED = "#007700"
_COLOR_ERROR = "#cc6600"


class RecorderUI(ttk.Frame):
    """Embeddable recorder screen that delegates all logic to RecorderService."""

    def __init__(self, master: tk.Misc, app_controller=None) -> None:
        super().__init__(master)
        self._app_controller = app_controller
        self._service = RecorderService(on_status_change=self._on_status_change)

        self._build_ui()
        self._apply_state(RecorderState.IDLE, action_count=0, saved_path=None, error=None)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        main = ttk.Frame(self, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Recorder", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", **_PAD
        )

        ttk.Label(main, text="Recording Name:").grid(
            row=1, column=0, sticky="w", **_PAD
        )
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(main, textvariable=self._name_var, width=35)
        self._name_entry.grid(row=1, column=1, columnspan=2, sticky="ew", **_PAD)

        ttk.Label(main, text="Recording Directory:").grid(
            row=2, column=0, sticky="w", **_PAD
        )
        self._dir_var = tk.StringVar(value="(select a workspace first)")
        self._dir_entry = ttk.Entry(main, textvariable=self._dir_var, width=35, state="readonly")
        self._dir_entry.grid(row=2, column=1, columnspan=2, sticky="ew", **_PAD)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=3, column=0, columnspan=3, sticky="w", **_PAD)

        self._start_btn = ttk.Button(
            btn_frame,
            text="Start Recording",
            command=self._on_start,
        )
        self._start_btn.grid(row=0, column=0, padx=5)

        self._stop_btn = ttk.Button(
            btn_frame,
            text="Stop Recording",
            command=self._on_stop,
        )
        self._stop_btn.grid(row=0, column=1, padx=5)

        self._save_btn = ttk.Button(
            btn_frame,
            text="Save Recording",
            command=self._on_save,
        )
        self._save_btn.grid(row=0, column=2, padx=5)

        ttk.Label(main, text="Status:").grid(row=4, column=0, sticky="w", **_PAD)
        self._status_var = tk.StringVar(value="Idle")
        self._status_label = tk.Label(
            main,
            textvariable=self._status_var,
            fg=_COLOR_IDLE,
            font=("TkDefaultFont", 10, "bold"),
            anchor="w",
            width=40,
        )
        self._status_label.grid(row=4, column=1, columnspan=2, sticky="w", **_PAD)

        ttk.Label(main, text="Actions captured:").grid(
            row=5, column=0, sticky="w", **_PAD
        )
        self._count_var = tk.StringVar(value="-")
        ttk.Label(main, textvariable=self._count_var, anchor="w").grid(
            row=5, column=1, columnspan=2, sticky="w", **_PAD
        )

        ttk.Label(main, text="Saved to:").grid(row=6, column=0, sticky="w", **_PAD)
        self._path_var = tk.StringVar(value="-")
        ttk.Label(
            main,
            textvariable=self._path_var,
            anchor="w",
            wraplength=500,
        ).grid(row=6, column=1, columnspan=2, sticky="w", **_PAD)

        ttk.Label(main, text="Recording Timeline:").grid(row=7, column=0, sticky="nw", **_PAD)
        timeline_frame = ttk.Frame(main)
        timeline_frame.grid(row=7, column=1, columnspan=2, sticky="nsew", **_PAD)
        timeline_frame.columnconfigure(0, weight=1)
        timeline_frame.rowconfigure(0, weight=1)

        self._events_list = tk.Listbox(timeline_frame, height=8, exportselection=False)
        self._events_list.grid(row=0, column=0, sticky="nsew")
        timeline_scroll = ttk.Scrollbar(timeline_frame, orient="vertical", command=self._events_list.yview)
        timeline_scroll.grid(row=0, column=1, sticky="ns")
        self._events_list.configure(yscrollcommand=timeline_scroll.set)

        self._error_var = tk.StringVar(value="")
        self._error_label = tk.Label(
            main,
            textvariable=self._error_var,
            fg=_COLOR_ERROR,
            anchor="w",
            wraplength=600,
        )
        self._error_label.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky="w",
            **_PAD,
        )

    # ------------------------------------------------------------------
    # App-shell hooks
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        self.focus_set()
        self._refresh_workspace_dir()

    def _refresh_workspace_dir(self) -> None:
        """Update the directory field from the currently active workspace."""
        recordings_dir = self._resolve_workspace_recordings_dir()
        if recordings_dir is not None:
            self._dir_var.set(str(recordings_dir))
        else:
            self._dir_var.set("(select a workspace first)")

    def _resolve_workspace_recordings_dir(self):
        """Return Path to the workspace recordings dir, or None if no workspace is active."""
        if self._app_controller is None:
            return None
        if not hasattr(self._app_controller, "get_active_workspace"):
            return None
        ws = self._app_controller.get_active_workspace()
        if ws is None:
            return None
        try:
            return ws.recordings_dir_for()
        except Exception:
            _log.exception("Failed to resolve workspace recordings directory")
            return None

    def handle_exit_request(self) -> bool:
        """Return True if the shell can safely close."""
        if not self._service.is_recording:
            return True

        try:
            from tkinter import messagebox

            should_stop = messagebox.askyesno(
                title="Active Recording",
                message="A recording is in progress. Stop and save before exit?",
                parent=self.winfo_toplevel(),
            )
            if not should_stop:
                return False
            self._stop_recording()
            self.update_idletasks()
            return True
        except Exception:  # noqa: BLE001
            _log.exception("Failed to stop recording during application exit.")
            return False

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        self._clear_error()
        name = self._name_var.get()

        # Validate workspace is selected before allowing recording to start.
        recordings_dir = self._resolve_workspace_recordings_dir()
        if recordings_dir is None:
            self._show_error(
                "No workspace selected. Please open a workspace in the Workspace screen before recording."
            )
            return

        directory = str(recordings_dir)
        self._dir_var.set(directory)

        threading.Thread(
            target=self._start_recording,
            args=(name, directory),
            daemon=True,
        ).start()

    def _start_recording(self, name: str, directory: str) -> None:
        # Capture the DA application's screen rectangle *before* recording
        # starts so that clicks on its own controls are excluded from the
        # recorded test actions.
        excluded_rect = self._get_app_screen_rect()
        status = self._service.start(
            name=name,
            recordings_dir=directory,
            excluded_rect=excluded_rect,
        )
        self.after(0, lambda: self._handle_status(status))

    def _get_app_screen_rect(self) -> tuple[int, int, int, int] | None:
        """Return (left, top, right, bottom) of the DA app window in screen coords."""
        try:
            root = self.winfo_toplevel()
            left = root.winfo_rootx()
            top = root.winfo_rooty()
            right = left + root.winfo_width()
            bottom = top + root.winfo_height()
            return (left, top, right, bottom)
        except Exception:
            _log.debug("Could not determine DA app window rect for exclusion")
            return None

    def _on_stop(self) -> None:
        self._clear_error()
        threading.Thread(
            target=self._stop_recording,
            daemon=True,
        ).start()

    def _stop_recording(self) -> None:
        status = self._service.stop()
        self.after(0, lambda: self._handle_status(status))

    def _on_save(self) -> None:
        """Expose explicit save intent while preserving RecorderService contract.

        RecorderService persists on stop, so this action delegates to stop when
        recording is active and otherwise gives a clear status reminder.
        """
        self._clear_error()
        if self._service.is_recording:
            self._on_stop()
            return

        if self._service.status.saved_path is not None:
            self._status_var.set("Recording is already saved.")
            self._status_label.config(fg=_COLOR_SAVED)
            return

        self._show_error("No active recording to save.")

    # ------------------------------------------------------------------
    # Status handling
    # ------------------------------------------------------------------

    def _on_status_change(self, status: RecorderStatus) -> None:
        self.after(0, lambda: self._handle_status(status))

    def _handle_status(self, status: RecorderStatus) -> None:
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
            self._save_btn.config(state="disabled")
            self._name_entry.config(state="normal")
            self._dir_entry.config(state="normal")

        elif state == RecorderState.RECORDING:
            self._status_var.set("Recording...")
            self._status_label.config(fg=_COLOR_RECORDING)
            self._start_btn.config(state="disabled")
            self._stop_btn.config(state="normal")
            self._save_btn.config(state="normal")
            self._name_entry.config(state="disabled")
            self._dir_entry.config(state="disabled")
            self._count_var.set("-")
            self._path_var.set("-")
            # Clear stale timeline entries from any previous recording session
            # before appending the new session's first message.
            self._events_list.delete(0, tk.END)
            self._append_event("Recording started.")

        elif state == RecorderState.STOPPED:
            self._status_var.set("Saved / Stopped")
            self._status_label.config(fg=_COLOR_SAVED)
            self._start_btn.config(state="normal")
            self._stop_btn.config(state="disabled")
            self._save_btn.config(state="normal")
            self._name_entry.config(state="normal")
            self._dir_entry.config(state="normal")
            self._count_var.set(str(action_count))
            if saved_path is not None:
                self._path_var.set(str(saved_path))
                self._append_event(f"Saved recording: {saved_path}")
            self._append_event(f"Captured actions: {action_count}")
            self._service.reset()

        if error and state not in (RecorderState.RECORDING,):
            self._start_btn.config(state="normal")
            self._stop_btn.config(state="disabled")
            self._name_entry.config(state="normal")
            self._dir_entry.config(state="normal")

    def _append_event(self, text: str) -> None:
        self._events_list.insert(tk.END, text)
        self._events_list.yview_moveto(1.0)

    def _show_error(self, message: str) -> None:
        self._error_var.set(f"Error: {message}")

    def _clear_error(self) -> None:
        self._error_var.set("")


def main() -> None:  # pragma: no cover
    from ui.app_shell import AppShell

    logging.basicConfig(level=logging.DEBUG)
    app = AppShell(default_screen="recorder")
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
