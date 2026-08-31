"""Windows-native folder picker without blocking the Tk event loop."""
from __future__ import annotations

import logging
import platform
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

_log = logging.getLogger(__name__)


class FolderPickerAsync:
    """Asynchronously launch a folder picker without blocking Tk."""

    def __init__(
        self,
        root_tk,
        initial_dir: Path | str | None = None,
        title: str = "Select Folder",
        on_complete: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize and launch the folder picker in a background thread.

        Args:
            root_tk: Tk root widget (used for thread-safe callbacks via after()).
            initial_dir: Starting directory.
            title: Dialog title.
            on_complete: Callback function called with selected path (or empty string if cancelled).
                         This callback is invoked from the Tk thread.
        """
        self._root = root_tk
        self._on_complete = on_complete or (lambda _: None)
        self._initial_dir = initial_dir
        self._title = title
        self._thread: Optional[threading.Thread] = None
        self._result: str = ""
        self._process: Optional[subprocess.Popen] = None

        # Start the folder picker in a background thread immediately.
        self._start_picker()

    def _start_picker(self) -> None:
        """Launch the folder picker in a background thread."""
        self._thread = threading.Thread(target=self._run_picker, daemon=True)
        self._thread.start()

    def _run_picker(self) -> None:
        """Run the folder picker in a background thread."""
        system_name = platform.system().lower()

        if system_name == "windows":
            self._result = self._pick_folder_windows()
        else:
            self._result = self._pick_folder_fallback()

        # Schedule the completion callback on the Tk thread.
        try:
            self._root.after(0, self._on_picker_complete)
        except Exception as exc:
            _log.exception("Failed to schedule picker completion callback: %s", exc)

    def _pick_folder_windows(self) -> str:
        """Launch Windows native folder picker via PowerShell."""
        try:
            ps_script = self._build_powershell_script()
            self._process = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            )

            # Wait for the process with timeout. If timeout occurs, kill it.
            try:
                stdout, stderr = self._process.communicate(timeout=60)
                if self._process.returncode == 0 and stdout.strip():
                    return stdout.strip()
            except subprocess.TimeoutExpired:
                _log.warning("PowerShell folder picker timed out after 60 seconds")
                try:
                    self._process.kill()
                    self._process.wait(timeout=5)
                except Exception as exc:
                    _log.warning("Failed to kill PowerShell process: %s", exc)

            return ""

        except Exception as exc:
            _log.exception("Windows folder picker failed: %s", exc)
            return ""

    def _build_powershell_script(self) -> str:
        """Build PowerShell script for folder selection."""
        initial_path = str(Path(self._initial_dir).resolve()) if self._initial_dir else "C:\\"
        # Escape backslashes for PowerShell.
        initial_path = initial_path.replace("\\", "\\\\")
        title = self._title.replace('"', '\\"')

        script = f"""
[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "{title}"
$dialog.SelectedPath = "{initial_path}"
$result = $dialog.ShowDialog()
if ($result -eq "OK") {{
    Write-Output $dialog.SelectedPath
}}
"""
        return script

    def _pick_folder_fallback(self) -> str:
        """Fallback to tkinter.filedialog for non-Windows platforms."""
        try:
            from tkinter import filedialog, Tk

            root = Tk()
            root.withdraw()
            root.attributes("-alpha", 0.0)

            initial_dir_str = ""
            if self._initial_dir:
                try:
                    p = Path(self._initial_dir).resolve()
                    if p.exists() and p.is_dir():
                        initial_dir_str = str(p)
                except (OSError, ValueError):
                    pass

            chosen = filedialog.askdirectory(
                title=self._title,
                initialdir=initial_dir_str or None,
                mustexist=True,
            )

            root.destroy()
            return chosen if chosen else ""

        except Exception as exc:
            _log.exception("Fallback folder picker failed: %s", exc)
            return ""

    def _on_picker_complete(self) -> None:
        """Callback invoked on the Tk thread after picker completes."""
        try:
            self._on_complete(self._result)
        except Exception as exc:
            _log.exception("Picker completion callback failed: %s", exc)

    def cleanup(self) -> None:
        """Clean up any running processes."""
        if self._process is not None:
            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
            except Exception as exc:
                _log.warning("Failed to cleanup PowerShell process: %s", exc)
