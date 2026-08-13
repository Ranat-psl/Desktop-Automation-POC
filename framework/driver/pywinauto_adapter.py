from __future__ import annotations

import time

from pywinauto import Application, Desktop

from framework.core.models import Locator
from framework.driver.locator_resolver import to_kwargs


class PyWinAutoAdapter:
    """Thin pywinauto wrapper to isolate external library calls."""

    def __init__(self, backend: str = "uia") -> None:
        self.backend = backend
        self._app: Application | None = None
        self._window = None

    def start(self, executable_path: str) -> None:
        self._app = Application(backend=self.backend).start(executable_path)

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
            deadline = time.time() + 8.0
            while time.time() < deadline:
                windows = Desktop(backend=self.backend).windows(
                    process=process_id,
                    top_level_only=True,
                    visible_only=True,
                )
                if windows:
                    break
                time.sleep(0.2)

        # Fallback: title-regex search on Desktop — handles Win11 Store apps that
        # spawn in a different host process than the launcher PID.
        if not windows:
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
                        break
                    time.sleep(0.2)

        if windows:
            # Prefer a top-level window that has a title if available.
            titled_windows = [w for w in windows if w.window_text().strip()]
            self._window = titled_windows[0] if titled_windows else windows[0]
        else:
            try:
                self._window = self._app.top_window()
            except Exception:
                self._window = self._app.window(**to_kwargs(locator))

        self._window.set_focus()

    def click(self, locator: Locator) -> None:
        control = self._resolve_control(locator)
        control.click_input()

    def type_text(self, locator: Locator, text: str) -> None:
        control = self._resolve_control(locator)
        control.type_keys(text, with_spaces=True, set_foreground=True)

    def exists(self, locator: Locator, timeout_seconds: float = 5.0) -> bool:
        try:
            control = self._resolve_control(locator)
        except Exception:
            return False
        if hasattr(control, "exists"):
            # WindowSpecification supports exists(timeout=...).
            return control.exists(timeout=timeout_seconds)
        # Concrete UIAWrapper — resolution already confirmed it exists.
        return control is not None

    def get_text(self, locator: Locator) -> str:
        control = self._resolve_control(locator)
        try:
            return str(control.window_text())
        except Exception:
            return ""

    def _resolve_control(self, locator: Locator):
        if self._window is None:
            raise RuntimeError("Active window is not selected.")
        kwargs = to_kwargs(locator)
        if hasattr(self._window, "child_window"):
            # WindowSpecification (from app.window()) — lazy resolution.
            return self._window.child_window(**kwargs)
        # Concrete UIAWrapper (from Desktop.windows()) — search descendants directly.
        matches = self._window.descendants(**kwargs)
        if not matches:
            from framework.core.exceptions import LocatorResolutionError
            raise LocatorResolutionError(f"Control not found: {locator.by}={locator.value}")
        return matches[0]
