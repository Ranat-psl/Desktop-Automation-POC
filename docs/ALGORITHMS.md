# Key Algorithms — Desktop Automation POC

---

## 1. Action normalization (keyboard buffering)

**What:** Converts a stream of raw key-press/release events into framework
`Action` objects. Consecutive printable characters are batched into a single
`TYPE` action rather than one action per character.

**Why:** Automation recordings must be human-readable. One `TYPE("Hello")` is
more maintainable than five individual key actions. It also reduces playback
latency and report noise.

**How:**
- A `_text_buffer` accumulates printable characters.
- When a non-printable key, click, or modifier is seen, `_flush_text_buffer()`
  emits a `TYPE` action and clears the buffer.
- Modifier keys (`ctrl`, `alt`, `shift`, `cmd`) are tracked in `_held_modifiers`.
  When a non-modifier key is pressed while a modifier is held, a `HOTKEY` action
  is emitted immediately (no buffering).
- Standalone special keys (enter, backspace, F-keys, arrows) are emitted as `KEY`
  actions, always flushing the text buffer first.

---

## 2. Hotkey normalization

**What:** Builds a canonical hotkey string from a set of held modifiers and a
trigger key, e.g. `"ctrl+shift+s"`, `"alt+f4"`, `"cmd+r"`.

**Why:** Consistency in recording and playback. The same combination must always
produce the same string regardless of which physical modifier key was pressed
(left vs. right ctrl, etc.).

**How:**
```
held = {"ctrl", "shift"}  +  key = "s"
→ apply _MODIFIER_ORDER = (ctrl, alt, shift, cmd)
→ parts = ["ctrl", "shift", "s"]
→ value = "ctrl+shift+s"
```
`_MODIFIER_CANONICAL` maps physical key names (ctrl_l, ctrl_r) to canonical
forms (ctrl).

---

## 3. Click coordinate recording with screen resolution

**What:** Every CLICK action stores `recorded_x`, `recorded_y` AND
`screen_width`, `screen_height` in its metadata.

**Why:** Coordinates are absolute screen pixels. On a different resolution
monitor the same pixel coordinates point to a different location. Recording
the screen size at capture time enables correct scaling at playback.

**How:**
```python
screen_w, screen_h = get_screen_size()   # ctypes GetSystemMetrics
action.metadata = {
    "recorded_x": x, "recorded_y": y,
    "screen_width": screen_w, "screen_height": screen_h,
}
```

---

## 4. Coordinate scaling at playback

**What:** Before firing a click, the recorded `(x, y)` are scaled to the
current screen resolution.

**Why:** If the recording was made at 1920×1080 and playback runs at 3840×2160,
a click at (960, 540) should land at (1920, 1080) — the same proportional position.

**How:**
```python
def scale_coords(x, y, recorded_w, recorded_h):
    current_w, current_h = get_screen_size()
    if recorded_w <= 0 or recorded_h <= 0:
        return (x, y)   # legacy recording — no data
    if current_w <= 0 or current_h <= 0:
        return (x, y)   # can't query screen
    return (round(x * current_w / recorded_w),
            round(y * current_h / recorded_h))
```
If scaling is impossible (missing data), original coordinates are used unchanged.

---

## 5. Playback sequencing and result collection

**What:** Executes a list of `Action` objects in order, collecting a result
for each one.

**Why:** All-or-nothing execution is not useful for debugging. Per-action
results allow the HTML report to show exactly which step failed.

**How:**
```
for i, action in enumerate(actions):
    start = time.monotonic()
    try:
        run_with_retry(lambda: _execute(action), attempts=2, delay=0.5)
        append ActionResult(status="passed", …)
    except:
        capture_screenshot()
        append ActionResult(status="failed", error=…, screenshot=…)
        self.result = PlaybackResult(status="failed", …)
        raise PlaybackExecutionError
    sleep(inter_action_delay)
```

---

## 6. Failure handling

**What:** On action failure, captures a screenshot, records a rich error
message, stores the `PlaybackResult` with `status="failed"`, then re-raises
`PlaybackExecutionError` to stop the sequence.

**Why:** The `finally` block in `_worker()` must always have a `result` to
generate the HTML report, even for partial/failed executions.

**How:**
- `_try_capture_screenshot()` calls `capture_failure_screenshot()` — wraps
  `ImageGrab` or equivalent. Failure here is logged and swallowed.
- `_build_error_message()` includes action index, type, locator, recording
  name, reason, and screenshot path.
- `self.result` is set before the raise so the `finally` block can always
  generate a report.

---

## 7. Target application cleanup / teardown

**What:** After playback (pass or fail), `driver.quit()` terminates the
application process if the framework started it.

**Why:** A leftover target application would interfere with the next
recording session (wrong foreground window, residual state).

**How:**
```python
# In _worker() finally block:
driver.quit()
# In PyWinAutoAdapter.quit():
if not _owns_app_process:
    return   # external process — don't kill
taskkill /PID <pid> /F /T
taskkill /PID <window_pid> /F /T   # Win11 host-process case
```

Apps opened via keyboard (cmd+r → notepad) have `_owns_app_process=False`;
their teardown must be part of the recording (alt+f4 action).

---

## 8. Workspace persistence / recent workspace

**What:** Saves the path of the most-recently-used workspace to disk.
Restores it automatically on next launch.

**Why:** QA engineers typically work in the same workspace across sessions.
Having to re-browse on every startup is a poor UX.

**How:**
```
save_recent(path):
    ~/.da-poc/recent_workspace.json  ←  {"path": str(path)}

load_recent():
    read ~/.da-poc/recent_workspace.json
    if path exists on disk → return Path(path)
    else → return None
```
All I/O errors are silently swallowed so a corrupt file never prevents startup.

---

## 9. HTML report generation

**What:** Produces a self-contained offline HTML file for one playback execution.

**Why:** Stakeholders and QA leads need a shareable, human-readable artifact.
The file has no external dependencies (inline CSS, no CDN) so it works offline.

**How:**
```
filename = recording_{safe_name}_{YYYYMMDD_HHmmss}_{microseconds}.html
```
Renders three sections:
1. **Summary** — name, workspace, PASS/FAIL badge, counts, timestamps.
2. **Action table** — one row per action: index, type, value/locator, badge, duration.
3. **Failure details** — present only when status=failed: error message, screenshot path.

Each execution produces a uniquely-named file. Reports are never overwritten.
