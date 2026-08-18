"""Unit tests for the execution dashboard reporting layer.

All tests are fast, deterministic, and require no Windows desktop interaction.
They validate the data contract, summary calculation, HTML generation, and
edge cases in the collector and dashboard modules.
"""
from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers — build synthetic execution data
# ---------------------------------------------------------------------------

def _make_test(
    name: str = "test_example",
    status: str = "passed",
    duration: float = 1.23,
    module: str = "tests/smoke/test_example.py",
    recording: str | None = None,
    failure: dict | None = None,
) -> dict[str, Any]:
    return {
        "node_id": f"{module}::{name}",
        "name": name,
        "module": module,
        "status": status,
        "duration_seconds": duration,
        "started_at": None,
        "recording": recording,
        "failure": failure,
    }


def _make_execution(tests: list[dict], **overrides) -> dict[str, Any]:
    """Build a minimal execution dict suitable for the dashboard generator."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for t in tests:
        s = t.get("status", "error")
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    pass_rate = round(counts["passed"] / total * 100, 1) if total else 0.0

    data: dict[str, Any] = {
        "execution_id": "exec_20260818_143022_abc12345",
        "suite": "tests/smoke",
        "started_at": "2026-08-18T14:30:22.123456+00:00",
        "finished_at": "2026-08-18T14:30:45.678901+00:00",
        "duration_seconds": 23.555,
        "environment": {
            "os": "Windows-11-10.0.26100",
            "python": "3.12.4",
            "pytest": "9.1.1",
            "framework_version": "day9-poc",
            "hostname": "TESTHOST",
        },
        "summary": {
            "total": total,
            "passed": counts["passed"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
            "error": counts["error"],
            "pass_rate": pass_rate,
        },
        "tests": tests,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Collector unit tests
# ---------------------------------------------------------------------------

class TestExecutionCollector:
    def test_initial_state_has_no_tests(self):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector(suite_name="test-suite")
        result = c.to_dict()
        assert result["summary"]["total"] == 0
        assert result["tests"] == []

    def test_execution_id_is_unique(self):
        from framework.reporting.collector import ExecutionCollector
        ids = {ExecutionCollector().execution_id for _ in range(10)}
        assert len(ids) == 10, "execution IDs must be unique"

    def test_execution_id_format(self):
        from framework.reporting.collector import ExecutionCollector
        exec_id = ExecutionCollector().execution_id
        assert exec_id.startswith("exec_"), f"bad prefix: {exec_id}"
        parts = exec_id.split("_")
        assert len(parts) == 4, f"expected 4 parts, got: {exec_id}"

    def test_suite_name_stored(self):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector(suite_name="my-suite")
        assert c.to_dict()["suite"] == "my-suite"

    def test_environment_fields_present(self):
        from framework.reporting.collector import ExecutionCollector
        env = ExecutionCollector().to_dict()["environment"]
        for field in ("os", "python", "pytest", "framework_version", "hostname"):
            assert field in env, f"missing env field: {field}"

    def test_finalise_sets_finished_at(self):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        assert c.to_dict()["finished_at"] is not None  # auto-set when called
        c.finalise()
        assert c.to_dict()["finished_at"] is not None

    def test_duration_is_non_negative(self):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.finalise()
        assert c.to_dict()["duration_seconds"] >= 0

    # ---- record_result via synthetic TestReport ----

    def _make_report(self, nodeid: str, when: str, outcome: str, duration: float = 0.5):
        """Build a minimal pytest.TestReport substitute."""

        class _FakeReport:
            def __init__(self):
                self.nodeid = nodeid
                self.when = when
                self.passed = outcome == "passed"
                self.failed = outcome == "failed"
                self.skipped = outcome == "skipped"
                self.duration = duration
                self.longrepr = None

        return _FakeReport()

    def test_record_passed_result(self):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.record_result(self._make_report("tests/t.py::test_ok", "call", "passed"))
        summary = c.to_dict()["summary"]
        assert summary["passed"] == 1
        assert summary["total"] == 1

    def test_record_failed_result(self):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.record_result(self._make_report("tests/t.py::test_bad", "call", "failed"))
        summary = c.to_dict()["summary"]
        assert summary["failed"] == 1

    def test_record_skipped_result(self):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.record_result(self._make_report("tests/t.py::test_skip", "call", "skipped"))
        summary = c.to_dict()["summary"]
        assert summary["skipped"] == 1

    def test_setup_pass_not_recorded(self):
        """Setup-phase pass events must not appear as test results."""
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.record_result(self._make_report("tests/t.py::test_ok", "setup", "passed"))
        assert c.to_dict()["summary"]["total"] == 0

    def test_teardown_not_recorded(self):
        """Teardown-phase events must not appear as test results."""
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.record_result(self._make_report("tests/t.py::test_ok", "teardown", "passed"))
        assert c.to_dict()["summary"]["total"] == 0

    def test_multiple_results_counted(self):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        for i in range(5):
            c.record_result(self._make_report(f"tests/t.py::test_{i}", "call", "passed"))
        c.record_result(self._make_report("tests/t.py::test_fail", "call", "failed"))
        c.record_result(self._make_report("tests/t.py::test_skip", "call", "skipped"))
        summary = c.to_dict()["summary"]
        assert summary["total"] == 7
        assert summary["passed"] == 5
        assert summary["failed"] == 1
        assert summary["skipped"] == 1


# ---------------------------------------------------------------------------
# Summary calculation
# ---------------------------------------------------------------------------

class TestSummaryCalculation:
    def test_pass_rate_all_pass(self):
        from framework.reporting.collector import _count_statuses
        tests = [{"status": "passed"}] * 8
        counts = _count_statuses(tests)
        total = counts["total"]
        rate = round(counts["passed"] / total * 100, 1)
        assert rate == 100.0

    def test_pass_rate_all_fail(self):
        from framework.reporting.collector import _count_statuses
        tests = [{"status": "failed"}] * 4
        counts = _count_statuses(tests)
        rate = round(counts["passed"] / counts["total"] * 100, 1)
        assert rate == 0.0

    def test_pass_rate_mixed(self):
        from framework.reporting.collector import _count_statuses
        tests = [{"status": "passed"}] * 8 + [{"status": "failed"}] * 2
        counts = _count_statuses(tests)
        rate = round(counts["passed"] / counts["total"] * 100, 1)
        assert rate == 80.0

    def test_empty_results_zero_total(self):
        from framework.reporting.collector import _count_statuses
        counts = _count_statuses([])
        assert counts["total"] == 0

    def test_duration_included_in_test_entry(self):
        """Duration from report is stored per test."""
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()

        class _R:
            nodeid = "t.py::t"
            when = "call"
            passed = True
            failed = False
            skipped = False
            duration = 3.77
            longrepr = None

        c.record_result(_R())
        test_entry = c.to_dict()["tests"][0]
        assert abs(test_entry["duration_seconds"] - 3.77) < 0.01


# ---------------------------------------------------------------------------
# Failure details extraction
# ---------------------------------------------------------------------------

class TestFailureExtraction:
    def test_failure_message_extracted(self):
        from framework.reporting.collector import _extract_failure

        class _R:
            when = "call"
            passed = False
            failed = True
            skipped = False
            longrepr = "AssertionError: expected True but got False"

        f = _extract_failure(_R())
        assert "AssertionError" in f["message"]

    def test_screenshot_path_extracted(self):
        from framework.reporting.collector import _extract_failure

        class _R:
            when = "call"
            passed = False
            failed = True
            skipped = False
            longrepr = (
                "PlaybackExecutionError: Playback failed at Action 2\n"
                "Failure screenshot: reports/screenshots/action2_click_20260818.png"
            )

        f = _extract_failure(_R())
        assert f["screenshot_path"] == "reports/screenshots/action2_click_20260818.png"

    def test_screenshot_path_none_when_absent(self):
        from framework.reporting.collector import _extract_failure

        class _R:
            when = "call"
            passed = False
            failed = True
            skipped = False
            longrepr = "RuntimeError: something went wrong"

        f = _extract_failure(_R())
        assert f["screenshot_path"] is None

    def test_action_context_extracted(self):
        from framework.reporting.collector import _extract_failure

        class _R:
            when = "call"
            passed = False
            failed = True
            skipped = False
            longrepr = "PlaybackExecutionError: Playback failed at Action 3: CLICK on 'Save'.\nReason: element not found"

        f = _extract_failure(_R())
        assert f["action_context"] is not None
        assert "Action 3" in f["action_context"]

    def test_no_action_context_when_absent(self):
        from framework.reporting.collector import _extract_failure

        class _R:
            when = "call"
            passed = False
            failed = True
            skipped = False
            longrepr = "AssertionError: something broke"

        f = _extract_failure(_R())
        assert f["action_context"] is None


# ---------------------------------------------------------------------------
# JSON save / load
# ---------------------------------------------------------------------------

class TestCollectorSave:
    def test_save_creates_json_file(self, tmp_path):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector(suite_name="test")
        c.finalise()
        out = c.save(output_dir=tmp_path)
        assert out.exists()
        assert out.suffix == ".json"

    def test_saved_json_is_valid(self, tmp_path):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.finalise()
        out = c.save(output_dir=tmp_path)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "execution_id" in data
        assert "summary" in data
        assert "tests" in data
        assert "environment" in data

    def test_saved_json_filename_matches_execution_id(self, tmp_path):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.finalise()
        out = c.save(output_dir=tmp_path)
        assert c.execution_id in out.name

    def test_empty_collector_saves_cleanly(self, tmp_path):
        from framework.reporting.collector import ExecutionCollector
        c = ExecutionCollector()
        c.finalise()
        out = c.save(output_dir=tmp_path)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["total"] == 0


# ---------------------------------------------------------------------------
# Dashboard generation
# ---------------------------------------------------------------------------

class TestDashboardGeneration:
    def _execution(self, **overrides) -> dict:
        tests = [
            _make_test("test_alpha", "passed", 1.1),
            _make_test("test_beta",  "passed", 0.5),
            _make_test("test_gamma", "failed", 2.3, failure={
                "message": "AssertionError: expected 1 got 2",
                "longrepr": "Full traceback here",
                "screenshot_path": None,
                "action_context": None,
            }),
            _make_test("test_delta", "skipped", 0.0),
        ]
        return _make_execution(tests, **overrides)

    def test_html_file_created(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        path = generate_dashboard(data, output_path=out)
        assert path.exists()

    def test_html_not_empty(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert len(content) > 500

    def test_html_contains_doctype(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_execution_id_in_output(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "exec_20260818_143022_abc12345" in content

    def test_pass_count_in_output(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        # 2 passed — should appear in summary cards
        assert "50.0%" in content  # pass rate

    def test_test_names_in_output(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "test_alpha" in content
        assert "test_gamma" in content

    def test_pass_badge_present(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "badge-pass" in content

    def test_fail_badge_present(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "badge-fail" in content

    def test_skip_badge_present(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "badge-skip" in content

    def test_failure_details_section_rendered(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "Failure Details" in content
        assert "AssertionError" in content

    def test_environment_section_rendered(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "TESTHOST" in content
        assert "3.12.4" in content

    def test_donut_chart_svg_present(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "<svg" in content
        assert "Pass Rate" in content

    def test_empty_execution_generates_valid_html(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = _make_execution([])
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "No test results" in content or "No data" in content

    def test_screenshot_link_in_failure_card(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        tests = [_make_test("test_snap", "failed", failure={
            "message": "element not found",
            "longrepr": "long trace",
            "screenshot_path": "reports/screenshots/action1_click_20260818.png",
            "action_context": "Playback failed at Action 1: CLICK",
        })]
        data = _make_execution(tests)
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "reports/screenshots/action1_click_20260818.png" in content
        assert "ss-link" in content

    def test_from_json_file(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        json_path = tmp_path / "exec.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "report.html"
        generate_dashboard(json_path, output_path=out)
        assert out.exists()

    def test_html_is_self_contained(self, tmp_path):
        """No external script/stylesheet src references should exist."""
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        # Should not link to external CDN resources
        assert "cdn.jsdelivr" not in content
        assert "unpkg.com" not in content
        assert "cdnjs.cloudflare" not in content

    def test_output_parent_created_if_missing(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        data = self._execution()
        nested = tmp_path / "a" / "b" / "c" / "report.html"
        generate_dashboard(data, output_path=nested)
        assert nested.exists()


# ---------------------------------------------------------------------------
# HTML safety — XSS escaping
# ---------------------------------------------------------------------------

class TestHtmlEscaping:
    def test_failure_message_escaped(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        tests = [_make_test("test_xss", "failed", failure={
            "message": "<script>alert('xss')</script>",
            "longrepr": "trace",
            "screenshot_path": None,
            "action_context": None,
        })]
        data = _make_execution(tests)
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "<script>alert" not in content
        assert "&lt;script&gt;" in content

    def test_test_name_escaped(self, tmp_path):
        from framework.reporting.dashboard import generate_dashboard
        tests = [_make_test("test_<b>bold</b>", "passed")]
        data = _make_execution(tests)
        out = tmp_path / "report.html"
        generate_dashboard(data, output_path=out)
        content = out.read_text(encoding="utf-8")
        assert "<b>bold</b>" not in content
