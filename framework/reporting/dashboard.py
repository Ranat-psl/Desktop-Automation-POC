"""Professional HTML execution dashboard generator.

Reads an ExecutionResult JSON (produced by collector.py) and renders a
self-contained HTML file that:
  - works offline (no CDN dependencies)
  - contains all CSS and JavaScript inline
  - renders an SVG donut chart (no external charting library required)
  - renders a bar chart for pass/fail/skipped distribution
  - displays a professional test execution table
  - shows failure details with expandable stack traces
  - shows environment and execution metadata
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path("reports/html/report.html")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_dashboard(
    execution_json: Path | dict[str, Any],
    output_path: Path | None = None,
) -> Path:
    """Generate the HTML dashboard from an execution result.

    Parameters
    ----------
    execution_json:
        Either a Path to the JSON file or the parsed dict.
    output_path:
        Destination HTML file.  Defaults to ``reports/html/report.html``.

    Returns
    -------
    Path
        Absolute path to the generated HTML file.
    """
    if isinstance(execution_json, (str, Path)):
        data: dict[str, Any] = json.loads(Path(execution_json).read_text(encoding="utf-8"))
    else:
        data = dict(execution_json)

    out = Path(output_path) if output_path else DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)

    html = _render(data)
    out.write_text(html, encoding="utf-8")
    _log.info("Dashboard written: %s", out)
    return out.resolve()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_STATUS_BADGE: dict[str, tuple[str, str]] = {
    "passed":  ("badge-pass",  "PASS"),
    "failed":  ("badge-fail",  "FAIL"),
    "skipped": ("badge-skip",  "SKIP"),
    "error":   ("badge-error", "ERROR"),
}

_STATUS_COLOR: dict[str, str] = {
    "passed":  "#22c55e",
    "failed":  "#ef4444",
    "skipped": "#f59e0b",
    "error":   "#a855f7",
}


def _render(data: dict[str, Any]) -> str:
    summary = data.get("summary", {})
    tests = data.get("tests", [])
    env = data.get("environment", {})

    total    = summary.get("total", 0)
    passed   = summary.get("passed", 0)
    failed   = summary.get("failed", 0)
    skipped  = summary.get("skipped", 0)
    error    = summary.get("error", 0)
    pass_rate = summary.get("pass_rate", 0.0)
    duration = data.get("duration_seconds", 0.0)
    exec_id  = data.get("execution_id", "—")
    suite    = data.get("suite", "—") or "—"
    started  = _fmt_ts(data.get("started_at", ""))
    finished = _fmt_ts(data.get("finished_at", ""))
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    donut_svg = _donut_chart(passed, failed, skipped, error, total)
    bar_svg   = _bar_chart(passed, failed, skipped, error)
    test_rows = _test_table_rows(tests)
    failure_cards = _failure_cards(tests)
    env_rows  = _env_rows(env, exec_id, suite, started, finished, generated)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Execution Dashboard — {exec_id}</title>
<style>
{_CSS}
</style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <div class="header-brand">
      <span class="brand-icon">&#9654;</span>
      <span class="brand-name">Desktop Automation POC</span>
    </div>
    <div class="header-meta">
      <span class="exec-badge">Execution Dashboard</span>
    </div>
  </div>
</header>

<main class="main-content">

  <!-- SUMMARY CARDS -->
  <section class="section">
    <h2 class="section-title">Execution Summary</h2>
    <div class="cards-grid">
      {_card("Total Tests", str(total), "card-total")}
      {_card("Passed", str(passed), "card-pass")}
      {_card("Failed", str(failed), "card-fail")}
      {_card("Skipped", str(skipped), "card-skip")}
      {_card("Errors", str(error), "card-error")}
      {_card("Pass Rate", f"{pass_rate}%", "card-rate")}
      {_card("Duration", f"{duration:.1f}s", "card-dur")}
    </div>
  </section>

  <!-- CHARTS -->
  <section class="section">
    <h2 class="section-title">Result Distribution</h2>
    <div class="charts-row">
      <div class="chart-box">
        <h3 class="chart-title">Pass / Fail / Skip</h3>
        {donut_svg}
        <div class="donut-legend">
          <span class="legend-dot" style="background:#22c55e"></span>Passed {passed}
          <span class="legend-dot" style="background:#ef4444"></span>Failed {failed}
          <span class="legend-dot" style="background:#f59e0b"></span>Skipped {skipped}
          {(f'<span class="legend-dot" style="background:#a855f7"></span>Error {error}') if error else ''}
        </div>
      </div>
      <div class="chart-box">
        <h3 class="chart-title">Result Counts</h3>
        {bar_svg}
      </div>
    </div>
  </section>

  <!-- TEST TABLE -->
  <section class="section">
    <h2 class="section-title">Test Execution</h2>
    <div class="table-wrapper">
      <table class="exec-table">
        <thead>
          <tr>
            <th>Test Name</th>
            <th>Module</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Recording</th>
          </tr>
        </thead>
        <tbody>
          {test_rows if test_rows else '<tr><td colspan="5" class="empty-row">No test results collected.</td></tr>'}
        </tbody>
      </table>
    </div>
  </section>

  <!-- FAILURE DETAILS -->
  {"" if not failure_cards else f'''
  <section class="section">
    <h2 class="section-title">Failure Details</h2>
    {failure_cards}
  </section>
  '''}

  <!-- ENVIRONMENT & EXECUTION INFO -->
  <section class="section">
    <h2 class="section-title">Environment &amp; Execution Info</h2>
    <table class="env-table">
      <tbody>
        {env_rows}
      </tbody>
    </table>
  </section>

</main>

<footer class="site-footer">
  <span>Report generated {generated}</span>
  &nbsp;|&nbsp;
  <span>Desktop Automation POC</span>
</footer>

<script>
{_JS}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Component renderers
# ---------------------------------------------------------------------------

def _card(label: str, value: str, cls: str) -> str:
    return f"""
    <div class="card {cls}">
      <div class="card-value">{value}</div>
      <div class="card-label">{label}</div>
    </div>"""


def _donut_chart(passed: int, failed: int, skipped: int, error: int, total: int) -> str:
    if total == 0:
        return '<svg width="160" height="160" viewBox="0 0 160 160"><circle cx="80" cy="80" r="60" fill="none" stroke="#e5e7eb" stroke-width="28"/><text x="80" y="86" text-anchor="middle" fill="#9ca3af" font-size="14">No data</text></svg>'

    segments = [
        (passed,  "#22c55e"),
        (failed,  "#ef4444"),
        (skipped, "#f59e0b"),
        (error,   "#a855f7"),
    ]

    cx, cy, r = 80, 80, 54
    stroke_w = 28
    circumference = 2 * 3.14159265 * r
    offset = 0.0
    paths = []
    for count, color in segments:
        if count == 0:
            continue
        frac = count / total
        dash = frac * circumference
        paths.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke_w}" stroke-dasharray="{dash:.4f} {circumference:.4f}" '
            f'stroke-dashoffset="{-offset:.4f}" transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += dash

    pass_pct = f"{passed / total * 100:.0f}%"
    svg_inner = "\n  ".join(paths)
    return f"""<svg width="160" height="160" viewBox="0 0 160 160">
  {svg_inner}
  <text x="{cx}" y="{cy - 6}" text-anchor="middle" fill="#111827" font-size="20" font-weight="700">{pass_pct}</text>
  <text x="{cx}" y="{cy + 14}" text-anchor="middle" fill="#6b7280" font-size="11">Pass Rate</text>
