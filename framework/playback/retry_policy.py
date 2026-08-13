from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


def run_with_retry(func: Callable[[], T], attempts: int = 2, delay_seconds: float = 0.5) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry policy reached an unexpected state.")
