from __future__ import annotations

import json
from pathlib import Path

from framework.core.models import Action


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
