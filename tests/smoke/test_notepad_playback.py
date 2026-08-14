import os
import subprocess
import time

import pytest

from framework.core.actions import assert_exists, launch, type_text
from framework.core.models import Locator
from framework.driver.desktop_driver import DesktopDriver
from framework.playback.executor import PlaybackExecutor
from framework.recorder.recording_store import RecordingStore


@pytest.mark.ui
@pytest.mark.skipif(
    os.getenv("RUN_DESKTOP_UI", "0") != "1",
    reason="Set RUN_DESKTOP_UI=1 to run desktop smoke tests.",
)
def test_notepad_recording_save_load_and_playback() -> None:
    """Prove record->save->load->replay using existing Action/Driver/Executor stack."""
    recording_name = f"notepad_playback_{int(time.time())}"
    store = RecordingStore(base_dir="recordings")
    driver = DesktopDriver(backend="uia")
    executor = PlaybackExecutor(driver=driver)

    actions = [
        launch("notepad.exe"),
        type_text("control_type", "Document", "Hello Desktop Automation"),
        assert_exists("control_type", "Document", timeout_seconds=3),
    ]

    try:
        store.save(recording_name, actions)
        loaded_actions = store.load(recording_name)
        executor.run(loaded_actions[:1])

        # Focus is currently an explicit driver operation in this POC contract.
        driver.focus_window(Locator(by="class_name", value="Notepad"))
        executor.run(loaded_actions[1:])

        assert driver.exists(Locator(by="control_type", value="Document"), timeout_seconds=3)
        text = driver.get_text(Locator(by="control_type", value="Document"))
        assert "Hello" in text
        assert "Automation" in text
    finally:
        subprocess.run(
            ["taskkill", "/IM", "notepad.exe", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
