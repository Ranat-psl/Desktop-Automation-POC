from __future__ import annotations

from pathlib import Path
import json
import logging
import re as _re
from typing import TYPE_CHECKING, Generator

import pytest

if TYPE_CHECKING:
    from framework.reporting.collector import ExecutionCollector

# ---------------------------------------------------------------------------
# Execution dashboard — result collection
# ---------------------------------------------------------------------------

_collector: ExecutionCollector | None = None


def pytest_configure(config: pytest.Config) -> None:
    """Create the result collector for this session."""
    global _collector
    from framework.reporting.collector import ExecutionCollector
    suite = " ".join(str(a) for a in config.args) if config.args else "default"
    _collector = ExecutionCollector(suite_name=suite)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Feed every test report phase into the collector."""
    if _collector is not None:
        _collector.record_result(report)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Finalise collection, persist JSON, generate dashboard."""
    if _collector is None:
        return
    _collector.finalise()
    try:
        json_path = _collector.save()
        _generate_dashboard(json_path)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "Dashboard generation failed (non-fatal): %s", exc
        )


def _generate_dashboard(json_path: Path) -> None:
    from framework.reporting.dashboard import generate_dashboard, DEFAULT_OUTPUT
    out = generate_dashboard(json_path, output_path=DEFAULT_OUTPUT)
    logging.getLogger(__name__).info("Dashboard generated: %s", out)


# ---------------------------------------------------------------------------
# Screenshot → HTML report linkage
# ---------------------------------------------------------------------------

_SCREENSHOT_RE = _re.compile(r"Failure screenshot:\s*([^\n]+\.png)", _re.IGNORECASE)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attach failure screenshots to the pytest-html report when available."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        _attach_screenshot_to_report(report)


def _attach_screenshot_to_report(report) -> None:
    """Parse the failure message for a screenshot path and embed it as HTML extra."""
    try:
        from pytest_html import extras  # type: ignore[import]
    except ImportError:
        return  # pytest-html not installed; skip silently

    try:
        longrepr_text = str(report.longrepr) if report.longrepr else ""
        match = _SCREENSHOT_RE.search(longrepr_text)
        if not match:
            return

        screenshot_path = match.group(1).strip()
        path = Path(screenshot_path)
        if not path.exists():
            return

        # Embed as base64 so the report is portable (no file:// dependency).
        import base64
        img_data = base64.b64encode(path.read_bytes()).decode("ascii")

        if not hasattr(report, "extras"):
            report.extras = []

        report.extras.append(
            extras.image(
                f"data:image/png;base64,{img_data}",
                name="Failure Screenshot",
            )
        )
        report.extras.append(
            extras.text(screenshot_path, name="Screenshot Path")
        )
    except Exception:  # noqa: BLE001
        pass  # diagnostics must never break test reporting



@pytest.fixture(scope="session")
def framework_config() -> dict:
    """Load lightweight framework config without extra dependencies."""
    config_path = Path(__file__).parent / "config" / "framework_config.yaml"
    data: dict[str, str] = {}

    # Keep parser intentionally minimal: key: value pairs only.
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        data[key.strip()] = value.strip().strip("\"'")

    return data


@pytest.fixture(scope="session", autouse=True)
def configure_framework_logging(framework_config: dict) -> None:
    """Initialise stdlib logging once per session from config. No test-specific logic."""
    level_name = framework_config.get("log_level", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@pytest.fixture(scope="session")
def artifact_folder() -> Path:
    path = Path("reports")
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def session_metadata(artifact_folder: Path) -> Path:
    meta_path = artifact_folder / "session_metadata.json"
    payload = {"framework": "desktop-automation-poc", "stage": "day-2"}
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return meta_path


@pytest.fixture()
def desktop_driver() -> Generator:
    """Yield a DesktopDriver and guarantee the launched application is killed on teardown.

    Kills the specific PID started during the test — does not affect other
    running instances of the same executable.
    """
    from framework.driver.desktop_driver import DesktopDriver

    driver = DesktopDriver()
    try:
        yield driver
    finally:
        driver.quit()
