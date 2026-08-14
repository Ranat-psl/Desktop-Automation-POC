from __future__ import annotations

from framework.core.models import Action, ActionType


def _scenario_metadata(test_name: str, actions: list[Action]) -> tuple[str, str, str]:
    scenario_name = test_name.replace("_", " ").title()
    business_purpose = "Validate the business workflow represented by this automated scenario."
    expected_result = "The workflow completes successfully with expected outcomes."

    for action in actions:
        metadata = action.metadata or {}
        scenario_name = metadata.get("scenario_name", scenario_name)
        business_purpose = metadata.get("business_purpose", business_purpose)
        expected_result = metadata.get("expected_result", expected_result)
        # First action containing scenario metadata is sufficient.
        if any(key in metadata for key in ("scenario_name", "business_purpose", "expected_result")):
            break

    return scenario_name, business_purpose, expected_result


def _step_business_text(action: Action, step_number: int) -> tuple[str, str]:
    metadata = action.metadata or {}
    default_title = f"Step {step_number}: Perform {action.action_type.value} action"

    if action.action_type is ActionType.LAUNCH:
        default_title = f"Step {step_number}: Launch the application"
        default_business = "Open the business application to begin the workflow."
    elif action.action_type is ActionType.CLICK:
        default_title = f"Step {step_number}: Select the target control"
        default_business = "Trigger the next business operation by selecting the target control."
    elif action.action_type is ActionType.TYPE:
        default_title = f"Step {step_number}: Enter required information"
        default_business = "Provide the required business data to continue the process."
    elif action.action_type is ActionType.WAIT:
        default_title = f"Step {step_number}: Wait for application readiness"
        default_business = "Allow the application state to stabilize before continuing."
    elif action.action_type is ActionType.ASSERT_EXISTS:
        default_title = f"Step {step_number}: Validate control availability"
        default_business = "Confirm the required control is available for the user workflow."
    else:
        default_title = f"Step {step_number}: Validate resulting business state"
        default_business = "Confirm the resulting information matches expected business output."

    step_title = metadata.get("step_title", default_title)
    if action.action_type in (ActionType.ASSERT_EXISTS, ActionType.ASSERT_TEXT):
        business_line = metadata.get("business_validation", metadata.get("business_action", default_business))
        business_label = "Business validation"
    else:
        business_line = metadata.get("business_action", default_business)
        business_label = "Business action"

    return step_title, f"{business_label}: {business_line}"


def _locator_expr(action: Action) -> str:
    if action.locator is None:
        return "None"
    return f'Locator(by={action.locator.by!r}, value={action.locator.value!r})'


def _automation_statement(action: Action) -> str:
    if action.action_type is ActionType.LAUNCH:
        return f"desktop.start({(action.value or '')!r})"
    if action.action_type is ActionType.CLICK:
        return f"desktop.click({_locator_expr(action)})"
    if action.action_type is ActionType.TYPE:
        return f"desktop.type_text({_locator_expr(action)}, {(action.value or '')!r})"
    if action.action_type is ActionType.WAIT:
        timeout = action.timeout_seconds if action.timeout_seconds is not None else 0
        return f"time.sleep({timeout})"
    if action.action_type is ActionType.ASSERT_EXISTS:
        timeout = action.timeout_seconds if action.timeout_seconds is not None else 5.0
        return f"assert desktop.exists({_locator_expr(action)}, timeout_seconds={timeout})"
    if action.action_type is ActionType.ASSERT_TEXT:
        return f"assert desktop.get_text({_locator_expr(action)}) == {(action.value or '')!r}"
    return "# Unsupported action type"


def generate_pytest_test(test_name: str, actions: list[Action]) -> str:
    scenario_name, business_purpose, expected_result = _scenario_metadata(test_name, actions)

    lines = [
        "import time",
        "",
        "from framework.core.models import Locator",
        "from framework.driver.desktop_driver import DesktopDriver",
        "",
        "# ============================================================",
        f"# Test Scenario: {scenario_name}",
        "#",
        "# Business Purpose:",
        f"# {business_purpose}",
        "#",
        "# Expected Result:",
        f"# {expected_result}",
        "# ============================================================",
        "",
        f"def test_{test_name}():",
        '    desktop = DesktopDriver(backend="uia")',
        "    try:",
    ]

    if not actions:
        lines.extend(
            [
                "        # Step 1: Validate generator scaffold",
                "        # Business validation: Confirm the generated test is executable even when no actions exist.",
                "        assert True",
            ]
        )
    else:
        for index, action in enumerate(actions, start=1):
            step_title, business_line = _step_business_text(action, index)
            lines.append(f"        # {step_title}")
            lines.append(f"        # {business_line}")
            lines.append(f"        {_automation_statement(action)}")
            lines.append("")

    lines.extend(
        [
            "    finally:",
            "        # Cleanup hook reserved for framework-managed teardown in generated suites.",
            "        pass",
        ]
    )

    return "\n".join(lines) + "\n"