</svg>"""


def _bar_chart(passed: int, failed: int, skipped: int, error: int) -> str:
    bars = [
        ("Passed",  passed,  "#22c55e"),
        ("Failed",  failed,  "#ef4444"),
        ("Skipped", skipped, "#f59e0b"),
        ("Error",   error,   "#a855f7"),
    ]
    max_val = max((v for _, v, _ in bars), default=1) or 1
    chart_h, chart_w = 130, 200
    bar_w = 34
    gap = 16
    base_y = 110

    rects = []
    for i, (label, val, color) in enumerate(bars):
        x = gap + i * (bar_w + gap)
        bar_h = max(4, int(val / max_val * 90)) if val else 0
        y = base_y - bar_h
        rects.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{color}" rx="3"/>'
            f'<text x="{x + bar_w // 2}" y="{y - 4}" text-anchor="middle" fill="#374151" font-size="11">{val}</text>'
            f'<text x="{x + bar_w // 2}" y="{base_y + 14}" text-anchor="middle" fill="#6b7280" font-size="10">{label}</text>'
        )

    inner = "\n  ".join(rects)
    return f"""<svg width="{chart_w}" height="{chart_h + 20}" viewBox="0 0 {chart_w} {chart_h + 20}">
  <line x1="0" y1="{base_y}" x2="{chart_w}" y2="{base_y}" stroke="#e5e7eb" stroke-width="1"/>
  {inner}
