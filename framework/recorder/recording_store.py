from __future__ import annotations

import json
import logging
from pathlib import Path

from framework.core.models import Action, ActionType, Locator
from framework.driver.screen_info import get_screen_size

_log = logging.getLogger(__name__)


class RecordingStore:
    def __init__(self, base_dir: Path | str = "recordings") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, actions: list[Action]) -> Path:
        path = self.base_dir / f"{name}.json"
        screen_w, screen_h = get_screen_size()
        action_list = [
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
        # Wrap in a versioned envelope so recording-level metadata can be stored
        # alongside actions without changing the action schema.
        payload = {
            "meta": {
                "version": 1,
                "screen_width": screen_w,
                "screen_height": screen_h,
            },
            "actions": action_list,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _log.info(
            "Recording saved: %s  (%d action(s))  screen=%dx%d",
            path.resolve(), len(actions), screen_w, screen_h,
        )
        return path

    def load(self, name: str) -> list[Action]:
        path = self.base_dir / f"{name}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))

        # Support both new envelope format {"meta":…, "actions":[…]}
        # and legacy flat-list format [action, …] so existing recordings
        # continue to work without modification.
        if isinstance(raw, dict):
            action_list = raw.get("actions", [])
        else:
            action_list = raw  # legacy flat list

        actions: list[Action] = []
        for item in action_list:
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

    def load_meta(self, name: str) -> dict:
        """Return the recording-level metadata dict, or empty dict for legacy files."""
        path = self.base_dir / f"{name}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw.get("meta", {})
        return {}

