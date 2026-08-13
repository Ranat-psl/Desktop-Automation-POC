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
def test_notepad_launch_and_type_smoke() -> None:
    """Minimal desktop smoke flow: launch Notepad, type text, validate editor exists."""
    driver = DesktopDriver(backend="uia")

    try:
        driver.start("notepad.exe")
        time.sleep(1)

        # Focus top-level Notepad window and interact with the editor.
        driver.focus_window(Locator(by="class_name", value="Notepad"))
        editor = Locator(by="control_type", value="Edit")

        driver.type_text(editor, "Desktop Automation POC")
        assert driver.exists(editor, timeout_seconds=3)
    finally:
        # Keep cleanup simple for POC to avoid leaving hanging app instances.
        subprocess.run(
            ["taskkill", "/IM", "notepad.exe", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
