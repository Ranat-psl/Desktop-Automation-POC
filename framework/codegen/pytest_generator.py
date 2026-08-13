from __future__ import annotations

from framework.core.models import Action


def generate_pytest_test(test_name: str, actions: list[Action]) -> str:
    lines = [
        "import pytest",
        "",
        f"def test_{test_name}():",
        "    # Generated placeholder test body from recorded actions.",
        f"    assert {len(actions)} >= 0",
    ]
    return "\n".join(lines) + "\n"
