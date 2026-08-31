# Test Strategy — Desktop Automation POC

## Principles

- All automated tests are pure unit / integration tests that run without a real
  Windows desktop application being launched.
- External OS calls (ctypes, pywinauto, pynput listeners) are mocked.
- Tests must pass in a headless or CI-like environment.
- No test may weaken a genuine assertion to make it pass.
- Failing tests are investigated before modifying them.

---

## Test structure

```
tests/
  smoke/
    test_click_reliability.py     ← click/mouse, coord scaling, mixed scenario
    test_playback_lifecycle.py    ← recorder timeline reset, maximize, state reset
    test_playback_integration.py  ← end-to-end executor + adapter chain
    test_keyboard_engine_capabilities.py  ← 117 unit tests for KeyboardEngine
    test_recorder_day6.py         ← action normalizer, event listener, hotkeys
    test_recorder_keyboard.py     ← keyboard recording scenarios
    test_recorder_ui_day7.py      ← RecorderService lifecycle
    test_workspace_management_ui_phase1.py  ← WorkspaceManagementUI widget tests
    test_workspace_day8.py        ← workspace service and persistence
    test_reporting_dashboard.py   ← HTML report content
    test_framework_smoke.py       ← basic imports and module structure
    ... (additional unit/integration tests)
```

---

## Test categories

### Unit tests
Test a single function or class in isolation with all dependencies mocked.

Examples:
- `TestScaleCoords` — verifies `scale_coords()` math for all edge cases.
- `TestKeyboardEngineHotkey` — verifies pynput key press/release ordering.
- `TestActionNormalizer` — verifies text buffering, modifier tracking, hotkey building.

### Integration tests
Test multiple components working together, with only OS-level calls mocked.

Examples:
- `TestMixedKeyboardMousePlayback` — LAUNCH + CLICK + TYPE + KEY + HOTKEY sequence.
- `TestAdapterClickWithCoords` — full adapter → sendinput path.
- `TestPlaybackResultIsolation` — two separate executions produce separate reports.

### UI / widget tests
Test Tkinter widgets in a headed environment. Skipped automatically when
no display is available.

Examples:
- `TestRecorderUITimelineReset` — verify timeline cleared on new recording session.
- `TestPlaybackStateReset` — verify Run button re-enabled after execution.
- `TestWorkspaceManagementUIConstructionAndBrowse` — initial state assertions.

### Recorder tests
Test the recording pipeline from raw events to persisted JSON.

Examples:
- `TestRecordingStoreEnvelope` — new envelope format + legacy backward compat.
- `TestNormalizerClickMetadata` — screen dims stored in CLICK metadata.

### Report tests
Test HTML report content and uniqueness.

Examples:
- `TestHTMLReportClickActions` — CLICK actions render correctly in report.
- `TestPlaybackResultIsolation.test_html_reports_use_distinct_filenames` — no overwrite.

---

## Running tests

### Focused test file
```
python -m pytest tests\smoke\test_click_reliability.py -v --no-header --tb=short
```

### Full regression suite
```
python -m pytest tests\smoke --override-ini "addopts=" -q --no-header --tb=line
```

### Expected results (current baseline)
- **567 passed**
- **4 skipped** (Tkinter display unavailable in some terminal sessions)
- **0 failed**
- **2 warnings** (pre-existing Tkinter main-thread warnings from test thread setup)

---

## Failure scenarios tested

| Scenario | Test location |
|---|---|
| CLICK fails → FAILED result + error message | `test_click_reliability.py::TestClickFailureHandling` |
| CLICK fails → `self.result` populated for report | same |
| LAUNCH maximize fails → playback continues | `test_playback_lifecycle.py::TestExecutorLaunchMaximize` |
| No coords + no locator → PlaybackExecutionError | `test_click_reliability.py::TestExecutorClickScaling` |
| Recorder timeline stale across sessions | `test_playback_lifecycle.py::TestRecorderUITimelineReset` |
| Run button stuck disabled | `test_playback_lifecycle.py::TestPlaybackStateReset` |
| Scale coords with zero recorded resolution | `test_click_reliability.py::TestScaleCoords` |
| Legacy flat-list JSON still loads | `test_click_reliability.py::TestRecordingStoreEnvelope` |

---

## Manual validation

See [USER_MANUAL.md](USER_MANUAL.md) for the full manual acceptance test sequence.

Key manual checks:
1. Record A → stop → start B → verify timeline is clean (no stale A messages).
2. Run recording → verify DA Tool minimizes → completes → DA Tool restores.
3. Run recording A → run recording B (same session) → both succeed.
4. Record and play Ctrl+F4 → target app closes → DA Tool remains open.
5. Open HTML report → verify action table, PASS/FAIL, durations.
6. Restart tool → verify most-recently-used workspace is restored.
