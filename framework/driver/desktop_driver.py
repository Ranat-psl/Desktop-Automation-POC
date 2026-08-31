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

    def maximize_window(self) -> None:
        """Maximize the currently focused window. Fails gracefully."""
        self.adapter.maximize_window()

    def click(self, locator: Locator, coords: tuple[int, int] | None = None) -> None:
        self.adapter.click(locator, coords=coords)

    def type_text(self, locator: Locator, text: str) -> None:
        self.adapter.type_text(locator, text)

    def type_text_global(self, text: str) -> None:
        """Type text globally without a locator (e.g. into Win+R Run dialog)."""
        self.adapter.type_text_global(text)

    def press_key(self, key_name: str) -> None:
        """Press and release a single named key (Enter, F5, arrow keys, etc.)."""
        self.adapter.press_key(key_name)

    def hotkey(self, hotkey_str: str) -> None:
        """Execute a hotkey combination e.g. 'ctrl+c', 'cmd+r', 'ctrl+shift+s'."""
        self.adapter.hotkey(hotkey_str)

    def exists(self, locator: Locator, timeout_seconds: float = 5.0) -> bool:
        return self.adapter.exists(locator, timeout_seconds=timeout_seconds)

    def get_text(self, locator: Locator) -> str:
        return self.adapter.get_text(locator)

    def quit(self) -> None:
        """Terminate the application process started by this driver session."""
        self.adapter.quit()
