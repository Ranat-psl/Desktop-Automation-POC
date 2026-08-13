import os
import subprocess
import time

import pytest

from framework.core.models import Locator
from framework.driver.desktop_driver import DesktopDriver


@pytest.mark.ui
@pytest.mark.skipif(
    os.getenv("RUN_DESKTOP_UI", "0") != "1",
    reason="Set RUN_DESKTOP_UI=1 to run desktop smoke tests.",
)
def test_control_panel_launch_and_focus_smoke() -> None:
    """Minimal smoke flow: launch Control Panel, focus it, validate a visible pane exists."""
    driver = DesktopDriver(backend="uia")

    try:
        driver.start("control.exe")
        time.sleep(1.5)

        driver.focus_window(Locator(by="title", value="Control Panel"))
        assert driver.exists(Locator(by="control_type", value="Pane"), timeout_seconds=3)
    finally:
        # Keep cleanup simple for POC and avoid leaving desktop windows open.
        subprocess.run(
            ["taskkill", "/F", "/FI", "WINDOWTITLE eq *Control Panel*"],
            check=False,
            capture_output=True,
            text=True,
        )
