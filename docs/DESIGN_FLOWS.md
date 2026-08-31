# Design Flows — Desktop Automation POC

---

## A. Workspace creation / open flow

```
User enters name + path
      ↓
WorkspaceManagementUI._on_create_workspace()
      ↓
WorkspaceService.create(name, path)
      ↓
Creates directory structure (recordings/, reports/)
      ↓
save_recent(path)  →  ~/.da-poc/recent_workspace.json
      ↓
UI updates: name label, path label, recording list refreshed
```

---

## B. Workspace persistence / restore flow

```
AppShell starts
      ↓
WorkspaceManagementUI.__init__()
      ↓
load_recent()  →  reads ~/.da-poc/recent_workspace.json
      ↓
If path exists on disk:
      ↓
WorkspaceService.load(path)
      ↓
UI fields populated with saved name / path
Recording list populated
Status: "Workspace restored: <path>"
```

---

## C. Recording flow

```
User clicks Start Recording
      ↓
RecorderUI._on_start()
      ↓
Thread: _start_recording(name, directory)
      ↓
RecorderService.start(name, recordings_dir, excluded_rect)
      ↓
EventListener.start()
  ├── mouse.Listener  (pynput global hook)
  └── keyboard.Listener  (pynput global hook)
      ↓
Events → EventListener._handle_click / _handle_key_press / _handle_key_release
      ↓
EventListener._on_event(raw_event_dict)
      ↓
RecorderService receives callback → ActionNormalizer.push(raw_event)
```

---

## D. Recording save flow

```
User clicks Stop Recording
      ↓
RecorderUI._on_stop()
      ↓
Thread: _stop_recording()
      ↓
RecorderService.stop()
  └── EventListener.stop()
      ↓
ActionNormalizer.flush()  →  list[Action]
      ↓
RecordingStore.save(name, actions)
  ├── get_screen_size()  →  records screen resolution in meta
  └── writes JSON envelope:
        { "meta": { version, screen_width, screen_height },
          "actions": [ { action_type, locator, value, metadata }, … ] }
      ↓
RecorderStatus(state=STOPPED, saved_path=Path, action_count=N)
      ↓
RecorderUI timeline shows: "Saved recording: <path>", "Captured actions: N"
```

---

## E. Playback flow

```
User selects recording → clicks Run Selected
      ↓
WorkspaceManagementUI._run_recording_async(item, actions)
      ↓
root.iconify()  — minimize DA tool
      ↓
Daemon thread: _worker()
  ├── DesktopDriver()
  ├── PlaybackExecutor(driver, recording_name)
  ├── executor.run(actions)
  │     └── for each action:
  │           run_with_retry(lambda: _execute(action))
  │           append ActionResult (passed/failed)
  │           sleep(inter_action_delay)
  └── generate_recording_report(executor.result)
      ↓
_on_done(exc, report_path)  — back on main thread
  ├── root.deiconify()  — restore DA tool
  ├── _update_button_states()  — re-enable Run button
  └── status message shown
```

---

## F. Target application preparation flow

```
PlaybackExecutor._execute(LAUNCH action)
      ↓
driver.start(executable_path)
  └── adapter._app = Application.start(executable_path)
      _owns_app_process = True
      ↓
time.sleep(0.5)  — wait for window to appear
      ↓
driver.maximize_window()
  └── adapter._window.maximize()  (fails gracefully if not supported)
```

---

## G. Target application maximize flow

```
DesktopDriver.maximize_window()
      ↓
PyWinAutoAdapter.maximize_window()
      ↓
if self._window is None:
    log and return  (no window focused yet)
else:
    try: self._window.maximize()
    except: log and return  (graceful failure)
```

---

## H. Target application teardown flow

```
PlaybackExecutor.run() completes (pass or fail)
      ↓
_worker() finally block:
      ↓
driver.quit()
  └── PyWinAutoAdapter.quit()
        if _owns_app_process:
            taskkill /PID <pid> /F /T
            taskkill /PID <window_pid> /F /T   (if different)
        else:
            log and skip  (external process — not killed)
```

Apps opened via keyboard hotkeys (cmd+r → type notepad → enter) are NOT
owned by the framework. Their cleanup depends on the recording containing
an explicit `alt+f4` or `ctrl+f4` action.

---

## I. Playback failure cleanup flow

```
PlaybackExecutor._execute(action) raises
      ↓
capture_failure_screenshot(output_dir, prefix)
      ↓
ActionResult(status="failed", error_message=…, screenshot_path=…) appended
      ↓
self.result = PlaybackResult(status="failed", …)
      ↓
raise PlaybackExecutionError(err_msg)
      ↓
_worker() outer except: exc_holder[0] = exc
      ↓
finally: driver.quit()
         generate_recording_report(executor.result)  → FAIL report
         self.after(0, _on_done(exc, report_path))
      ↓
_on_done():
    root.deiconify()
    _update_button_states()  → Run re-enabled
    status message: "Playback failed: <error>  Report: <file>"
```

---

## J. HTML report generation flow

```
generate_recording_report(PlaybackResult, workspace_name, output_dir)
      ↓
Build filename: recording_{safe_name}_{YYYYMMDD_HHmmss}_{μs}.html
      ↓
Render HTML:
  Section A: summary (name, status badge, duration, counts)
  Section B: action table (index, type, value/locator, badge, duration)
  Section C: failure details (failed action, error, screenshot path)
      ↓
Write to reports/html/{filename}
      ↓
return Path
```

---

## K. Consecutive recording playback flow

```
Playback A completes
      ↓
_on_done(): root.deiconify(), _update_button_states()
      ↓
Workspace screen fully usable — recording list intact
      ↓
User clicks Recording B
      ↓
_on_recording_selection_change() → Run button enabled
      ↓
User clicks Run Selected
      ↓
New _worker() daemon thread started
      ↓
Playback B executes independently
```

No restart required. All workspace/list state is preserved between runs.
