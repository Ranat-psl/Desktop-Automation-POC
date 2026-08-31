# Playback Lifecycle — Desktop Automation POC

## Why the lifecycle matters

The Desktop Automation Tool (DA Tool) and the target application it tests
are two separate processes with completely separate lifecycles. If they are
conflated, the following failures can occur:

- DA Tool closes when the target app closes (Alt+F4 applied to wrong window).
- Target app remains open and pollutes the next recording session.
- UI elements from the DA Tool are accidentally clicked during playback.
- Run button stays disabled because cleanup did not complete properly.

The lifecycle below enforces a clean separation at every step.

---

## Lifecycle diagram

```
USER SELECTS RECORDING
        ↓
SETUP
  └── DA Tool minimized (iconified)
  └── New DesktopDriver created
  └── New PlaybackExecutor created
        ↓
PREPARE TARGET APPLICATION
  └── On LAUNCH action: driver.start(executable)
  └── _owns_app_process = True
        ↓
MAXIMIZE TARGET APPLICATION (when possible)
  └── time.sleep(0.5) — wait for window
  └── driver.maximize_window() — graceful if unsupported
        ↓
EXECUTE RECORDING
  └── For each action:
        ├── run_with_retry(_execute(action))
        ├── collect ActionResult (passed/failed)
        ├── on failure: capture screenshot, store result, raise
        └── inter-action sleep
        ↓
COLLECT RESULTS
  └── PlaybackResult (status, action_results, times, durations)
        ↓
GENERATE REPORT (always — pass or fail)
  └── generate_recording_report(result, workspace_name)
  └── writes reports/html/recording_{name}_{ts}.html
        ↓
TEARDOWN (always — in finally block)
  └── driver.quit()
        ├── if _owns_app_process: taskkill target PID
        └── else: log and skip (not owned)
        ↓
RESET UI STATE (back on main thread)
  └── root.deiconify() — restore DA Tool
  └── _update_button_states() — re-enable Run
  └── _last_report_path updated
  └── Status message shown (pass or fail + report name)
        ↓
DA TOOL REMAINS OPEN — READY FOR NEXT RECORDING
```

---

## Guarantees

| Guarantee | How enforced |
|---|---|
| DA Tool always restored | `_on_done()` always calls `root.deiconify()` |
| Run button always re-enabled | `_update_button_states()` called in `_on_done()` for both pass and fail |
| Report always generated | `generate_recording_report()` in `finally` block |
| Driver always cleaned up | `driver.quit()` in `finally` block |
| Target app does not close DA Tool | DA Tool is not managed by the driver; separate Tk root |
| Consecutive playback works | Each run creates fresh `DesktopDriver` and `PlaybackExecutor` |

---

## Alt+F4 / Ctrl+F4 during playback

`Alt+F4` and `Ctrl+F4` are valid recorded `HOTKEY` actions. During playback
they are dispatched to pynput which delivers them to the foreground application
(the target app, since the DA Tool is minimized). The target application responds
to the shortcut naturally (e.g. closes). The DA Tool is unaffected because it is
iconified and not in the foreground.

After the target app closes, the DA lifecycle continues: teardown runs,
the report is generated, and the DA Tool is restored.

---

## Thread model

```
Tkinter main thread
    ├── builds UI
    ├── handles button events
    ├── iconifies/deiconifies root
    └── receives _on_done() callback via self.after(0, ...)

Daemon thread (playback-{recording_name})
    ├── creates DesktopDriver
    ├── runs PlaybackExecutor.run()
    ├── generates HTML report
    └── calls driver.quit()
    └── schedules _on_done() on main thread
```

The daemon thread is never allowed to manipulate Tkinter widgets directly.
All UI updates are posted to the main thread via `self.after(0, callback)`.
