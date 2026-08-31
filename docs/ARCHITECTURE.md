# Architecture — Desktop Automation POC

## Overview

The tool is a Windows desktop record-and-playback automation framework.
It consists of five logical layers: UI shell, recorder, playback engine,
driver/adapter, and reporting.

```
┌─────────────────────────────────────────────────────────┐
│                      UI Layer (Tkinter)                 │
│  AppShell ─── WorkspaceManagementUI ─── RecorderUI      │
└───────────────────────┬─────────────────────────────────┘
                        │ user events / callbacks
┌───────────────────────▼─────────────────────────────────┐
│                  Recorder Layer                         │
│  EventListener  ──►  ActionNormalizer  ──►  RecorderService │
│                                   └──► RecordingStore   │
└───────────────────────┬─────────────────────────────────┘
                        │ recorded JSON loaded at playback
┌───────────────────────▼─────────────────────────────────┐
│                  Playback Engine                        │
│  PlaybackExecutor ──► action dispatch ──► collect results │
│       └──► generate_recording_report()                  │
└───────────────────────┬─────────────────────────────────┘
                        │ driver calls
┌───────────────────────▼─────────────────────────────────┐
│                  Driver / Adapter Layer                 │
│  DesktopDriver ──► PyWinAutoAdapter                     │
│       ├── KeyboardEngine (pynput)                       │
│       └── _sendinput_click (ctypes)                     │
└─────────────────────────────────────────────────────────┘
```

---

## Components and responsibilities

### `ui/app_shell.py` — AppShell
Single-window Tkinter application host. Manages navigation between screens
(Workspace, Recorder). Owns the Tk root window lifecycle.

### `ui/workspace_ui.py` — WorkspaceManagementUI
- Creates / opens workspaces.
- Lists recordings in the active workspace.
- Triggers playback on a daemon thread.
- Minimizes DA tool during playback; restores on completion.
- Generates and displays the per-recording HTML report.
- Restores the most-recently-used workspace on startup.

### `ui/recorder_ui.py` — RecorderUI
- Provides recording name input, start/stop/save buttons.
- Shows recording timeline (cleared at the start of each new session).
- Delegates all recording logic to `RecorderService`.

### `framework/recorder/event_listener.py` — EventListener
Pynput global hooks. Captures left mouse clicks and all keyboard events.
Filters out clicks on the DA application's own window (by screen rectangle).
Emits raw event dicts to a callback.

### `framework/recorder/action_normalizer.py` — ActionNormalizer
Converts raw event dicts into framework `Action` objects.
- Buffers printable characters → emits a single TYPE action on flush.
- Modifier-key tracking → emits HOTKEY actions (ctrl+c, alt+f4, etc.).
- Stand-alone keys → emits KEY actions (enter, backspace, F5, arrows, etc.).
- Mouse click → resolves UIA locator + records screen coordinates + screen resolution.

### `framework/recorder/recorder_service.py` — RecorderService
Manages the recording lifecycle (IDLE → RECORDING → STOPPED).
Starts/stops EventListener. Calls ActionNormalizer.flush() and persists
via RecordingStore.

### `framework/recorder/recording_store.py` — RecordingStore
Serialises/deserialises recording JSON files.
Format: versioned envelope `{"meta": {version, screen_width, screen_height}, "actions": [...]}`.
Backward-compatible with legacy flat-list format.

### `framework/playback/executor.py` — PlaybackExecutor
Main playback engine.
- Iterates through actions, dispatches to DesktopDriver.
- Collects per-action `ActionResult` objects.
- On failure: captures screenshot, stores result, raises `PlaybackExecutionError`.
- Returns `PlaybackResult` on success or failure.
- Applies coordinate scaling (via `screen_info.scale_coords`) for CLICK actions.
- Attempts `maximize_window()` after LAUNCH.

### `framework/driver/desktop_driver.py` — DesktopDriver
Thin orchestration wrapper. Delegates all calls to `PyWinAutoAdapter`.
Provides a stable interface so the executor is decoupled from pywinauto.

### `framework/driver/pywinauto_adapter.py` — PyWinAutoAdapter
All pywinauto and ctypes calls live here.
- `click()` — coord-first path via `_sendinput_click`, semantic fallback via `_resolve_control`.
- `_sendinput_click()` — ctypes `SendInput` (MOUSEEVENTF_ABSOLUTE | VIRTUALDESK).
- `focus_window()` — UIA window resolution with Win11 Store-app fallback.
- `maximize_window()` — calls `self._window.maximize()`, fails gracefully.
- `quit()` — taskkill by PID (only when `_owns_app_process=True`).

### `framework/driver/keyboard_engine.py` — KeyboardEngine
All keyboard delivery via pynput `keyboard.Controller`.
- `type_into()` / `type_global()` — `Controller().type(text)`.
- `press_key()` — press/release named key.
- `hotkey()` — press all modifiers + key, release in reverse order.

### `framework/driver/screen_info.py` — screen_info
`get_screen_size()` — queries Windows virtual screen dimensions.
`scale_coords()` — linear scaling of coordinates from recorded to current resolution.

### `framework/reporting/recording_report.py` — generate_recording_report
Generates a self-contained HTML file for a single playback execution.
Filename: `recording_{name}_{timestamp}_{microseconds}.html`.
Contains: summary, action table, failure details.

### `framework/workspace/` — workspace_service, workspace_models
Manages workspace root, name, and recordings directory path.
`recent_workspace.py` — persists most-recently-used workspace to
`~/.da-poc/recent_workspace.json` and restores it on startup.

---

## Key design decisions

| Decision | Rationale |
|---|---|
| pynput for ALL keyboard | pywinauto `type_keys` is silently ignored by Win11 WinUI3/XAML-Island apps (Notepad, etc.) |
| ctypes SendInput for mouse | Reliable low-level input; not blocked by most foreground ownership checks |
| coord-first click path | Avoids incorrect semantic resolution against wrong foreground window |
| Daemon thread for playback | Prevents Tkinter main thread from blocking during long playback |
| Separate DA Tool + target app lifecycles | DA tool must never be affected by target app crashes or close actions |
| Versioned JSON envelope | Allows recording-level metadata (screen resolution) without breaking action schema |
