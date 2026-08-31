# Future Enhancement Roadmap — Desktop Automation POC

This roadmap lists planned enhancements in logical development phases.
**None of the items below are currently implemented.**
Each phase builds on the previous one.

---

## Phase 1 — Recorder reliability (current focus: partly done)

**Objective:** Make recording output stable and deterministic.

**Business value:** Reduces noise recordings. Reduces manual cleanup of
recorded files. Higher-quality input → higher-quality automation.

**Technical direction:**
- Handle rapid double-click → record as single CLICK at that location.
- Debounce high-frequency mouse events.
- Improve locator quality for WinUI3 apps using UIA3 automation IDs.
- Capture window title at the time of each click for better context.

**Dependencies:** Existing EventListener + ActionNormalizer.

---

## Phase 2 — Mouse/click reliability (partly done in current phase)

**Objective:** Make click playback reliable across resolutions, DPIs, and time.

**Business value:** Recordings made once work on different machines without manual
coordinate adjustment.

**Technical direction:**
- Per-monitor DPI scaling using `GetDpiForMonitor` Win API.
- Store DPI scale factor in CLICK metadata.
- Element-based fallback when coordinates are stale (use stored locator if
  SendInput click misses).
- Store bounding rect alongside coordinates for validation.

**Dependencies:** Phase 1 locator quality; screen_info.py.

---

## Phase 3 — Window and control identification

**Objective:** Reliable identification of target windows and controls by
accessible identity rather than screen position.

**Business value:** Recordings remain valid after minor UI layout changes.
Click on "OK button in Save dialog" works even if the button moved 5 pixels.

**Technical direction:**
- Prefer `auto_id` → `name` → `control_type` → coords (current ordering is correct;
  needs reliability improvement for apps where auto_id changes between sessions).
- Store window title + process name alongside click locators.
- Implement `find_control_by_path()` for hierarchical locator resolution.

**Dependencies:** Phase 2; pywinauto UIA tree.

---

## Phase 4 — Element-based automation

**Objective:** Replace coordinate-based playback with element-based interaction
where possible.

**Business value:** More robust automation that does not break on resolution
changes, window moves, or minor UI updates.

**Technical direction:**
- `CLICK(locator=Locator(by="auto_id", value="OKButton"))` without any coords.
- `focus_window()` → `find_control()` → `invoke_or_click()`.
- Graceful fallback to coords if element not found.

**Dependencies:** Phase 3.

---

## Phase 5 — Advanced synchronization / waits

**Objective:** Replace hard-coded sleeps between actions with intelligent waits.

**Business value:** Faster, more reliable playback. Actions execute as soon as
the target is ready rather than after a fixed delay.

**Technical direction:**
- `WAIT_FOR_WINDOW(title_re="…", timeout=10)` action type.
- `WAIT_FOR_ELEMENT(locator, timeout)` action type.
- Replace `inter_action_delay_seconds` with configurable per-action waits.
- Integrate `synchronizer.wait_until()` into the executor.

**Dependencies:** Phase 4 element resolution.

---

## Phase 6 — Test case management

**Objective:** Organise recordings into suites with shared setup/teardown.

**Business value:** Run a collection of related recordings as a single test
suite. Shared fixtures (open browser, log in) are extracted once.

**Technical direction:**
- Suite JSON format referencing multiple recording files.
- Shared setup/teardown recordings.
- Suite-level HTML report aggregating per-recording results.

**Dependencies:** Phase 5.

---

## Phase 7 — Code generation

**Objective:** Convert recordings to maintainable Python/pytest test scripts.

**Business value:** QA engineers can version-control tests as code, review diffs,
and edit them like regular test code rather than binary recordings.

**Technical direction:**
- `framework/codegen/pytest_generator.py` already exists as a stub.
- Generate one `test_*.py` file per recording.
- Generated tests use the DesktopDriver API directly.

**Dependencies:** Stable recording format (Phase 1/2).

---

## Phase 8 — Advanced reporting

**Objective:** Richer execution reports and trend tracking.

**Business value:** Stakeholders can see pass-rate trends over time. Failed
actions include annotated screenshots (highlight of the target area).

**Technical direction:**
- Annotated screenshot with bounding box around the failed control.
- Historical execution database (SQLite).
- Trend dashboard (pass rate by recording, by date).
- Extend `framework/reporting/dashboard.py` (currently a stub).

**Dependencies:** Phases 6–7.

---

## Phase 9 — CI/CD integration

**Objective:** Run recordings as part of a continuous integration pipeline.

**Business value:** Automated regression runs on every code change. Failures
surfaced immediately rather than discovered manually.

**Technical direction:**
- Headless-safe playback mode (virtual display / remote desktop session).
- Exit code conventions for CI (0 = pass, 1 = fail).
- JUnit XML output for CI test result ingestion.
- Docker / GitHub Actions / Azure DevOps pipeline examples.

**Dependencies:** Phases 7–8.

---

## Phase 10 — Enterprise scalability and extensibility

**Objective:** Multi-machine execution, plugin architecture, and enterprise
reporting.

**Business value:** Run recordings on a grid of machines. Custom action types
added without modifying core framework.

**Technical direction:**
- Action plugin system (register custom ActionType handlers).
- Remote execution agent.
- Centralised result store (REST API or database).
- Role-based access control for sensitive recordings.

**Dependencies:** All previous phases.
