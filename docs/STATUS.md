# Implementation Status — Desktop Automation POC

Last updated: 2026-08-31

---

## IMPLEMENTED (verified by automated tests and/or manual validation)

| Feature | Notes |
|---|---|
| Workspace creation and open | Name + path + recordings dir |
| Recent workspace persistence | `~/.da-poc/recent_workspace.json`; restored on startup |
| Recording session lifecycle | IDLE → RECORDING → STOPPED |
| Mouse left-click recording | Captures x/y + UIA locator + screen resolution |
| TYPE action recording | Buffered printable characters → single TYPE action |
| KEY action recording | Enter, backspace, tab, escape, delete, F1–F12, arrows, home/end |
| HOTKEY action recording | Modifier+key combinations including Ctrl+F4 and Alt+F4 |
| DA Tool window exclusion from recording | Clicks on DA app filtered via excluded_rect |
| Recorder timeline reset per session | `_events_list.delete(0, END)` at RECORDING state start |
| Recording JSON persistence | Versioned envelope: `{ meta, actions }` |
| Backward-compat load of legacy flat-list JSON | `isinstance(raw, list)` check |
| Screen resolution stored in CLICK metadata | `screen_width/screen_height` in action metadata |
| Coordinate scaling on CLICK playback | `scale_coords()` applied before SendInput |
| TYPE playback via pynput | Works on Win11 WinUI3/XAML-Island apps (Notepad) |
| KEY playback via pynput | Named key press/release |
| HOTKEY playback via pynput | Modifier+key press/release ordering |
| CLICK playback via ctypes SendInput | MOUSEEVENTF_ABSOLUTE + VIRTUALDESK |
| Target app maximize on LAUNCH | `adapter.maximize_window()` called post-LAUNCH |
| Per-action result collection | `ActionResult` per action, stored in `PlaybackResult` |
| Failure screenshot on action failure | `capture_failure_screenshot()` |
| Per-recording HTML execution report | Unique filename per execution |
| Report: summary section | Name, status badge, duration, counts, timestamps |
| Report: action table | Type, value/locator, PASS/FAIL, duration |
| Report: failure details | Error message, screenshot path |
| DA Tool minimizes during playback | `root.iconify()` before thread start |
| DA Tool restores after playback | `root.deiconify()` in `_on_done()` |
| Run button re-enabled after pass/fail | `_update_button_states()` in `_on_done()` |
| Consecutive playback in same session | New driver/executor per run; workspace state preserved |
| Target app teardown for owned processes | `taskkill /PID` in `driver.quit()` |
| Keyboard-launched app teardown via recording | Alt+F4 / Ctrl+F4 as HOTKEY actions |

---

## PARTIALLY IMPLEMENTED

| Feature | Status | Notes |
|---|---|---|
| Element-based fallback when coords are stale | Partial | Locator is stored and used when no coords; but if locator is generic (Pane) it may resolve to wrong control |
| DPI-aware coordinate scaling | Partial | Linear pixel scaling implemented; per-monitor DPI factor not yet applied |
| Wait/synchronization between actions | Partial | Fixed `inter_action_delay_seconds=1.0` sleep; `wait_until()` exists but not used for action-level sync |
| AI/code-gen integration | Stub only | `framework/ai/planner_interface.py` is an extension point, not implemented |

---

## KNOWN LIMITATIONS

| Limitation | Details |
|---|---|
| Coordinate-based click is resolution-dependent | Linear scaling corrects proportional position but does not account for per-monitor DPI scaling factors. Multi-monitor setups with different DPIs may produce offset clicks. |
| Keyboard-launched apps are not owned by framework | Apps opened via Win+R, cmd+r, or other keyboard shortcuts are not tracked as owned processes. `driver.quit()` does not terminate them. The recording must include an explicit close action (Alt+F4). |
| Win11 packaged app PID mismatch | Win11 Store apps (e.g. Notepad) spawn in a host process different from the launcher stub PID. `focus_window()` uses title-regex fallback to find the correct window. `quit()` uses both `_app.process` and `_window_pid`. |
| Locator resolution may return generic locators | For certain UIA trees, `_resolve_locator_at()` returns `control_type=Pane`. At playback this falls back to coordinates, which is correct — but the locator alone is not reusable if coordinates are missing. |
| No explicit window wait on FOCUS_WINDOW | After a keyboard-launched app appears, there is no `wait_until(window_visible)` — relying on `inter_action_delay_seconds`. |
| Left-click only | Right-click, double-click, drag, scroll are not recorded or played back. |
| Single monitor assumed for virtual screen | `GetSystemMetrics(SM_CXVIRTUALSCREEN)` returns the total virtual screen; on multi-monitor setups with the same DPI this scales correctly; different-DPI setups are a limitation. |

---

## FUTURE ENHANCEMENTS

See [ROADMAP.md](ROADMAP.md) for the phased roadmap.
