"""Screenshot capture utilities for playback failure diagnostics.

Uses PowerShell + System.Drawing (built-in on Windows) to capture the primary
screen as a PNG file.  No third-party Python dependencies are required beyond
those already listed in requirements.txt.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

_log = logging.getLogger(__name__)

# Default location for failure screenshots (relative to project root).
SCREENSHOT_DIR = Path("reports/screenshots")

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_\-]")


def capture_failure_screenshot(
    output_dir: Path | None = None,
    prefix: str = "failure",
) -> Path:
    """Capture a full-desktop screenshot and persist it as a PNG file.

    Parameters
    ----------
    output_dir:
        Directory to write the screenshot into.  Created automatically if it
        does not exist.  Defaults to ``reports/screenshots`` relative to the
        current working directory.
    prefix:
        Filename prefix (e.g. recording name + action label).  A timestamp is
        appended automatically to make names unique.

    Returns
    -------
    Path
        Absolute path of the saved screenshot file.

    Raises
    ------
    RuntimeError
        If the screenshot could not be written (PowerShell error or file not
        created after the command exits).
    """
    if output_dir is None:
        output_dir = SCREENSHOT_DIR

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{_sanitise(prefix)}_{timestamp}.png"
    output_path = (output_dir / filename).resolve()

    _capture_via_powershell(output_path)
    return output_path


def _sanitise(name: str) -> str:
    """Replace filesystem-unsafe characters and truncate to 64 chars."""
    return _UNSAFE_RE.sub("_", name)[:64]


def _capture_via_powershell(output_path: Path) -> None:
    """Write a PNG screenshot of the primary screen using PowerShell.

    The output path is passed via an environment variable (_DIAG_SS_PATH)
    to avoid any shell-injection risk from caller-supplied filenames.

    Raises
    ------
    RuntimeError
        If PowerShell exits with a non-zero return code **or** if the expected
        output file is not found after the command completes.
    """
    abs_path = str(output_path)
    env = {**os.environ, "_DIAG_SS_PATH": abs_path}

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
                "$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                "$b=[System.Drawing.Bitmap]::new($s.Width,$s.Height); "
                "$g=[System.Drawing.Graphics]::FromImage($b); "
                "$g.CopyFromScreen($s.Left,$s.Top,0,0,$s.Size); "
                "$b.Save($Env:_DIAG_SS_PATH); "
                "$g.Dispose(); $b.Dispose()"
            ),
        ],
        capture_output=True,
        timeout=15,
        env=env,
    )

    stderr = result.stderr.decode(errors="replace").strip()
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(
            f"Screenshot capture failed (rc={result.returncode}): {stderr}"
        )
