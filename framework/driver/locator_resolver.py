from __future__ import annotations

from framework.core.exceptions import LocatorResolutionError
from framework.core.models import Locator


_SUPPORTED = {"title", "auto_id", "class_name", "control_type"}


def to_kwargs(locator: Locator) -> dict[str, str]:
    if locator.by not in _SUPPORTED:
        raise LocatorResolutionError(f"Unsupported locator strategy: {locator.by}")
    return {locator.by: locator.value}
