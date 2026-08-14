from pathlib import Path
import subprocess
import sys

from framework.codegen.pytest_generator import generate_pytest_test
from framework.core.actions import assert_exists, assert_text, click, launch, type_text, wait
from framework.core.models import ActionType
from framework.playback.retry_policy import run_with_retry
from framework.recorder.recording_store import RecordingStore


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


def test_codegen_includes_business_readable_scenario_documentation():
    actions = [
        launch("notepad.exe"),
        type_text("control_type", "Document", "Hello Desktop Automation"),
        assert_exists("control_type", "Document", timeout_seconds=3),
    ]
    actions[0].metadata.update(
        {
            "scenario_name": "Create A Notepad Entry",
            "business_purpose": "Verify a user can create an entry in Notepad for operational notes.",
            "expected_result": "The user entry is present and visible in Notepad.",
        }
    )

    code = generate_pytest_test("notepad_playback", actions)

    assert "# Test Scenario: Create A Notepad Entry" in code
    assert "# Business Purpose:" in code
    assert "# Expected Result:" in code
    assert "# Step 1:" in code
    assert "# Business action:" in code
    assert "desktop.start('notepad.exe')" in code
    assert "desktop.type_text(Locator(by='control_type', value='Document'), 'Hello Desktop Automation')" in code
    assert "assert desktop.exists(Locator(by='control_type', value='Document'), timeout_seconds=3)" in code


def test_codegen_uses_business_validation_comment_for_assertions():
    actions = [assert_exists("title", "Main Window")]
    actions[0].metadata["business_validation"] = "Confirm the main workflow window is available to the user."

    code = generate_pytest_test("validation_flow", actions)

    assert "# Business validation: Confirm the main workflow window is available to the user." in code


def test_generated_code_is_valid_python_and_has_all_supported_statements():
    actions = [
        launch("notepad.exe"),
        click("title", "File"),
        type_text("control_type", "Document", "Hello Desktop Automation"),
        wait(0),
        assert_exists("control_type", "Document", timeout_seconds=3),
        assert_text("control_type", "Document", "Hello Desktop Automation"),
    ]

    actions[0].metadata.update(
        {
            "scenario_name": "Create And Verify Notepad Entry",
            "business_purpose": "Verify that a user can create and validate a note entry.",
            "expected_result": "The entered note is available in the editor.",
            "step_title": "Step 1: Open the note-taking application",
            "business_action": "Start the application used by business users to capture notes.",
        }
    )
    actions[1].metadata.update(
        {
            "step_title": "Step 2: Open the primary command area",
            "business_action": "Access the command area required to continue the user workflow.",
        }
    )
    actions[2].metadata.update(
        {
            "step_title": "Step 3: Enter note content",
            "business_action": "Record the user-provided information in the active editor.",
        }
    )
    actions[3].metadata.update(
        {
            "step_title": "Step 4: Wait for UI readiness",
            "business_action": "Allow the application to finish any pending UI updates.",
        }
    )
    actions[4].metadata.update(
        {
            "step_title": "Step 5: Validate editor availability",
            "business_validation": "Confirm the editor remains available for user verification.",
        }
    )
    actions[5].metadata.update(
        {
            "step_title": "Step 6: Validate note content",
            "business_validation": "Confirm the saved note text matches the expected business value.",
        }
    )

    code = generate_pytest_test("business_readable_flow", actions)

    compile(code, "generated_business_readable_flow.py", "exec")

    assert "# Test Scenario: Create And Verify Notepad Entry" in code
    assert "# Business Purpose:" in code
    assert "# Expected Result:" in code
    assert "# Step 1: Open the note-taking application" in code
    assert "# Step 6: Validate note content" in code
    assert "# Business action: Start the application used by business users to capture notes." in code
    assert "# Business validation: Confirm the saved note text matches the expected business value." in code

    assert "desktop.start('notepad.exe')" in code
    assert "desktop.click(Locator(by='title', value='File'))" in code
    assert "desktop.type_text(Locator(by='control_type', value='Document'), 'Hello Desktop Automation')" in code
    assert "time.sleep(0)" in code
    assert "assert desktop.exists(Locator(by='control_type', value='Document'), timeout_seconds=3)" in code
    assert "assert desktop.get_text(Locator(by='control_type', value='Document')) == 'Hello Desktop Automation'" in code


def test_generated_code_executes_against_existing_driver_contract(monkeypatch):
    class FakeDesktopDriver:
        instances: list["FakeDesktopDriver"] = []

        def __init__(self, backend: str = "uia") -> None:
            self.backend = backend
            self.started: list[str] = []
            self.clicked: list[tuple[str, str]] = []
            self.typed: list[tuple[str, str, str]] = []
            self.last_text = ""
            FakeDesktopDriver.instances.append(self)

        def start(self, executable_path: str) -> None:
            self.started.append(executable_path)

        def click(self, locator):
            self.clicked.append((locator.by, locator.value))

        def type_text(self, locator, text: str) -> None:
            self.typed.append((locator.by, locator.value, text))
            self.last_text = text

        def exists(self, locator, timeout_seconds: float = 5.0) -> bool:
            return True

        def get_text(self, locator) -> str:
            return self.last_text

    import framework.driver.desktop_driver as desktop_driver_module

    monkeypatch.setattr(desktop_driver_module, "DesktopDriver", FakeDesktopDriver)

    actions = [
        launch("notepad.exe"),
        click("title", "File"),
        type_text("control_type", "Document", "Hello Desktop Automation"),
        assert_exists("control_type", "Document"),
        assert_text("control_type", "Document", "Hello Desktop Automation"),
    ]
    code = generate_pytest_test("generated_execution_flow", actions)

    namespace: dict[str, object] = {}
    exec(compile(code, "generated_execution_flow.py", "exec"), namespace)
    namespace["test_generated_execution_flow"]()

    fake = FakeDesktopDriver.instances[-1]
    assert fake.started == ["notepad.exe"]
    assert fake.clicked == [("title", "File")]
    assert fake.typed == [("control_type", "Document", "Hello Desktop Automation")]


def test_generated_python_file_is_pytest_executable(tmp_path: Path):
    code = generate_pytest_test("generated_pytest_exec", [])
    generated_file = tmp_path / "test_generated_pytest_exec.py"
    generated_file.write_text(code, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(generated_file), "-q"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "1 passed" in result.stdout


def test_old_and_new_flows_integrate_without_breaking_recording_playback_contract(tmp_path: Path):
    # Old flow: action list -> save -> load
    store = RecordingStore(base_dir=tmp_path)
    actions = [
        launch("notepad.exe"),
        type_text("control_type", "Document", "Hello Desktop Automation"),
        assert_exists("control_type", "Document", timeout_seconds=3),
    ]

    path = store.save("integration_flow", actions)
    loaded_actions = store.load("integration_flow")

    assert path.exists()
    assert len(loaded_actions) == 3
    assert loaded_actions[0].action_type is ActionType.LAUNCH
    assert loaded_actions[1].action_type is ActionType.TYPE
    assert loaded_actions[2].action_type is ActionType.ASSERT_EXISTS

    # New flow: action list -> python generator -> executable source contract
    code = generate_pytest_test("integration_flow", loaded_actions)
    compile(code, "generated_integration_flow.py", "exec")

    assert "desktop.start('notepad.exe')" in code
    assert "desktop.type_text(Locator(by='control_type', value='Document'), 'Hello Desktop Automation')" in code
    assert "assert desktop.exists(Locator(by='control_type', value='Document'), timeout_seconds=3)" in code
