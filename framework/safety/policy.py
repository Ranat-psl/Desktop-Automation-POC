from __future__ import annotations

from framework.core.models import Action, ActionType


def is_sensitive_action(action: Action) -> bool:
    sensitive_types = {ActionType.CLICK, ActionType.TYPE}
    if action.action_type in sensitive_types:
        return bool(action.metadata.get("sensitive", False))
    return False
