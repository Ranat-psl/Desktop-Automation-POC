from __future__ import annotations

import json
from pathlib import Path

from framework.core.models import Action, ActionType, Locator


class RecordingStore:
    def __init__(self, base_dir: Path | str = "recordings") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, actions: list[Action]) -> Path:
        path = self.base_dir / f"{name}.json"
        payload = [
            {
                "action_type": action.action_type.value,
                "locator": None
                if action.locator is None
                else {"by": action.locator.by, "value": action.locator.value},
                "value": action.value,
                "timeout_seconds": action.timeout_seconds,
                "metadata": action.metadata,
            }
            for action in actions
        ]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def load(self, name: str) -> list[Action]:
        path = self.base_dir / f"{name}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))

        actions: list[Action] = []
        for item in payload:
            locator_data = item.get("locator")
            locator = None
            if locator_data is not None:
                locator = Locator(by=locator_data["by"], value=locator_data["value"])

            actions.append(
                Action(
                    action_type=ActionType(item["action_type"]),
                    locator=locator,
                    value=item.get("value"),
                    timeout_seconds=item.get("timeout_seconds"),
                    metadata=item.get("metadata", {}),
                )
            )

        return actions
