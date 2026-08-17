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
def test_notepad_launch_and_type_smoke(desktop_driver: DesktopDriver) -> None:
    """Minimal desktop smoke flow: launch Notepad, type text, validate editor exists."""
    desktop_driver.start("notepad.exe")
    time.sleep(1)

    # Focus top-level Notepad window and interact with the editor.
    desktop_driver.focus_window(Locator(by="class_name", value="Notepad"))
    editor = Locator(by="control_type", value="Document")

    desktop_driver.type_text(editor, "Desktop Automation POC")
    assert desktop_driver.exists(editor, timeout_seconds=3)
    # desktop_driver fixture guarantees driver.quit() after this test.
