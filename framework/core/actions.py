from __future__ import annotations

from framework.core.models import Action, ActionType, Locator


def launch(executable_path: str) -> Action:
    return Action(action_type=ActionType.LAUNCH, value=executable_path)


def click(by: str, value: str, *, timeout_seconds: float | None = None) -> Action:
    return Action(
        action_type=ActionType.CLICK,
        locator=Locator(by=by, value=value),
        timeout_seconds=timeout_seconds,
    )


def type_text(by: str, value: str, text: str, *, timeout_seconds: float | None = None) -> Action:
    return Action(
        action_type=ActionType.TYPE,
        locator=Locator(by=by, value=value),
        value=text,
        timeout_seconds=timeout_seconds,
    )


def wait(seconds: float) -> Action:
    return Action(action_type=ActionType.WAIT, timeout_seconds=seconds)


def assert_exists(by: str, value: str, *, timeout_seconds: float | None = None) -> Action:
    return Action(
        action_type=ActionType.ASSERT_EXISTS,
        locator=Locator(by=by, value=value),
        timeout_seconds=timeout_seconds,
    )


def assert_text(by: str, value: str, expected_text: str, *, timeout_seconds: float | None = None) -> Action:
    return Action(
        action_type=ActionType.ASSERT_TEXT,
        locator=Locator(by=by, value=value),
        value=expected_text,
        timeout_seconds=timeout_seconds,
    )
