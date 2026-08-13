from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from framework.core.models import Action


@dataclass(slots=True)
class PlanRequest:
    objective: str
    constraints: list[str]


class PlannerInterface(Protocol):
    """Future AI planner contract. Execution remains framework-controlled."""

    def propose_actions(self, request: PlanRequest) -> list[Action]:
        ...
