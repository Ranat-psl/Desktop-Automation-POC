from __future__ import annotations

import logging
import time

from pywinauto import Application, Desktop

from framework.core.models import Locator
from framework.driver.locator_resolver import to_kwargs

_log = logging.getLogger(__name__)


class PyWinAutoAdapter:
    """Thin pywinauto wrapper to isolate external library calls."""

    def __init__(self, backend: str = "uia") -> None:
        self.backend = backend
        self._app: Application | None = None
        self._window = None
        self._window_pid: int | None = None  # actual window process, may differ from _app.process on Win11

    def start(self, executable_path: str) -> None:
        _log.debug("Starting application: %s (backend=%s)", executable_path, self.backend)
        self._app = Application(backend=self.backend).start(executable_path)
        _log.debug("Application started")

    def connect(self, **kwargs: str) -> None:
        self._app = Application(backend=self.backend).connect(**kwargs)

    def focus_window(self, locator: Locator) -> None:
        if self._app is None:
            raise RuntimeError("Application is not started or connected.")

        # Prefer process-bound top-level window discovery for Win11 apps.
        raw_process = getattr(self._app, "process", None)
        if callable(raw_process):
            raw_process = raw_process()

        process_id: int | None
        try:
            process_id = int(raw_process)
        except (TypeError, ValueError):
            process_id = None

        windows = []
        if process_id is not None:
            _log.debug("Searching top-level windows by process id=%s", process_id)
            deadline = time.time() + 2.0
            while time.time() < deadline:
                windows = Desktop(backend=self.backend).windows(
                    process=process_id,
                    top_level_only=True,
                    visible_only=True,
                )
                if windows:
                    _log.debug("Found %d window(s) via process id", len(windows))
                    break
                time.sleep(0.2)

        # Fallback: title-regex search on Desktop — handles Win11 Store apps that
        # spawn in a different host process than the launcher PID.
        if not windows:
            _log.debug("No windows found by process id; trying title-regex fallback")
            search_hint = locator.value if locator.by in ("title", "class_name") else None
            if search_hint:
                deadline2 = time.time() + 5.0
                while time.time() < deadline2:
                    windows = Desktop(backend=self.backend).windows(
                        title_re=f".*{search_hint}.*",
                        top_level_only=True,
                        visible_only=True,
                    )
                    if windows:
                        _log.debug("Found %d window(s) via title-regex", len(windows))
                        break
                    time.sleep(0.2)

        if windows:
            # Prefer a top-level window that has a title if available.
            titled_windows = [w for w in windows if w.window_text().strip()]
            self._window = titled_windows[0] if titled_windows else windows[0]
            _log.debug("Focused window: '%s'", self._window.window_text())
        else:
            _log.debug("Desktop search exhausted; falling back to app-bound lookup")
            try:
                self._window = self._app.top_window()
            except Exception:
                self._window = self._app.window(**to_kwargs(locator))

        # Record the actual window process ID so quit() can kill it even when
        # Win11 Store apps spawn in a host process different from _app.process.
        try:
            if hasattr(self._window, "process_id") and callable(self._window.process_id):
                self._window_pid = int(self._window.process_id())
                _log.debug("focus_window: window process_id=%d", self._window_pid)
        except Exception:
            pass

        self._window.set_focus()
        _log.debug("set_focus() called")

    def click(self, locator: Locator) -> None:
        control = self._resolve_control(locator)
        control.click_input()

    def type_text(self, locator: Locator, text: str) -> None:
        _log.debug("type_text: locator=%s|%s", locator.by, locator.value)
        control = self._resolve_control(locator)
        control.type_keys(text, with_spaces=True, set_foreground=True)
        _log.debug("type_text: completed")

    def exists(self, locator: Locator, timeout_seconds: float = 5.0) -> bool:
        _log.debug("exists: locator=%s|%s", locator.by, locator.value)
        try:
            control = self._resolve_control(locator)
        except Exception:
            _log.debug("exists: control not found -> False")
            return False
        if hasattr(control, "exists"):
            # WindowSpecification supports exists(timeout=...).
            result = control.exists(timeout=timeout_seconds)
            _log.debug("exists: WindowSpecification result=%s", result)
            return result
        # Concrete UIAWrapper — resolution already confirmed it exists.
        _log.debug("exists: UIAWrapper resolved -> True")
        return control is not None

    def quit(self) -> None:
        """Terminate the specific application process started by this adapter.

        Kills by PID so only the process launched in this session is affected.
        Safe to call even if the application was never started.
        """
        if self._app is None:
            return
        raw_process = getattr(self._app, "process", None)
        if callable(raw_process):
            raw_process = raw_process()
        try:
            pid = int(raw_process)
        except (TypeError, ValueError):
            _log.debug("quit: cannot determine PID — skipping kill")
            return
        _log.debug("quit: killing PID %d", pid)
        import subprocess
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            check=False,
            capture_output=True,
        )
        # If the focused window belonged to a different process (Win11 Store app
        # hosting scenario), kill that process too so no orphan windows remain.
        if self._window_pid is not None and self._window_pid != pid:
            _log.debug("quit: also killing window PID %d", self._window_pid)
            subprocess.run(
                ["taskkill", "/PID", str(self._window_pid), "/F", "/T"],
                check=False,
                capture_output=True,
            )
        self._app = None
        self._window = None
        self._window_pid = None

    def get_text(self, locator: Locator) -> str:
        _log.debug("get_text: locator=%s|%s", locator.by, locator.value)
        control = self._resolve_control(locator)
        try:
            text = str(control.window_text())
            _log.debug("get_text: result='%s'", text)
            return text
        except Exception:
            _log.debug("get_text: window_text() raised, returning empty string")
            return ""

    def _resolve_control(self, locator: Locator):
        if self._window is None:
            raise RuntimeError("Active window is not selected.")
        kwargs = to_kwargs(locator)
        if hasattr(self._window, "child_window"):
            # WindowSpecification (from app.window()) — lazy resolution.
            _log.debug("_resolve_control: WindowSpecification path for %s|%s", locator.by, locator.value)
            return self._window.child_window(**kwargs)
        # Concrete UIAWrapper (from Desktop.windows()) — search descendants directly.
        _log.debug("_resolve_control: UIAWrapper.descendants() path for %s|%s", locator.by, locator.value)
        matches = self._window.descendants(**kwargs)
        if not matches:
            from framework.core.exceptions import LocatorResolutionError
            raise LocatorResolutionError(f"Control not found: {locator.by}={locator.value}")
        return matches[0]
