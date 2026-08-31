# Desktop Automation POC

A Windows desktop automation framework that records manual interactions and
replays them as automated test executions, complete with action-level HTML
execution reports.

## What it does

1. **Record** — you perform manual steps in any Windows desktop application.
   The tool captures every mouse click, keyboard action, and hotkey.
2. **Save** — the recording is stored as a versioned JSON file in your workspace.
3. **Play back** — the tool replays the recording against the target application.
4. **Report** — a self-contained HTML report is generated for every execution,
   showing each action as PASS or FAIL with timing and failure details.

## Quick start

```
# Activate the virtual environment
.venv\Scripts\activate

# Launch the Desktop Automation Tool
python -m ui.app_shell

# Run all automated tests
python -m pytest tests\smoke --override-ini "addopts=" -q
```

## Current capabilities

| Capability | Status |
|---|---|
| Workspace creation and recent-workspace restore | ✅ |
| Mouse click recording with screen coordinates | ✅ |
| Keyboard TYPE, KEY, HOTKEY recording | ✅ |
| Ctrl+F4 / Alt+F4 as recorded hotkey actions | ✅ |
| Playback via pynput (keyboard) + SendInput (mouse) | ✅ |
| Target application maximize on LAUNCH | ✅ |
| Coordinate scaling when recording/playback resolution differs | ✅ |
| Per-recording HTML execution report | ✅ |
| DA Tool remains open after playback | ✅ |
| Consecutive playback without restarting | ✅ |
| Recorder timeline reset between sessions | ✅ |

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, dependencies, architecture diagram |
| [docs/USER_MANUAL.md](docs/USER_MANUAL.md) | Step-by-step usage guide |
| [docs/DESIGN_FLOWS.md](docs/DESIGN_FLOWS.md) | Recording, playback, reporting, teardown flows |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Recording JSON structure and action schema |
| [docs/ALGORITHMS.md](docs/ALGORITHMS.md) | Key algorithms explained |
| [docs/PLAYBACK_LIFECYCLE.md](docs/PLAYBACK_LIFECYCLE.md) | Lifecycle: setup → execute → teardown → report |
| [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md) | Test approach, suite structure, running tests |
| [docs/STATUS.md](docs/STATUS.md) | Implemented / Partial / Known limitations |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Future enhancement roadmap |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Dev setup, project structure, contribution guide |

## Test suite

```
python -m pytest tests\smoke --override-ini "addopts=" -q
```

Expected: **567 passed, 4 skipped, 0 failed**

## Tech stack

- Python 3.12
- pywinauto (UIA backend) — window/control resolution
- pynput — keyboard delivery (TYPE, KEY, HOTKEY)
- ctypes SendInput — mouse click delivery
- Tkinter — UI framework
- pytest + pytest-html — test runner and legacy report
