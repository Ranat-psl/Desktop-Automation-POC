from framework.codegen.pytest_generator import generate_pytest_test
from framework.core.actions import assert_exists, click, wait
from framework.core.models import ActionType
from framework.playback.retry_policy import run_with_retry


def test_action_factory_builds_expected_types():
    actions = [
        click("auto_id", "okButton"),
        wait(1.0),
        assert_exists("title", "Main Window"),
    ]

    assert actions[0].action_type is ActionType.CLICK
    assert actions[1].action_type is ActionType.WAIT
    assert actions[2].action_type is ActionType.ASSERT_EXISTS


def test_retry_policy_runs_successfully_without_retries():
    result = run_with_retry(lambda: "ok", attempts=2, delay_seconds=0.01)
    assert result == "ok"


def test_codegen_returns_pytest_function_text():
    code = generate_pytest_test("sample_flow", [])
    assert "def test_sample_flow():" in code