</svg>"""


def _test_table_rows(tests: list[dict[str, Any]]) -> str:
    rows = []
    for t in tests:
        status = t.get("status", "error")
        cls, label = _STATUS_BADGE.get(status, ("badge-error", "ERROR"))
        name = _esc(t.get("name", "—"))
        module = _esc(t.get("module", "—"))
        dur = t.get("duration_seconds", 0.0) or 0.0
        recording = _esc(t.get("recording") or "—")
        fail = t.get("failure")
        fail_indicator = ""
        if fail:
            msg = _esc((fail.get("message") or "")[:120])
            fail_indicator = f'<br><span class="fail-hint">{msg}</span>'
        rows.append(
            f'<tr class="row-{status}">'
            f'<td class="test-name">{name}{fail_indicator}</td>'
            f'<td class="test-module">{module}</td>'
            f'<td><span class="badge {cls}">{label}</span></td>'
            f'<td class="dur">{dur:.3f}s</td>'
            f'<td class="recording-col">{recording}</td>'
            f'</tr>'
        )
    return "\n".join(rows)


def _failure_cards(tests: list[dict[str, Any]]) -> str:
    cards = []
    for t in tests:
        if t.get("status") not in ("failed", "error"):
            continue
        fail = t.get("failure") or {}
        name = _esc(t.get("name", "—"))
        msg = _esc(fail.get("message", "No details available"))
        action_ctx = _esc(fail.get("action_context") or "")
        ss_path = fail.get("screenshot_path")
        ss_html = ""
        if ss_path:
            ss_path_esc = _esc(ss_path)
            ss_html = f'<div class="failure-screenshot"><strong>Screenshot:</strong> <a href="{ss_path_esc}" class="ss-link" target="_blank">{ss_path_esc}</a></div>'
        action_html = f'<div class="failure-action"><strong>Action:</strong> {action_ctx}</div>' if action_ctx else ""
        longrepr = _esc(fail.get("longrepr", ""))
        cards.append(f"""
<div class="failure-card">
  <div class="failure-header">
    <span class="badge badge-fail">FAIL</span>
    <span class="failure-name">{name}</span>
  </div>
  <div class="failure-message">{msg}</div>
  {action_html}
  {ss_html}
  <details class="stack-details">
    <summary>Show technical details</summary>
    <pre class="stack-trace">{longrepr}</pre>
  </details>
