from __future__ import annotations

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
        process_id = getattr(self._app, "process", None)
        windows = []
        if process_id:
            windows = Desktop(backend=self.backend).windows(
                process=process_id,
                top_level_only=True,
                visible_only=True,
            )

        if windows:
            self._window = windows[0]
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
        control = self._resolve_control(locator)
        return control.exists(timeout=timeout_seconds)

    def get_text(self, locator: Locator) -> str:
        control = self._resolve_control(locator)
        try:
            return str(control.window_text())
        except Exception:
            return ""

    def _resolve_control(self, locator: Locator):
        if self._window is None:
            raise RuntimeError("Active window is not selected.")
        return self._window.child_window(**to_kwargs(locator))
