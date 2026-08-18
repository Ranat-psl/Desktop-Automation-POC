"""Pytest result collector — builds the execution JSON data contract.

This module hooks into pytest's reporting lifecycle and produces a structured
JSON file at ``reports/data/execution_<id>.json``.  The dashboard generator
reads this file; nothing in here depends on the dashboard renderer.

Data contract (ExecutionResult):
{
  "execution_id": "exec_20260818_143022_abc12345",
  "suite": "<pytest invocation args>",
  "started_at": "2026-08-18T14:30:22.123456",
  "finished_at": "2026-08-18T14:30:45.678901",
  "duration_seconds": 23.555,
  "environment": {
    "os": "Windows-11-...",
    "python": "3.12.4",
    "pytest": "9.1.1",
    "framework_version": "day9",
    "hostname": "WORKSTATION"
  },
  "summary": {
    "total": 10,
    "passed": 8,
    "failed": 1,
    "skipped": 1,
    "error": 0,
    "pass_rate": 80.0
  },
  "tests": [
    {
      "node_id": "tests/smoke/test_x.py::test_y",
      "name": "test_y",
      "module": "tests/smoke/test_x.py",
      "status": "passed",   // passed | failed | skipped | error
      "duration_seconds": 1.23,
      "started_at": null,
      "recording": null,
      "failure": null | {
        "message": "...",
        "longrepr": "...",
        "screenshot_path": "..." | null
      }
    }
  ]
}
"""
from __future__ import annotations

import json
import logging
import os
import platform
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

_log = logging.getLogger(__name__)

DATA_DIR = Path("reports/data")
_SCREENSHOT_RE_PATTERN = r"Failure screenshot:\s*([^\n]+\.png)"


# ---------------------------------------------------------------------------
# Public API used by conftest
# ---------------------------------------------------------------------------

class ExecutionCollector:
    """Accumulates test results during a pytest session."""

    def __init__(self, suite_name: str = "") -> None:
        self._suite = suite_name
        self._started_at: datetime = datetime.now(timezone.utc)
        self._finished_at: datetime | None = None
        self._tests: list[dict[str, Any]] = []
        self._execution_id: str = _make_execution_id()
        self._env: dict[str, str] = _collect_environment()

    # ------------------------------------------------------------------
    # Called from pytest hooks
    # ------------------------------------------------------------------

    def record_result(self, report: pytest.TestReport) -> None:
        """Integrate a single pytest TestReport into the collected results."""
        # Only process "call" phase (not setup/teardown) for pass/fail/skip.
        # Exception: collect "setup" phase errors as test errors.
        if report.when not in ("call", "setup"):
            return

        # Find an existing entry for this node (setup may create it first)
        existing = next(
            (t for t in self._tests if t["node_id"] == report.nodeid),
            None,
        )

        status = _status_from_report(report)

        # Skip setup-pass entries — they are not user-visible test results.
        if report.when == "setup" and status == "passed":
            return

        failure_info = None
        if status in ("failed", "error"):
            failure_info = _extract_failure(report)

        entry: dict[str, Any] = {
            "node_id": report.nodeid,
            "name": _short_name(report.nodeid),
            "module": _module_from_nodeid(report.nodeid),
            "status": status,
            "duration_seconds": round(getattr(report, "duration", 0.0) or 0.0, 4),
            "started_at": None,
            "recording": _extract_recording(report),
            "failure": failure_info,
        }

        if existing is not None:
            # Merge: a failing setup supersedes a later pass
            if status in ("failed", "error"):
                existing.update(entry)
            # Otherwise ignore duplicate (setup error already recorded)
        else:
            self._tests.append(entry)

    def finalise(self) -> None:
        self._finished_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        finished = self._finished_at or datetime.now(timezone.utc)
        duration = (finished - self._started_at).total_seconds()

        counts = _count_statuses(self._tests)
        total = counts["total"]
        pass_rate = round(counts["passed"] / total * 100, 1) if total else 0.0

        return {
            "execution_id": self._execution_id,
            "suite": self._suite,
            "started_at": self._started_at.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_seconds": round(duration, 3),
            "environment": self._env,
            "summary": {
                "total": total,
                "passed": counts["passed"],
                "failed": counts["failed"],
                "skipped": counts["skipped"],
                "error": counts["error"],
                "pass_rate": pass_rate,
            },
            "tests": self._tests,
        }

    def save(self, output_dir: Path | None = None) -> Path:
        """Persist the execution result JSON and return the path."""
        out_dir = Path(output_dir) if output_dir else DATA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self._execution_id}.json"
        out_path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        _log.info("Execution result saved: %s", out_path)
        return out_path

    @property
    def execution_id(self) -> str:
        return self._execution_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_execution_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"exec_{ts}_{short}"


def _collect_environment() -> dict[str, str]:
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    fw_version = os.getenv("FRAMEWORK_VERSION", "day9-poc")

    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "pytest": pytest.__version__,
        "framework_version": fw_version,
        "hostname": hostname,
    }


def _status_from_report(report: pytest.TestReport) -> str:
    if report.when == "setup" and report.failed:
        return "error"
    if report.passed:
        return "passed"
    if report.failed:
        return "failed"
    if report.skipped:
        return "skipped"
    return "error"


def _extract_failure(report: pytest.TestReport) -> dict[str, Any]:
    import re
    longrepr = str(report.longrepr) if report.longrepr else ""

    # Short human message: last non-empty line of longrepr up to 400 chars
    lines = [ln.strip() for ln in longrepr.splitlines() if ln.strip()]
    message = lines[-1][:400] if lines else "Unknown failure"

    # Extract screenshot path from user-friendly error message
    screenshot_path: str | None = None
    match = re.search(_SCREENSHOT_RE_PATTERN, longrepr, re.IGNORECASE)
    if match:
        screenshot_path = match.group(1).strip()

    # Action context from PlaybackExecutionError messages
    action_context: str | None = None
    if "Playback failed at Action" in longrepr:
        for ln in longrepr.splitlines():
            if "Playback failed at Action" in ln:
                action_context = ln.strip()[:300]
                break

    return {
        "message": message,
        "longrepr": longrepr,
        "screenshot_path": screenshot_path,
        "action_context": action_context,
    }


def _extract_recording(report: pytest.TestReport) -> str | None:
    """Try to infer recording name from test node id or markers."""
    # Convention: test functions named test_*_playback or test_*_recording
    name = _short_name(report.nodeid).lower()
    if "playback" in name or "recording" in name:
        # Strip common prefixes/suffixes to get a cleaner name
        return name
    return None


def _short_name(nodeid: str) -> str:
    return nodeid.split("::")[-1] if "::" in nodeid else nodeid


def _module_from_nodeid(nodeid: str) -> str:
    return nodeid.split("::")[0] if "::" in nodeid else nodeid


def _count_statuses(tests: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for t in tests:
        s = t.get("status", "error")
        counts[s] = counts.get(s, 0) + 1
    counts["total"] = sum(counts.values())
    return counts
