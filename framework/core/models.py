from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    LAUNCH = "launch"
    CLICK = "click"
    TYPE = "type"
    WAIT = "wait"
    ASSERT_EXISTS = "assert_exists"
    ASSERT_TEXT = "assert_text"


@dataclass(slots=True)
class Locator:
    by: str
    value: str


@dataclass(slots=True)
class Action:
    action_type: ActionType
    locator: Locator | None = None
    value: str | None = None
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
