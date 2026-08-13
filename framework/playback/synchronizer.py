from __future__ import annotations

import time
from collections.abc import Callable


def wait_until(predicate: Callable[[], bool], timeout_seconds: float = 10.0, poll_seconds: float = 0.2) -> bool:
    end_time = time.time() + timeout_seconds
    while time.time() < end_time:
        if predicate():
            return True
        time.sleep(poll_seconds)
    return False
