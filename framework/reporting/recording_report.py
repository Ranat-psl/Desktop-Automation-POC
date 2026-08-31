"""Per-recording HTML execution report generator.

Produces a self-contained, offline HTML report for a single recording playback.
Every execution generates a uniquely-named file:
    reports/html/recording_{name}_{YYYYMMDD_HHmmss}_{short_id}.html

The report contains:
  A. Execution Summary     — recording name, status, times, duration, counts
  B. Action-level Results  — each action, type, value, status, duration
  C. Failure Information   — failed action details, error message, screenshot
  D. Environment / Info    — timestamp, workspace info

Usage::

    from framework.reporting.recording_report import generate_recording_report
    from framework.playback.executor import PlaybackResult

    report_path = generate_recording_report(result, workspace_name="MyWorkspace")
"""
from __future__ import annotations

import html as html_lib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

_log = logging.getLogger(__name__)

_HTML_DIR = Path("reports/html")


def generate_recording_report(
    result,  # PlaybackResult — import avoided to prevent circular dep
    workspace_name: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Generate an HTML report for a single recording playback.

    Parameters
    ----------
    result:
        A ``PlaybackResult`` instance (from ``PlaybackExecutor.run()``).
    workspace_name:
        Optional workspace label shown in the report header.
    output_dir:
        Directory to write the HTML file.  Defaults to ``reports/html/``.

    Returns
    -------
    Path
        Absolute path of the generated HTML file.
    """
    out_dir = Path(output_dir) if output_dir else _HTML_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = result.started_at.strftime("%Y%m%d_%H%M%S")
    short_id = result.started_at.strftime("%f")[:6]
    safe_name = _safe_filename(result.recording_name or "recording")
    filename = f"recording_{safe_name}_{ts}_{short_id}.html"
    out_path = out_dir / filename

    html_content = _render(result, workspace_name)
    out_path.write_text(html_content, encoding="utf-8")
    _log.info("Recording report written: %s", out_path)
    return out_path.resolve()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _safe_filename(name: str) -> str:
    """Strip characters unsafe in filenames."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:50]


def _h(text: str) -> str:
    """HTML-escape a string."""
    return html_lib.escape(str(text) if text is not None else "")


def _fmt_ts(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _render(result, workspace_name: str | None) -> str:
    rec_name = result.recording_name or "Unknown Recording"
    status = result.status  # "passed" | "failed"
    started = _fmt_ts(result.started_at)
    finished = _fmt_ts(result.finished_at)
    duration = f"{result.duration_seconds:.2f}s"
    actions = result.action_results
    total = len(actions)
    passed = sum(1 for a in actions if a.status == "passed")
    failed = sum(1 for a in actions if a.status == "failed")

    status_color = "#22c55e" if status == "passed" else "#ef4444"
    status_label = "PASS" if status == "passed" else "FAIL"

    action_rows = _action_rows(actions)
    failure_section = _failure_section(actions)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ws_info = f"<tr><td>Workspace</td><td>{_h(workspace_name)}</td></tr>" if workspace_name else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Recording Report — {_h(rec_name)}</title>
<style>
{_CSS}
</style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <span class="brand-icon">&#9654;</span>
    <span class="brand-name">Desktop Automation POC — Recording Report</span>
  </div>
</header>

<main>

  <!-- SUMMARY -->
  <section class="section">
    <h2 class="section-title">Execution Summary</h2>
    <div class="summary-grid">
      <div class="summary-card">
        <div class="card-label">Recording</div>
        <div class="card-value" style="font-size:1rem">{_h(rec_name)}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">Status</div>
        <div class="card-value" style="color:{status_color};font-size:1.5rem;font-weight:700">{status_label}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">Duration</div>
        <div class="card-value">{duration}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">Total Actions</div>
        <div class="card-value">{total}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">Passed</div>
        <div class="card-value" style="color:#22c55e">{passed}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">Failed</div>
        <div class="card-value" style="color:#ef4444">{failed}</div>
      </div>
    </div>
    <table class="info-table" style="margin-top:1rem">
      <tr><td>Start Time</td><td>{started}</td></tr>
      <tr><td>End Time</td><td>{finished}</td></tr>
      {ws_info}
      <tr><td>Report Generated</td><td>{generated}</td></tr>
    </table>
  </section>

  <!-- ACTION TABLE -->
  <section class="section">
    <h2 class="section-title">Action-Level Results</h2>
    <table class="action-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Action</th>
          <th>Value / Locator</th>
          <th>Status</th>
          <th>Duration</th>
        </tr>
      </thead>
      <tbody>
        {action_rows if action_rows else '<tr><td colspan="5" class="empty">No actions recorded.</td></tr>'}
      </tbody>
    </table>
  </section>

  {failure_section}

</main>
</body>
</html>"""


def _action_rows(actions: list) -> str:
    rows = []
    for a in actions:
        num = a.action_index + 1
        atype = _h(a.action_type.upper())
        value_parts = []
        if a.value:
            value_parts.append(_h(a.value[:80]))
        if a.locator_str:
            value_parts.append(f'<span class="locator">{_h(a.locator_str)}</span>')
        value_cell = " | ".join(value_parts) if value_parts else "—"
        if a.status == "passed":
            badge = '<span class="badge-pass">PASS</span>'
        else:
            badge = '<span class="badge-fail">FAIL</span>'
        dur = f"{a.duration_seconds:.3f}s"
        rows.append(
            f"<tr>"
            f"<td>{num}</td>"
            f"<td><code>{atype}</code></td>"
            f"<td>{value_cell}</td>"
            f"<td>{badge}</td>"
            f"<td>{dur}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _failure_section(actions: list) -> str:
    failures = [a for a in actions if a.status == "failed"]
    if not failures:
        return ""

    cards = []
    for a in failures:
        num = a.action_index + 1
        atype = _h(a.action_type.upper())
        err = _h(a.error_message or "Unknown error")
        ss = ""
        if a.screenshot_path:
            ss = f'<p><strong>Screenshot:</strong> <code>{_h(a.screenshot_path)}</code></p>'
        cards.append(f"""
        <div class="failure-card">
          <div class="failure-title">&#10005; Action {num} — {atype} FAILED</div>
          <p class="failure-error">{err}</p>
          {ss}
        </div>""")

    return f"""
  <section class="section">
    <h2 class="section-title" style="color:#ef4444">Failure Details</h2>
    {"".join(cards)}
  </section>"""


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f4f6f8; color: #22313f; }
.site-header { background: #0d2b45; color: #fff; padding: 14px 24px; display: flex; align-items: center; gap: 10px; }
.brand-icon { font-size: 1.2rem; }
.brand-name { font-size: 1rem; font-weight: 600; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
.section { background: #fff; border: 1px solid #d7dde3; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
.section-title { font-size: 1rem; font-weight: 700; color: #1e3246; margin-bottom: 14px; border-bottom: 1px solid #e8ecf0; padding-bottom: 8px; }
.summary-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.summary-card { background: #f8fafc; border: 1px solid #d7dde3; border-radius: 6px; padding: 12px 18px; min-width: 130px; }
.card-label { font-size: 0.75rem; color: #6b7785; text-transform: uppercase; margin-bottom: 4px; }
.card-value { font-size: 1.25rem; font-weight: 700; color: #22313f; }
.info-table { border-collapse: collapse; width: 100%; max-width: 600px; font-size: 0.875rem; }
.info-table td { padding: 6px 12px; border-bottom: 1px solid #f0f3f5; }
.info-table td:first-child { color: #6b7785; font-weight: 600; width: 160px; }
.action-table { border-collapse: collapse; width: 100%; font-size: 0.875rem; }
.action-table th { background: #f4f6f8; text-align: left; padding: 8px 12px; border-bottom: 2px solid #d7dde3; font-weight: 600; color: #1e3246; }
.action-table td { padding: 8px 12px; border-bottom: 1px solid #f0f3f5; vertical-align: top; }
.action-table tr:hover td { background: #fafbfc; }
.badge-pass { background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }
.badge-fail { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }
.locator { font-size: 0.8rem; color: #5b6670; }
.empty { text-align: center; color: #9fb4c8; padding: 20px; }
code { font-family: 'Consolas', 'Cascadia Code', monospace; font-size: 0.875em; background: #f4f6f8; padding: 1px 4px; border-radius: 3px; }
.failure-card { background: #fff5f5; border: 1px solid #fecaca; border-radius: 6px; padding: 16px; margin-bottom: 12px; }
.failure-title { font-weight: 700; color: #991b1b; margin-bottom: 8px; }
.failure-error { font-family: 'Consolas', monospace; font-size: 0.85rem; color: #7f1d1d; background: #fee2e2; padding: 8px 12px; border-radius: 4px; word-break: break-word; }
"""
