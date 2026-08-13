from __future__ import annotations

from framework.core.models import Locator
from framework.driver.pywinauto_adapter import PyWinAutoAdapter


class DesktopDriver:
    """Framework-facing driver wrapper used by playback and assertions."""

    def __init__(self, backend: str = "uia") -> None:
        self.adapter = PyWinAutoAdapter(backend=backend)

    def start(self, executable_path: str) -> None:
        self.adapter.start(executable_path)

    def connect(self, **kwargs: str) -> None:
        self.adapter.connect(**kwargs)

    def focus_window(self, locator: Locator) -> None:
        self.adapter.focus_window(locator)

    def click(self, locator: Locator) -> None:
        self.adapter.click(locator)

    def type_text(self, locator: Locator, text: str) -> None:
        self.adapter.type_text(locator, text)

    def exists(self, locator: Locator, timeout_seconds: float = 5.0) -> bool:
        return self.adapter.exists(locator, timeout_seconds=timeout_seconds)

    def get_text(self, locator: Locator) -> str:
        return self.adapter.get_text(locator)
