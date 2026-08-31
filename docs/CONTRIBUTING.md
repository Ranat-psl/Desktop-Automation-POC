# Contributing / Development Guide — Desktop Automation POC

---

## Prerequisites

- Windows 10 or 11 (required for pywinauto UIA backend and ctypes SendInput)
- Python 3.12
- Git

---

## Environment setup

```
# Clone the repository
git clone <repo-url>
cd Desktop-Automation-POC

# Create virtual environment
python -m venv .venv

# Activate
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Project structure

```
Desktop-Automation-POC/
├── framework/
│   ├── ai/              # Extension point stubs (AI/planner integration)
│   ├── assertions/      # assert_exists, assert_text_equals helpers
│   ├── codegen/         # Code generation stubs
│   ├── core/            # models.py (Action, ActionType, Locator), exceptions.py
│   ├── driver/          # DesktopDriver, PyWinAutoAdapter, KeyboardEngine, screen_info
│   ├── playback/        # PlaybackExecutor, RetryPolicy, Synchronizer
│   ├── recorder/        # EventListener, ActionNormalizer, RecorderService, RecordingStore
│   ├── reporting/       # recording_report.py, screenshot.py, dashboard.py (stub)
│   ├── safety/          # ApprovalGate, policy
│   └── workspace/       # WorkspaceService, models, recent_workspace
├── ui/
│   ├── app_shell.py     # Main Tkinter application window + navigation
│   ├── recorder_ui.py   # Recorder screen
│   └── workspace_ui.py  # Workspace + playback screen
├── tests/
│   └── smoke/           # All automated tests
├── recordings/          # Saved recording JSON files
├── reports/
│   ├── html/            # Per-recording HTML reports
│   └── data/            # Execution data JSON files
├── docs/                # Project documentation
├── config/              # framework_config.yaml
├── conftest.py
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Running the application

```
python -m ui.app_shell
```

---

## Running focused tests

```
# Single test file
python -m pytest tests\smoke\test_click_reliability.py -v --no-header --tb=short

# Single test class
python -m pytest tests\smoke\test_click_reliability.py::TestScaleCoords -v

# Single test
python -m pytest "tests\smoke\test_click_reliability.py::TestScaleCoords::test_scale_up_doubles_resolution" -v
```

---

## Running the full regression suite

```
python -m pytest tests\smoke --override-ini "addopts=" -q --no-header --tb=line
```

Expected baseline: **567 passed, 4 skipped, 0 failed**

---

## Coding conventions

| Convention | Rule |
|---|---|
| Imports | `from __future__ import annotations` at top of every module |
| Logging | `_log = logging.getLogger(__name__)` per module; use `_log.debug/info/warning` |
| External calls | All pywinauto, ctypes, pynput calls go inside `PyWinAutoAdapter` or `KeyboardEngine` — never directly in the executor or UI |
| Graceful degradation | Any non-critical external call (maximize, screenshot, report) must be wrapped in `try/except` and log on failure |
| Tests | All tests must run without a real Windows application. Mock `ctypes`, `pywinauto`, `pynput` at the module boundary |
| No `time.sleep` in tests | Use `patch("time.sleep")` |
| No hardcoded paths | Use `tmp_path` pytest fixture for file I/O tests |

---

## Adding a new action type

1. Add the value to `ActionType` enum in `framework/core/models.py`.
2. Add a handler branch in `PlaybackExecutor._execute()`.
3. Add normalization logic in `ActionNormalizer` if it needs to be recorded.
4. Add tests in `tests/smoke/`.
5. Update `docs/DATA_MODEL.md` with the new action schema.

---

## Change validation expectations

Before merging any change:

1. Run `python -m pytest tests\smoke --override-ini "addopts=" -q`.
2. Result must be ≥ current baseline passed count, 0 failed.
3. Any new functionality must have unit tests.
4. Any changed behavior that invalidates an existing test must be explained
   before the test is updated.
5. Documentation in `docs/` must be updated for any user-visible change.

---

## Branch strategy

- `main` — stable, validated, documented.
- Feature branches — one phase at a time.
- Never force-push to `main`.

---

## Do NOT

- Commit `.venv/`, `__pycache__/`, `*.pyc`, `reports/html/*.html`.
- Commit machine-specific paths.
- Commit secrets or credentials.
- Skip the regression suite before marking a phase complete.
