"""Workspace Management screen for the single-root desktop shell."""
from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

from framework.driver.desktop_driver import DesktopDriver
from framework.playback.executor import PlaybackExecutor
from framework.recorder.recording_store import RecordingStore
from framework.reporting.recording_report import generate_recording_report
from framework.workspace.models import validate_name
from framework.workspace.recent_workspace import load_recent, save_recent
from framework.workspace.root_resolver import resolve_default_workspace_root
from framework.workspace.workspace_service import WorkspaceError, WorkspaceNotFoundError, WorkspaceService
from ui.editor_manager import get_editor_manager
from ui.folder_picker import FolderPickerAsync
from ui.tooltip import HoverTooltip

_log = logging.getLogger(__name__)

_TITLE = "Persistent Desktop Automation - Workspace Management"

_COLOR_HEADER_BG = "#0d2b45"
_COLOR_HEADER_TEXT = "#ffffff"
_COLOR_SURFACE = "#f4f6f8"
_COLOR_PANEL = "#ffffff"
_COLOR_BORDER = "#d7dde3"
_COLOR_TEXT = "#22313f"
_COLOR_PRIMARY = "#1f5f8b"
_COLOR_SECONDARY = "#6b7785"
_COLOR_SUCCESS = "#1f7a3e"
_COLOR_ERROR = "#b42318"
_COLOR_WARNING = "#b86400"
_COLOR_HELP_BG = "#e6eef5"
_COLOR_HELP_BORDER = "#5d7992"
_COLOR_HELP_TEXT = "#1f3f59"


@dataclass
class RecordingItem:
    test_name: str
    json_path: Path
    source: str


