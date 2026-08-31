"""Single-root application shell for desktop automation screens."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from ui.editor_manager import get_editor_manager
from ui.recorder_ui import RecorderUI
from ui.workspace_ui import WorkspaceManagementUI

_log = logging.getLogger(__name__)

_APP_TITLE = "Persistent Desktop Automation"
_DEFAULT_SIZE = "1180x760"
_MIN_WIDTH = 980
_MIN_HEIGHT = 680

_HEADER_BG = "#0d2b45"
_HEADER_TEXT = "#ffffff"
_SUBHEADER_TEXT = "#d9e6f2"


class AppShell(tk.Tk):
    """Owns one Tk root, one mainloop, and in-window screen navigation."""

    def __init__(self, default_screen: str = "workspace") -> None:
        super().__init__()
        self.title(_APP_TITLE)
        self.geometry(_DEFAULT_SIZE)
        self.minsize(_MIN_WIDTH, _MIN_HEIGHT)

        self._screens: dict[str, ttk.Frame] = {}
        self._current_screen_name: str | None = None

        self._build_layout()
        self._register_screens()
        self.show_screen(default_screen)

        self.protocol("WM_DELETE_WINDOW", self._on_exit)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = tk.Frame(self, bg=_HEADER_BG, padx=14, pady=10)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        logo_box = tk.Frame(
            header,
            bg=_HEADER_BG,
            highlightbackground="#3f6484",
            highlightthickness=1,
            width=52,
            height=52,
        )
        logo_box.grid(row=0, column=0, padx=(0, 10), pady=2)
        logo_box.grid_propagate(False)
        tk.Label(
            logo_box,
            text="PS",
            bg=_HEADER_BG,
            fg=_HEADER_TEXT,
            font=("Segoe UI", 12, "bold"),
        ).place(relx=0.5, rely=0.5, anchor="center")

        title_frame = tk.Frame(header, bg=_HEADER_BG)
        title_frame.grid(row=0, column=1, sticky="w")
        tk.Label(
            title_frame,
            text="Persistent Systems",
            bg=_HEADER_BG,
            fg=_HEADER_TEXT,
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            title_frame,
            text="Desktop Automation",
            bg=_HEADER_BG,
            fg=_SUBHEADER_TEXT,
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w")

        nav = ttk.Frame(self, padding=(10, 8))
        nav.grid(row=1, column=0, sticky="ew")
        nav.columnconfigure(6, weight=1)

        self._workspace_nav_btn = ttk.Button(nav, text="Workspace", command=lambda: self.show_screen("workspace"))
        self._workspace_nav_btn.grid(row=0, column=0, padx=4, sticky="w")

        self._recorder_nav_btn = ttk.Button(nav, text="Recorder", command=lambda: self.show_screen("recorder"))
        self._recorder_nav_btn.grid(row=0, column=1, padx=4, sticky="w")

        self._testcases_nav_btn = ttk.Button(nav, text="Test Cases / Recordings", command=self._open_test_cases)
        self._testcases_nav_btn.grid(row=0, column=2, padx=4, sticky="w")

        self._reports_nav_btn = ttk.Button(nav, text="Reports", command=self._open_reports)
        self._reports_nav_btn.grid(row=0, column=3, padx=4, sticky="w")

        self._help_nav_btn = ttk.Button(nav, text="Help", command=self._on_help)
        self._help_nav_btn.grid(row=0, column=4, padx=4, sticky="w")

        self._settings_nav_btn = ttk.Button(nav, text="Settings", command=self._on_settings)
        self._settings_nav_btn.grid(row=0, column=5, padx=4, sticky="w")

        self._exit_nav_btn = ttk.Button(nav, text="Exit", command=self._on_exit)
        self._exit_nav_btn.grid(row=0, column=7, padx=4, sticky="e")

        self._content = ttk.Frame(self)
        self._content.grid(row=2, column=0, sticky="nsew")
        self._content.columnconfigure(0, weight=1)
        self._content.rowconfigure(0, weight=1)

    def _register_screens(self) -> None:
        workspace = WorkspaceManagementUI(self._content, app_controller=self)
        recorder = RecorderUI(self._content, app_controller=self)

        self._screens["workspace"] = workspace
        self._screens["recorder"] = recorder

        for frame in self._screens.values():
            frame.grid(row=0, column=0, sticky="nsew")

    def show_screen(self, name: str) -> None:
        target = self._screens.get(name)
        if target is None:
            raise KeyError(f"Unknown screen: {name}")

        target.tkraise()
        self._current_screen_name = name
        if hasattr(target, "on_show"):
            target.on_show()

    def _open_test_cases(self) -> None:
        self.show_screen("workspace")
        workspace = self._screens["workspace"]
        if hasattr(workspace, "focus_recordings"):
            workspace.focus_recordings()

    def _open_reports(self) -> None:
        self.show_screen("workspace")
        workspace = self._screens["workspace"]
        if hasattr(workspace, "focus_reports"):
            workspace.focus_reports()

    def get_active_workspace(self):
        """Return the currently active WorkspaceService, or None if no workspace is selected.

        Used by RecorderUI to resolve the recordings directory.
        """
        workspace_screen = self._screens.get("workspace")
        if workspace_screen is None:
            return None
        return getattr(workspace_screen, "_workspace_service", None)

    def _on_help(self) -> None:
        from tkinter import messagebox

        messagebox.showinfo(
            title="Help",
            message=(
                "Use Workspace to create/open workspaces and run recordings.\n"
                "Use Recorder to capture new recordings."
            ),
            parent=self,
        )

    def _on_settings(self) -> None:
        from tkinter import messagebox

        messagebox.showinfo(
            title="Settings",
            message="Settings screen is not implemented in this phase.",
            parent=self,
        )

    def _on_exit(self) -> None:
        recorder = self._screens.get("recorder")
        if recorder is not None and hasattr(recorder, "handle_exit_request"):
            if not recorder.handle_exit_request():
                return

        # Clean up any launched editor processes.
        try:
            editor_manager = get_editor_manager()
            editor_manager.cleanup()
        except Exception:
            pass

        self.destroy()


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    app = AppShell(default_screen="workspace")
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
