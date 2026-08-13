from __future__ import annotations

from collections.abc import Callable

from framework.core.exceptions import ApprovalRequiredError
from framework.core.models import Action


class ApprovalGate:
    """Human-in-the-loop checkpoint before sensitive actions."""

    def __init__(self, approver: Callable[[Action], bool] | None = None) -> None:
        self._approver = approver

    def require_approval(self, action: Action) -> None:
        if self._approver is None:
            raise ApprovalRequiredError("Sensitive action blocked: no approver configured.")
        if not self._approver(action):
            raise ApprovalRequiredError("Sensitive action denied by approver.")