class WorkspaceManagementUI(ttk.Frame):
    """Embeddable workspace management screen (no root/mainloop ownership)."""

    def __init__(self, master: tk.Misc, app_controller=None) -> None:
        super().__init__(master, style="App.TFrame")
        self._app_controller = app_controller

        self._workspace_service: WorkspaceService | None = None
        self._recordings: list[RecordingItem] = []
        self._recording_row_map: dict[str, RecordingItem] = {}
        self._tooltips: list[HoverTooltip] = []
        self._default_workspace_root = resolve_default_workspace_root()

        self._configure_styles()
        self._build_ui()

        self._last_report_path: Path | None = None

        # Restore most-recently-used workspace (best-effort).
        recent = load_recent()
        if recent is not None:
            loaded = self._try_load_workspace([recent])
            if loaded is not None:
                self._workspace_service = loaded
                self._workspace_path_var.set(str(loaded.info.root))
                self._set_selected_workspace_text(loaded.info.root)
                self._workspace_name_var.set(loaded.info.name if hasattr(loaded.info, "name") else recent.name)
                self._refresh_recordings_view()
                self._set_status(f"Workspace restored: {loaded.info.root}", level="success")
            else:
                self._workspace_path_var.set(str(self._default_workspace_root))
                self._set_selected_workspace_text(None)
                self._set_status(
                    "No workspace selected. Create or open a workspace to view available recordings.",
                    level="info",
                )
                self._refresh_recordings_view()
        else:
            self._workspace_path_var.set(str(self._default_workspace_root))
            self._set_selected_workspace_text(None)
            self._set_status(
                "No workspace selected. Create or open a workspace to view available recordings.",
                level="info",
            )
            self._refresh_recordings_view()

        self._workspace_name_var.trace_add("write", self._on_input_changed)
        self._workspace_path_var.trace_add("write", self._on_input_changed)
        self.bind("<Configure>", self._on_window_resize)
        self._update_button_states()

    def _configure_styles(self) -> None:
        self.configure(style="App.TFrame")
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("App.TFrame", background=_COLOR_SURFACE)
        style.configure("Panel.TFrame", background=_COLOR_PANEL)
        style.configure("Panel.TLabel", background=_COLOR_PANEL, foreground=_COLOR_TEXT, font=("Segoe UI", 10))
        style.configure("FieldLabel.TLabel", background=_COLOR_PANEL, foreground="#2e4053", font=("Segoe UI", 10, "bold"))
        style.configure("Section.TLabelframe", background=_COLOR_PANEL, bordercolor=_COLOR_BORDER, borderwidth=1, relief="solid")
        style.configure("Section.TLabelframe.Label", background=_COLOR_PANEL, foreground="#1e3246", font=("Segoe UI", 10, "bold"))

        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            foreground="#ffffff",
            background=_COLOR_PRIMARY,
            borderwidth=0,
            padding=(12, 8),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#194f73"), ("disabled", "#9fb4c8")],
            foreground=[("disabled", "#eef3f7")],
        )

        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 10),
            foreground="#ffffff",
            background=_COLOR_SECONDARY,
            borderwidth=0,
            padding=(10, 8),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#56626e"), ("disabled", "#bcc4cc")],
            foreground=[("disabled", "#f4f7fa")],
        )

        style.configure("Main.TEntry", padding=(6, 6))
        style.configure("Recording.Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Recording.Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        content = ttk.Frame(self, style="App.TFrame", padding=14)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        # Screen-specific title
        title_frame = ttk.Frame(content, style="App.TFrame")
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        title_label = ttk.Label(
            title_frame,
            text="Workspace Management",
            font=("Segoe UI", 14, "bold"),
            background="#f4f6f8",
            foreground="#22313f",
        )
        title_label.pack(side="left")

        content_inner = ttk.Frame(content, style="App.TFrame")
        content_inner.grid(row=1, column=0, sticky="nsew")
        content_inner.columnconfigure(0, weight=1)
        content_inner.rowconfigure(1, weight=1)

        self._build_workspace_section(content_inner)
        self._build_recordings_section(content_inner)
        self._build_reporting_section(content_inner)
        self._build_status_section(content_inner)

    def _build_workspace_section(self, parent: ttk.Frame) -> None:
        workspace_panel = ttk.LabelFrame(parent, text="WORKSPACE", style="Section.TLabelframe", padding=12)
        workspace_panel.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        workspace_panel.columnconfigure(1, weight=1)

        ttk.Label(workspace_panel, text="Workspace Name", style="FieldLabel.TLabel").grid(
            row=0, column=0, sticky="w", padx=(2, 8), pady=6
        )
        self._workspace_name_var = tk.StringVar(value="MyWorkspace")
        ttk.Entry(workspace_panel, textvariable=self._workspace_name_var, style="Main.TEntry").grid(
            row=0, column=1, sticky="ew", pady=6
        )
        self._workspace_name_help = self._create_help_icon(workspace_panel)
        self._workspace_name_help.grid(row=0, column=2, sticky="w", pady=6)
        self._tooltips.append(
            HoverTooltip(
                self._workspace_name_help,
                "Enter the name of the workspace you want to create or manage.",
                wraplength=320,
            )
        )

        ttk.Label(workspace_panel, text="Workspace Path", style="FieldLabel.TLabel").grid(
            row=1, column=0, sticky="w", padx=(2, 8), pady=6
        )
        self._workspace_path_var = tk.StringVar()
        ttk.Entry(workspace_panel, textvariable=self._workspace_path_var, style="Main.TEntry").grid(
            row=1, column=1, sticky="ew", pady=6
        )

        path_controls = ttk.Frame(workspace_panel, style="Panel.TFrame")
        path_controls.grid(row=1, column=2, sticky="ew", padx=(8, 0), pady=6)

        self._workspace_path_help = self._create_help_icon(path_controls)
        self._workspace_path_help.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self._tooltips.append(
            HoverTooltip(
                self._workspace_path_help,
                "Base folder where Desktop Automation stores workspaces. A default Windows-safe location is provided automatically. Use Browse to choose another folder.",
                wraplength=360,
            )
        )

        self._browse_btn = ttk.Button(
            path_controls,
            text="Browse...",
            style="Secondary.TButton",
            command=self._on_browse,
        )
        self._browse_btn.grid(row=0, column=1, sticky="ew")

        action_row = ttk.Frame(workspace_panel, style="Panel.TFrame")
        action_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        action_row.columnconfigure(3, weight=1)

        self._create_btn = ttk.Button(
            action_row,
            text="Create Workspace",
            style="Primary.TButton",
            command=self._on_create_workspace,
        )
        self._create_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self._open_btn = ttk.Button(
            action_row,
            text="Open Workspace",
            style="Secondary.TButton",
            command=self._on_open_workspace,
        )
        self._open_btn.grid(row=0, column=1, sticky="w", padx=(0, 8))

        self._refresh_btn = ttk.Button(
            action_row,
            text="Refresh",
            style="Secondary.TButton",
            command=self._on_refresh,
        )
        self._refresh_btn.grid(row=0, column=2, sticky="w")

        ttk.Label(workspace_panel, text="Selected Workspace", style="FieldLabel.TLabel").grid(
            row=3, column=0, sticky="nw", padx=(2, 8), pady=(8, 4)
        )
        self._selected_workspace_var = tk.StringVar(value="-")
        self._selected_workspace_label = ttk.Label(
            workspace_panel,
            textvariable=self._selected_workspace_var,
            style="Panel.TLabel",
            wraplength=760,
        )
        self._selected_workspace_label.grid(row=3, column=1, columnspan=2, sticky="w", pady=(8, 4))

    def _build_recordings_section(self, parent: ttk.Frame) -> None:
        recordings_panel = ttk.LabelFrame(parent, text="TEST CASES / RECORDINGS", style="Section.TLabelframe", padding=12)
        recordings_panel.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        recordings_panel.columnconfigure(0, weight=1)
        recordings_panel.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(recordings_panel, style="Panel.TFrame")
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self._recording_tree = ttk.Treeview(
            list_frame,
            columns=("test_name", "json_file"),
            show="headings",
            style="Recording.Treeview",
            selectmode="browse",
        )
        self._recording_tree.heading("test_name", text="Test Name")
        self._recording_tree.heading("json_file", text="JSON File")
        self._recording_tree.column("test_name", width=260, minwidth=180, anchor="w", stretch=True)
        self._recording_tree.column("json_file", width=520, minwidth=260, anchor="w", stretch=True)
        self._recording_tree.grid(row=0, column=0, sticky="nsew")
        self._recording_tree.bind("<<TreeviewSelect>>", self._on_recording_selection_change)
        self._recording_tree.bind("<Double-1>", self._on_open_selected_json_event)
        self._recording_tree.bind("<ButtonRelease-1>", self._on_recording_tree_single_click)

        recording_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._recording_tree.yview)
        recording_scroll.grid(row=0, column=1, sticky="ns")
        self._recording_tree.configure(yscrollcommand=recording_scroll.set)

        self._empty_state_var = tk.StringVar(value="")
        ttk.Label(
            recordings_panel,
            textvariable=self._empty_state_var,
            style="Panel.TLabel",
            foreground="#4e5d6c",
        ).grid(row=1, column=0, sticky="w", pady=(8, 2))

        self._selection_hint_var = tk.StringVar(value="")
        ttk.Label(
            recordings_panel,
            textvariable=self._selection_hint_var,
            style="Panel.TLabel",
            foreground="#5b6670",
        ).grid(row=2, column=0, sticky="w", pady=(0, 8))

        controls = ttk.Frame(recordings_panel, style="Panel.TFrame")
        controls.grid(row=3, column=0, sticky="e")

        self._run_btn = ttk.Button(
            controls,
            text="Run Selected Test",
            style="Primary.TButton",
            command=self._on_run_selected,
        )
        self._run_btn.grid(row=0, column=0, sticky="e", padx=(0, 8))

        self._open_json_btn = ttk.Button(
            controls,
            text="Open JSON",
            style="Secondary.TButton",
            command=self._on_open_selected_json,
        )
        self._open_json_btn.grid(row=0, column=1, sticky="e")

    def _build_reporting_section(self, parent: ttk.Frame) -> None:
        reporting_panel = ttk.LabelFrame(parent, text="REPORTING", style="Section.TLabelframe", padding=12)
        reporting_panel.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        self._report_btn = ttk.Button(
            reporting_panel,
            text="Open Report",
            style="Secondary.TButton",
            command=self._on_open_report,
        )
        self._report_btn.grid(row=0, column=0, sticky="w")

    def _build_status_section(self, parent: ttk.Frame) -> None:
        status_panel = ttk.LabelFrame(parent, text="STATUS", style="Section.TLabelframe", padding=12)
        status_panel.grid(row=3, column=0, sticky="ew")
        status_panel.columnconfigure(0, weight=1)

        self._status_var = tk.StringVar(value="")
        self._status_label = tk.Label(
            status_panel,
            textvariable=self._status_var,
            bg=_COLOR_PANEL,
            fg="#3d4e5f",
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=980,
        )
        self._status_label.grid(row=0, column=0, sticky="ew")

    # ------------------------------------------------------------------
    # App-shell hooks
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        self._on_window_resize()

    def focus_recordings(self) -> None:
        self._recording_tree.focus_set()
        self._set_status("Viewing test cases and recordings.", level="info")

    def focus_reports(self) -> None:
        self._set_status("Use Open Report to view the latest execution report.", level="info")

    # ------------------------------------------------------------------
    # UI Actions
    # ------------------------------------------------------------------

    def _on_input_changed(self, *_args) -> None:
        self._update_button_states()

    def _on_window_resize(self, _event=None) -> None:
        width = max(self.winfo_width(), 920)
        wrap = max(340, width - 260)
        self._selected_workspace_label.configure(wraplength=wrap)
        self._status_label.configure(wraplength=wrap)

    def _on_recording_selection_change(self, _event=None) -> None:
        self._update_button_states()
        if self._selected_recording_item() is not None:
            self._selection_hint_var.set("Ready to run the selected recording.")
        elif self._workspace_service is not None and self._recordings:
            self._selection_hint_var.set("Select a recording to run the test.")

    def _on_recording_tree_single_click(self, event) -> None:
        row_id = self._recording_tree.identify_row(event.y)
        column = self._recording_tree.identify_column(event.x)
        if not row_id or column != "#2":
            return

        self._recording_tree.selection_set(row_id)
        self._on_recording_selection_change()
        self._on_open_selected_json()

    def _on_open_selected_json_event(self, _event=None) -> None:
        self._on_open_selected_json()

    def _on_browse(self) -> None:
        """Initiate asynchronous folder selection without blocking Tk."""
        initial_dir = self._browse_initial_directory()
        root_tk = self.winfo_toplevel()

        # Launch folder picker asynchronously.
        FolderPickerAsync(
            root_tk=root_tk,
            initial_dir=initial_dir,
            title="Select workspace directory",
            on_complete=self._on_browse_complete,
        )

    def _on_browse_complete(self, chosen: str) -> None:
        """Callback invoked when folder picker completes (result from background thread)."""
        if not chosen:
            self._set_status("Workspace selection cancelled.", level="info")
            return

        chosen_path = Path(chosen).expanduser()
        if not chosen_path.is_dir():
            self._set_status(
                "Selected workspace path is invalid. Please choose an existing directory.",
                level="warning",
            )
            return

        self._workspace_path_var.set(str(chosen_path.resolve()))
        self._set_status("Workspace path updated.", level="success")

    def _browse_initial_directory(self) -> Path:
        """Resolve a safe existing directory for the OS file dialog."""
        raw_value = self._workspace_path_var.get().strip()
        candidates: list[Path] = []

        if raw_value:
            candidates.append(Path(raw_value).expanduser())
        candidates.append(self._default_workspace_root)

        for candidate in candidates:
            existing = self._nearest_existing_directory(candidate)
            if existing is not None:
                return existing

        return Path.home().resolve()

    @staticmethod
    def _nearest_existing_directory(path: Path) -> Path | None:
        current = path
        while True:
            try:
                if current.exists() and current.is_dir():
                    return current.resolve()
            except OSError:
                return None
            if current.parent == current:
                return None
            current = current.parent

    @staticmethod
    def _create_help_icon(parent: tk.Misc) -> tk.Canvas:
        icon = tk.Canvas(
            parent,
            width=16,
            height=16,
            bg=_COLOR_PANEL,
            highlightthickness=0,
            cursor="hand2",
        )
        icon.create_oval(1, 1, 15, 15, fill=_COLOR_HELP_BG, outline=_COLOR_HELP_BORDER, width=1)
        icon.create_text(8, 8, text="?", fill=_COLOR_HELP_TEXT, font=("Segoe UI", 8, "bold"))
        return icon

    def _on_create_workspace(self) -> None:
        name = self._workspace_name_var.get().strip()
        path_text = self._workspace_path_var.get().strip()

        if not name:
            self._set_status("Workspace name is required.", level="warning")
            return

        try:
            validate_name(name)
        except ValueError:
            self._set_status(
                "Workspace name is invalid. Use letters, numbers, underscores, or hyphens.",
                level="warning",
            )
            return

        if not path_text:
            self._set_status("Workspace path is required.", level="warning")
            return

        base_dir = Path(path_text).expanduser()
        if base_dir.exists() and not base_dir.is_dir():
            self._set_status(
                "Workspace path is invalid. Please choose a directory.",
                level="error",
            )
            return

        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            _log.exception("Could not create workspace base directory: %s", base_dir)
            self._set_status(
                "Workspace path could not be prepared. Please verify directory permissions.",
                level="error",
            )
            return

        workspace_root = (base_dir / name).resolve()

        try:
            self._workspace_service = WorkspaceService.create(root=workspace_root, name=name)
        except ValueError:
            self._set_status(
                "Workspace name is invalid. Please provide a valid name.",
                level="warning",
            )
            return
        except WorkspaceError:
            _log.exception("Create workspace failed for root: %s", workspace_root)
            self._set_status(
                "Workspace could not be created. Please verify the selected directory.",
                level="error",
            )
            return
        except OSError:
            _log.exception("Filesystem error while creating workspace: %s", workspace_root)
            self._set_status(
                "Workspace could not be created due to a filesystem error.",
                level="error",
            )
            return

        self._workspace_path_var.set(str(self._workspace_service.info.root))
        self._set_selected_workspace_text(self._workspace_service.info.root)
        save_recent(self._workspace_service.info.root)
        self._discover_recordings()
        self._set_status("Workspace created and selected successfully.", level="success")

    def _on_open_workspace(self) -> None:
        path_text = self._workspace_path_var.get().strip()
        if not path_text:
            self._set_status("Workspace path is required.", level="warning")
            return

        raw_path = Path(path_text).expanduser()
        candidates: list[Path] = [raw_path]

        name = self._workspace_name_var.get().strip()
        if name:
            candidates.append(raw_path / name)

        loaded = self._try_load_workspace(candidates)
        if loaded is None:
            if not raw_path.exists():
                self._set_status(
                    "Workspace could not be opened. Please verify that the selected directory exists.",
                    level="error",
                )
            elif not raw_path.is_dir():
                self._set_status(
                    "Workspace path is invalid. Please choose a directory.",
                    level="error",
                )
            else:
                self._set_status(
                    "Workspace could not be opened. The selected directory is not a valid workspace.",
                    level="error",
                )
            return

        self._workspace_service = loaded
        self._workspace_path_var.set(str(self._workspace_service.info.root))
        self._set_selected_workspace_text(self._workspace_service.info.root)
        save_recent(self._workspace_service.info.root)
        self._discover_recordings()
        self._set_status("Workspace opened successfully.", level="success")

    def _on_refresh(self) -> None:
        if self._workspace_service is None:
            self._set_status(
                "No workspace selected. Create or open a workspace first.",
                level="warning",
            )
            return

        try:
            root = self._workspace_service.info.root
            self._workspace_service = WorkspaceService.load(root)
            self._workspace_service.ensure_dirs()
        except (WorkspaceNotFoundError, WorkspaceError, OSError):
            _log.exception("Workspace refresh failed.")
            self._set_status(
                "Workspace refresh failed. Please verify that the workspace still exists.",
                level="error",
            )
            return

        self._set_selected_workspace_text(self._workspace_service.info.root)
        self._discover_recordings()
        self._set_status("Workspace refreshed.", level="success")

    def _on_run_selected(self) -> None:
        item = self._selected_recording_item()
        if item is None:
            self._set_status("Select a recording to run the test.", level="warning")
            return

        # Validate before handing off to the background thread.
        store = RecordingStore(base_dir=item.json_path.parent)
        try:
            actions = store.load(item.json_path.stem)
        except FileNotFoundError:
            _log.exception("Selected recording file not found: %s", item.json_path)
            self._set_status(
                "Selected recording could not be loaded. Please refresh and try again.",
                level="error",
            )
            return
        if not actions:
            self._set_status("Selected recording is empty or invalid.", level="warning")
            return

        self._set_status(f"Running '{item.test_name}' — DA app will restore when done…", level="info")
        self._run_btn.configure(state="disabled")
        self._run_recording_async(item, actions)

    def _on_open_selected_json(self) -> None:
        item = self._selected_recording_item()
        if item is None:
            self._set_status("Select a recording to open its JSON file.", level="warning")
            return

        path = item.json_path
        if not path.exists() or not path.is_file():
            self._set_status("Selected JSON file is missing. Refresh the workspace list.", level="error")
            self._update_button_states()
            return

        try:
            self._open_path(path)
            self._set_status(f"Opened JSON file: {path}", level="success")
        except Exception:  # noqa: BLE001
            _log.exception("Failed to open selected JSON file: %s", path)
            self._set_status("JSON file could not be opened with the default editor.", level="error")

    def _on_open_report(self) -> None:
        report_path = self._resolve_report_path()
        if report_path is None:
            self._set_status("No report found yet. Run a test first.", level="warning")
            return

        try:
            self._open_path(report_path)
            self._set_status(f"Opened report: {report_path}", level="success")
        except Exception:
            _log.exception("Failed to open report: %s", report_path)
            self._set_status("Report could not be opened.", level="error")

    def _open_path(self, target: Path) -> None:
        """Open a file using the tracked editor manager."""
        editor_manager = get_editor_manager()
        editor_manager.open_file(target)

    # ------------------------------------------------------------------
    # Internal behavior
    # ------------------------------------------------------------------

    def _try_load_workspace(self, candidates: list[Path]) -> WorkspaceService | None:
        visited: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.expanduser().resolve()
            if resolved in visited:
                continue
            visited.add(resolved)

            if not resolved.exists() or not resolved.is_dir():
                continue

            try:
                return WorkspaceService.load(root=resolved)
            except WorkspaceNotFoundError:
                continue
            except (WorkspaceError, OSError):
                _log.exception("Workspace open failed at candidate path: %s", resolved)
                return None
        return None

    def _set_selected_workspace_text(self, path: Path | None) -> None:
        if path is None:
            self._selected_workspace_var.set("-")
            return
        self._selected_workspace_var.set(str(path))

    def _selected_recording_item(self) -> RecordingItem | None:
        selection = self._recording_tree.selection()
        if not selection:
            return None
        return self._recording_row_map.get(selection[0])

    def _discover_recordings(self) -> None:
        if self._workspace_service is None:
            self._recordings = []
            self._refresh_recordings_view()
            return

        ws = self._workspace_service
        discovered: list[RecordingItem] = []

        for file_path in sorted(ws.recordings_dir_for().glob("*.json")):
            discovered.append(
                RecordingItem(
                    test_name=f"workspace/{file_path.stem}",
                    json_path=file_path.resolve(),
                    source="workspace",
                )
            )

        for test_case in ws.list_test_cases():
            case_dir = ws.recordings_dir_for(test_case)
            for file_path in sorted(case_dir.glob("*.json")):
                discovered.append(
                    RecordingItem(
                        test_name=f"{test_case}/{file_path.stem}",
                        json_path=file_path.resolve(),
                        source=test_case,
                    )
                )

        self._recordings = discovered
        self._refresh_recordings_view()

    def _refresh_recordings_view(self) -> None:
        for row_id in self._recording_tree.get_children():
            self._recording_tree.delete(row_id)
        self._recording_row_map.clear()

        for index, item in enumerate(self._recordings):
            row_id = f"rec_{index}"
            json_display = self._display_json_path(item.json_path)
            self._recording_tree.insert(
                "",
                "end",
                iid=row_id,
                values=(item.test_name, json_display),
            )
            self._recording_row_map[row_id] = item

        if self._workspace_service is None:
            self._empty_state_var.set(
                "No workspace selected. Create or open a workspace to view available recordings."
            )
            self._selection_hint_var.set("Select a workspace to continue.")
        elif not self._recordings:
            self._empty_state_var.set("No recordings found in this workspace.")
            self._selection_hint_var.set("Recordings saved in this workspace will appear here.")
        else:
            self._empty_state_var.set(f"{len(self._recordings)} recording(s) available.")
            self._selection_hint_var.set("Select a recording to run the test.")

        self._update_button_states()

    def _display_json_path(self, path: Path) -> str:
        if self._workspace_service is None:
            return str(path)
        root = self._workspace_service.info.root
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)

    def _run_recording_async(self, item: RecordingItem, actions) -> None:
        """Minimize the DA app, run playback on a daemon thread, then restore.

        Running on a background thread is mandatory: if playback blocks the
        Tkinter main thread the DA app window stays in the foreground and
        _ensure_window() inside the adapter would attach to it instead of the
        target application, causing every action to fire against the wrong window.
        """
        import threading

        root = self.winfo_toplevel()
        # Minimize so the DA app does not occupy the foreground during playback.
        root.iconify()

        exc_holder: list[Exception | None] = [None]

        def _worker() -> None:
            driver = DesktopDriver()
            report_path: Path | None = None
            try:
                executor = PlaybackExecutor(
                    driver=driver,
                    recording_name=item.json_path.stem,
                )
                try:
                    executor.run(actions)
                except Exception as exc:  # noqa: BLE001
                    exc_holder[0] = exc
                    _log.exception("Playback failed for recording '%s'", item.test_name)
                finally:
                    # Generate HTML report regardless of pass/fail.
                    if getattr(executor, "result", None) is not None:
                        try:
                            ws_name = (
                                self._workspace_service.info.name
                                if self._workspace_service and hasattr(self._workspace_service.info, "name")
                                else None
                            )
                            report_path = generate_recording_report(
                                executor.result,
                                workspace_name=ws_name,
                            )
                            _log.info("Recording report: %s", report_path)
                        except Exception as rpt_err:  # noqa: BLE001
                            _log.warning("Could not generate recording report: %s", rpt_err)
            finally:
                driver.quit()
                # Schedule UI update back on the main thread.
                self.after(0, lambda: _on_done(exc_holder[0], report_path))

        def _on_done(exc: Exception | None, report_path: Path | None = None) -> None:
            root.deiconify()
            root.lift()
            root.focus_force()
            if report_path is not None:
                self._last_report_path = report_path
            if exc is None:
                rpt_hint = f"  Report: {report_path.name}" if report_path else ""
                self._set_status(
                    f"\u2713 Execution completed: {item.test_name}{rpt_hint}", level="success"
                )
            else:
                short = str(exc).split("\n")[0][:200]
                rpt_hint = f"  Report: {report_path.name}" if report_path else ""
                self._set_status(
                    f"Playback failed: {short}{rpt_hint}", level="error"
                )
            self._update_button_states()

        t = threading.Thread(target=_worker, name=f"playback-{item.test_name}", daemon=True)
        t.start()

    def _resolve_report_path(self) -> Path | None:
        # Prefer the most recently generated recording report.
        if self._last_report_path is not None and self._last_report_path.exists():
            return self._last_report_path

        # Fall back to the most recent recording_*.html file in reports/html/.
        html_dir = Path("reports/html")
        recording_reports = sorted(html_dir.glob("recording_*.html"), reverse=True)
        if recording_reports:
            return recording_reports[0].resolve()

        # Legacy: pytest suite report.
        candidates: list[Path] = []
        if self._workspace_service is not None:
            candidates.append(self._workspace_service.info.root / "reports" / "html" / "report.html")
        candidates.append(Path("reports/html/report.html").resolve())
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return None

    def _update_button_states(self) -> None:
        has_name = bool(self._workspace_name_var.get().strip())
        has_path = bool(self._workspace_path_var.get().strip())
        has_workspace = self._workspace_service is not None
        selected = self._selected_recording_item()
        has_selection = selected is not None
        has_json_file = bool(selected and selected.json_path.exists())
        has_report = self._resolve_report_path() is not None

        self._create_btn.configure(state="normal" if has_name and has_path else "disabled")
        self._open_btn.configure(state="normal" if has_path else "disabled")
        self._refresh_btn.configure(state="normal" if has_workspace else "disabled")
        self._run_btn.configure(state="normal" if has_workspace and has_selection else "disabled")
        self._open_json_btn.configure(state="normal" if has_workspace and has_json_file else "disabled")
        self._report_btn.configure(state="normal" if has_workspace and has_report else "disabled")

    def _set_status(self, message: str, *, level: str = "info") -> None:
        color_by_level = {
            "info": _COLOR_TEXT,
            "success": _COLOR_SUCCESS,
            "warning": _COLOR_WARNING,
            "error": _COLOR_ERROR,
        }
        self._status_var.set(message)
        self._status_label.configure(fg=color_by_level.get(level, _COLOR_TEXT))


def main() -> None:  # pragma: no cover
    from ui.app_shell import AppShell

    logging.basicConfig(level=logging.INFO)
    app = AppShell(default_screen="workspace")
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
