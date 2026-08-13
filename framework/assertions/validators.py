from __future__ import annotations

from framework.core.exceptions import PlaybackExecutionError
from framework.core.models import Locator
from framework.driver.desktop_driver import DesktopDriver


def assert_exists(driver: DesktopDriver, locator: Locator, timeout_seconds: float = 5.0) -> None:
    if not driver.exists(locator, timeout_seconds=timeout_seconds):
        raise PlaybackExecutionError(f"Control not found: {locator.by}={locator.value}")


def assert_text_equals(driver: DesktopDriver, locator: Locator, expected: str) -> None:
    actual = driver.get_text(locator)
    if actual != expected:
        raise PlaybackExecutionError(f"Text mismatch. expected='{expected}', actual='{actual}'")
