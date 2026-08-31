"""Lightweight screen resolution query.

Provides a single function that returns the virtual-screen pixel dimensions
so they can be stored in recording metadata and used during playback to
scale recorded coordinates to the current resolution.
"""
from __future__ import annotations

import ctypes
import logging

_log = logging.getLogger(__name__)

# Windows system-metric constants
_SM_CXVIRTUALSCREEN = 78   # total width of virtual screen in pixels
_SM_CYVIRTUALSCREEN = 79   # total height of virtual screen in pixels


def get_screen_size() -> tuple[int, int]:
    """Return ``(width, height)`` of the Windows virtual screen.

    Uses ``GetSystemMetrics`` which does not require a display handle.
    Falls back to ``(0, 0)`` if the call is unavailable (e.g. CI / Linux).
    """
    try:
        w = ctypes.windll.user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)
        h = ctypes.windll.user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)
        if w > 0 and h > 0:
            return (int(w), int(h))
    except Exception as exc:  # noqa: BLE001
        _log.debug("get_screen_size: GetSystemMetrics unavailable (%s)", exc)
    return (0, 0)


def scale_coords(
    x: int,
    y: int,
    recorded_width: int,
    recorded_height: int,
) -> tuple[int, int]:
    """Scale ``(x, y)`` from the recorded resolution to the current resolution.

    If either recorded dimension is zero, or the current screen size cannot be
    determined, the original coordinates are returned unchanged.

    Parameters
    ----------
    x, y:
        Coordinates as recorded.
    recorded_width, recorded_height:
        Screen dimensions at the time of recording (pixels).

    Returns
    -------
    tuple[int, int]
        Scaled ``(x, y)`` for the current screen.
    """
    if recorded_width <= 0 or recorded_height <= 0:
        return (x, y)

    current_w, current_h = get_screen_size()
    if current_w <= 0 or current_h <= 0:
        return (x, y)

    if current_w == recorded_width and current_h == recorded_height:
        return (x, y)   # Same resolution — no scaling needed.

    scaled_x = int(round(x * current_w / recorded_width))
    scaled_y = int(round(y * current_h / recorded_height))
    _log.debug(
        "scale_coords: (%d,%d) at %dx%d → (%d,%d) at %dx%d",
        x, y, recorded_width, recorded_height,
        scaled_x, scaled_y, current_w, current_h,
    )
    return (scaled_x, scaled_y)
