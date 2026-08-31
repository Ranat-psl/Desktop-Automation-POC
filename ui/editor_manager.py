"""Process tracking for launched editor/viewer applications."""
from __future__ import annotations

import logging
import platform
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

_HTML_SUFFIXES = {".html", ".htm"}


class EditorProcessManager:
    """Track and manage editor processes launched by the application."""

    def __init__(self) -> None:
        self._processes: list[subprocess.Popen] = []

    def open_file(self, path: Path) -> None:
        """Open a file using the appropriate default application.

        HTML files are opened in the system default browser via
        ``webbrowser.open()``.  All other files are opened with the
        platform's default editor (Notepad on Windows).
        """
        path = Path(path).resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        if path.suffix.lower() in _HTML_SUFFIXES:
            self._open_in_browser(path)
            return

        self._open_in_editor(path)

    def _open_in_browser(self, path: Path) -> None:
        """Open an HTML file in the system default browser."""
        url = path.as_uri()
        _log.info("Opening HTML file in default browser: %s", path)
        try:
            opened = webbrowser.open(url)
            if not opened:
                _log.warning("webbrowser.open() returned False for: %s", url)
        except Exception as exc:
            _log.exception("Failed to open HTML file in browser: %s", path)
            raise

    def _open_in_editor(self, path: Path) -> None:
        """Open a non-HTML file using the platform default editor."""
        system_name = platform.system().lower()
        try:
            if system_name == "windows":
                proc = subprocess.Popen(
                    ["notepad.exe", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
                self._processes.append(proc)
            elif system_name == "darwin":
                proc = subprocess.Popen(
                    ["open", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._processes.append(proc)
            else:
                proc = subprocess.Popen(
                    ["xdg-open", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._processes.append(proc)
        except Exception as exc:
            _log.exception("Failed to open file: %s", path)
            raise

        # Prune terminated processes to avoid memory leak.
        self._prune_processes()

    def cleanup(self) -> None:
        """Terminate all tracked processes gracefully."""
        for proc in self._processes:
            try:
                if proc.poll() is None:  # Process is still running.
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception as exc:
                _log.warning("Failed to terminate editor process: %s", exc)

        self._processes.clear()

    def _prune_processes(self) -> None:
        """Remove terminated processes from tracking list."""
        self._processes = [p for p in self._processes if p.poll() is None]


# Global manager instance.
_manager: Optional[EditorProcessManager] = None


def get_editor_manager() -> EditorProcessManager:
    """Get or create the global editor process manager."""
    global _manager
    if _manager is None:
        _manager = EditorProcessManager()
    return _manager
