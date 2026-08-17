import os
import time

import pytest

from framework.core.models import Locator
from framework.driver.desktop_driver import DesktopDriver


@pytest.mark.ui
@pytest.mark.skipif(
    os.getenv("RUN_DESKTOP_UI", "0") != "1",
    reason="Set RUN_DESKTOP_UI=1 to run desktop smoke tests.",
)
def test_control_panel_launch_and_focus_smoke(desktop_driver: DesktopDriver) -> None:
    """Minimal smoke flow: launch Control Panel, focus it, validate a visible pane exists."""
    desktop_driver.start("control.exe")
    time.sleep(1.5)

    desktop_driver.focus_window(Locator(by="title", value="Control Panel"))
    assert desktop_driver.exists(Locator(by="control_type", value="Pane"), timeout_seconds=3)
    # desktop_driver fixture guarantees driver.quit() after this test.
