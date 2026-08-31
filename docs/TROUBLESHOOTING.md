# Troubleshooting Guide — Desktop Automation POC

---

## Recording does not start

**Symptom:** Click Start Recording — nothing happens or error shown.

**Check:**
1. Is a workspace selected? The Recording Directory field must show a real path,
   not `(select a workspace first)`.
2. Open the Workspace screen and create or open a workspace first.
3. Is a Recording Name entered? Leave the name blank only if you want an
   auto-generated name (check `RecorderService` defaults).

---

## Actions are not captured

**Symptom:** Recording timeline shows "Recording started." but action count stays 0.

**Check:**
1. Are you clicking inside the DA Tool window? Those clicks are intentionally
   excluded (to prevent recorder buttons from appearing in recordings).
2. Are you using a remote desktop / virtual machine session? pynput global hooks
   may require specific permissions in RDP sessions.
3. Check the Python debug log for EventListener errors.

---

## Target application does not maximize

**Symptom:** After a LAUNCH action the app opens but is not maximized.

**Cause:** Some applications do not support the `maximize()` UIA method.

**Behavior:** `maximize_window()` fails gracefully — playback continues.
The window opens at its default size. This is expected and not an error.

---

## Click executes at the wrong location

**Symptom:** During playback a click lands in the wrong place.

**Causes and fixes:**

| Cause | Fix |
|---|---|
| Recording and playback screen resolutions differ | Coordinate scaling is applied automatically when `screen_width/screen_height` is stored in the action metadata. If it is a legacy recording (flat-list format), re-record on the playback machine. |
| Window is in a different position than at record time | Use element-based locators (auto_id). If the locator is `null` or `control_type=Pane`, the click is entirely coordinate-based. |
| Multi-monitor with different DPI per monitor | Known limitation. See [STATUS.md](STATUS.md). Re-record on the same monitor. |

---

## Application does not close after playback

**Symptom:** Target app is still running after playback completes.

**Causes:**

1. **App was opened via keyboard** (e.g. cmd+r → notepad): the framework does
   not own this process. Add an `alt+f4` or `ctrl+f4` hotkey as the last action
   in the recording.

2. **App was launched via LAUNCH action but did not close**: the framework will
   attempt `taskkill /PID` in the finally block. If the app ignores SIGTERM/force-kill,
   close it manually.

---

## Playback fails

**Symptom:** Status bar shows "Playback failed: ...".

**Steps:**
1. Open the HTML report (shown in the status bar).
2. Find the red FAIL row in the action table.
3. Read the error message and screenshot path.
4. Common causes: target window not found, control not visible, timing issue.
5. Increase `inter_action_delay_seconds` if timing is the issue (edit executor
   call in `workspace_ui.py`).

---

## Report is not generated

**Symptom:** Playback completes but no HTML report filename appears in status bar.

**Check:**
1. Is the `reports/html/` directory writable?
2. Check the Python debug log for `Could not generate recording report:` messages.
3. Was `executor.result` populated? Check that the executor completed its run
   method (even for failures, `self.result` is set before the raise).

---

## Run button remains disabled

**Symptom:** After playback the Run button is grayed out.

**Cause:** `_on_done()` was not called or raised an exception before
`_update_button_states()`.

**Fix:** This should not happen under normal conditions. If it occurs:
- Check the debug log for exceptions in `_on_done`.
- Restart the DA Tool (the workspace will be restored from recent workspace).

---

## Workspace is not restored on startup

**Symptom:** Tool opens with "No workspace selected" even though it was
previously used.

**Check:**
1. Does `~/.da-poc/recent_workspace.json` exist?
2. Does the path stored in it still exist on disk?
3. `load_recent()` returns `None` if the path no longer exists (e.g. moved folder).
4. Open the workspace manually to re-register it.

---

## Recording timeline contains stale entries

**Symptom:** After stopping and starting a new recording, old "Recording started."
or "Saved recording:" entries appear.

**Status:** This was a known bug — **fixed in the lifecycle phase**.

The timeline (`_events_list`) is now cleared (`delete(0, END)`) each time a new
recording transitions to `RECORDING` state. If you are still seeing stale entries,
ensure you are running the latest version of `ui/recorder_ui.py`.

---

## DA Tool closes when Alt+F4 is played back

**Symptom:** Alt+F4 in a recording closes the DA Tool instead of the target app.

**Cause:** DA Tool was in the foreground during playback (not minimized).

**Fix:** This should not happen — the DA Tool is iconified before playback starts
in `_run_recording_async()`. If it does happen, check that `root.iconify()` is
called before the daemon thread starts.