</div>""")
    return "\n".join(cards)


def _env_rows(env: dict[str, str], exec_id: str, suite: str,
              started: str, finished: str, generated: str) -> str:
    rows_data = [
        ("Execution ID",      exec_id),
        ("Test Suite",        suite),
        ("Started At",        started),
        ("Finished At",       finished),
        ("Report Generated",  generated),
        ("Operating System",  env.get("os", "—")),
        ("Python Version",    env.get("python", "—")),
        ("Pytest Version",    env.get("pytest", "—")),
        ("Framework Version", env.get("framework_version", "—")),
        ("Host",              env.get("hostname", "—")),
    ]
    rows = []
    for label, value in rows_data:
        rows.append(f'<tr><td class="env-key">{_esc(label)}</td><td class="env-val">{_esc(str(value))}</td></tr>')
    return "\n".join(rows)


def _fmt_ts(ts: str) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Inline CSS
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f3f4f6;
  color: #111827;
  font-size: 14px;
  line-height: 1.5;
}

/* HEADER */
.site-header {
  background: #1e293b;
  color: #f1f5f9;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
}
.header-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
}
.header-brand { display: flex; align-items: center; gap: 10px; }
.brand-icon { font-size: 18px; color: #38bdf8; }
.brand-name { font-size: 16px; font-weight: 600; letter-spacing: 0.3px; }
.exec-badge {
  background: #334155;
  border: 1px solid #475569;
  color: #94a3b8;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* MAIN */
.main-content {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px;
}

.section {
  background: #ffffff;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.05);
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f1f5f9;
}

/* SUMMARY CARDS */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 14px;
}
.card {
  border-radius: 8px;
  padding: 16px 18px;
  text-align: center;
  border: 1px solid transparent;
}
.card-value { font-size: 28px; font-weight: 700; line-height: 1.1; }
.card-label { font-size: 12px; color: #6b7280; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }

.card-total { background: #f8fafc; border-color: #e2e8f0; }
.card-total .card-value { color: #334155; }
.card-pass  { background: #f0fdf4; border-color: #bbf7d0; }
.card-pass  .card-value { color: #16a34a; }
.card-fail  { background: #fef2f2; border-color: #fecaca; }
.card-fail  .card-value { color: #dc2626; }
.card-skip  { background: #fffbeb; border-color: #fde68a; }
.card-skip  .card-value { color: #d97706; }
.card-error { background: #faf5ff; border-color: #e9d5ff; }
.card-error .card-value { color: #7c3aed; }
.card-rate  { background: #eff6ff; border-color: #bfdbfe; }
.card-rate  .card-value { color: #1d4ed8; }
.card-dur   { background: #f8fafc; border-color: #e2e8f0; }
.card-dur   .card-value { color: #334155; }

/* CHARTS */
.charts-row {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
  align-items: flex-start;
}
.chart-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 200px;
}
.chart-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.donut-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  font-size: 12px;
  color: #374151;
  margin-top: 10px;
  justify-content: center;
}
.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}

/* TEST TABLE */
.table-wrapper { overflow-x: auto; }
.exec-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.exec-table thead tr {
  background: #f8fafc;
  border-bottom: 2px solid #e2e8f0;
}
.exec-table th {
  padding: 10px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #6b7280;
}
.exec-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: top;
}
.exec-table tbody tr:last-child td { border-bottom: none; }
.exec-table tbody tr:hover td { background: #f8fafc; }
.test-name { font-weight: 500; color: #1e293b; max-width: 380px; }
.test-module { color: #6b7280; font-size: 12px; }
.dur { color: #6b7280; font-family: monospace; white-space: nowrap; }
.recording-col { color: #6b7280; font-size: 12px; }
.fail-hint { color: #dc2626; font-size: 11px; font-weight: 400; }
.empty-row { text-align: center; color: #9ca3af; padding: 24px; }

/* BADGES */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  white-space: nowrap;
}
.badge-pass  { background: #dcfce7; color: #15803d; }
.badge-fail  { background: #fee2e2; color: #b91c1c; }
.badge-skip  { background: #fef9c3; color: #a16207; }
.badge-error { background: #f3e8ff; color: #6d28d9; }

/* FAILURE CARDS */
.failure-card {
  border: 1px solid #fecaca;
  border-left: 4px solid #ef4444;
  border-radius: 6px;
  padding: 16px 18px;
  margin-bottom: 14px;
  background: #fef2f2;
}
.failure-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.failure-name {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
}
.failure-message {
  color: #dc2626;
  font-size: 13px;
  margin-bottom: 8px;
  word-break: break-word;
}
.failure-action {
  font-size: 12px;
  color: #374151;
  margin-bottom: 8px;
  background: #fff7ed;
  padding: 6px 10px;
  border-radius: 4px;
  border: 1px solid #fed7aa;
}
.failure-screenshot {
  font-size: 12px;
  margin-bottom: 8px;
}
.ss-link { color: #2563eb; word-break: break-all; }
.stack-details {
  margin-top: 8px;
}
.stack-details summary {
  font-size: 12px;
  color: #6b7280;
  cursor: pointer;
  user-select: none;
}
.stack-trace {
  margin-top: 8px;
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 4px;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

/* ENVIRONMENT TABLE */
.env-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.env-table tr { border-bottom: 1px solid #f1f5f9; }
.env-table tr:last-child { border-bottom: none; }
.env-key {
  width: 200px;
  padding: 8px 12px;
  font-weight: 600;
  color: #374151;
  white-space: nowrap;
}
.env-val {
  padding: 8px 12px;
  color: #6b7280;
  word-break: break-all;
}

/* FOOTER */
.site-footer {
  text-align: center;
  padding: 16px;
  color: #9ca3af;
  font-size: 12px;
  border-top: 1px solid #e5e7eb;
  margin-top: 8px;
}

/* Responsive */
@media (max-width: 640px) {
  .cards-grid { grid-template-columns: repeat(2, 1fr); }
  .charts-row { flex-direction: column; align-items: center; }
}
"""

# ---------------------------------------------------------------------------
# Inline JS (toggle expand, nothing complex)
# ---------------------------------------------------------------------------

_JS = """
// Nothing required — <details> is native HTML5.
// Reserved for future interactive enhancements.
"""
