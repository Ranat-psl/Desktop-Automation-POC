# User Manual — Desktop Automation POC

## Starting the application

```
cd C:\ProjectRelated\Desktop-Automation-POC
.venv\Scripts\python.exe -m ui.app_shell
```

The Desktop Automation Tool opens with two screens accessible via the left
navigation: **Workspace** and **Recorder**.

---

## Creating or opening a workspace

1. Go to the **Workspace** screen.
2. Enter a **Workspace Name** (e.g. `MyProject`).
3. Enter or browse to a **Workspace Path** — the folder where recordings and
   reports for this project will be stored.
4. Click **Create Workspace** to create a new workspace, or
   **Open Workspace** to open an existing one.

When the workspace is loaded, the recording list at the bottom populates with
any `.json` recordings already saved in that folder.

### Recent workspace

The most recently opened workspace is automatically restored the next time you
start the tool. You do not need to browse for it again.

---

## Recording a test

1. Go to the **Recorder** screen.
2. Enter a **Recording Name** (e.g. `OpenNotepadAndType`).
3. The **Recording Directory** is automatically set to the current workspace.
4. Click **Start Recording**.

While recording:
- Every mouse left-click is captured.
- Every keyboard keystroke (character, enter, backspace, F-keys, etc.) is captured.
- Hotkeys (Ctrl+C, Alt+F4, Win+R, etc.) are captured as single HOTKEY actions.
- The Recording Timeline shows live status messages.
- The DA Tool's own buttons are excluded from recording.

5. Perform your steps in the target application.
6. Click **Stop Recording** when finished.
   The recording is saved automatically.

### Important notes

- If you navigate away from the Recorder screen and return, the timeline is
  automatically cleared. Starting a new recording always begins with a fresh timeline.
- The **Recording Directory** always reflects the current workspace.

---

## Viewing recordings

On the **Workspace** screen, the recording list shows all `.json` recordings
in the current workspace folder. Columns:
- **Test Name** — filename without extension.
- **File** — relative path.
- **Actions** — number of actions in the recording.
- **Created** — file creation timestamp.

---

## Playing a recording

1. On the **Workspace** screen, click a recording to select it.
2. Click **Run Selected**.

During playback:
- The DA Tool minimizes so it does not interfere with the target application.
- Each recorded action is executed in sequence.
- A 1-second delay is inserted between actions to allow UI transitions to settle.
- When a LAUNCH action is present, the tool attempts to maximize the launched app.

After playback:
- The DA Tool is restored (de-iconified) automatically.
- A status message shows whether playback passed or failed.
- An HTML report is generated and its filename appears in the status bar.
- The **Run** button is re-enabled so you can run again or run a different recording.

### Running another recording without restarting

After a recording completes:
1. The tool remains open and the workspace list is still populated.
2. Click a different recording.
3. Click **Run Selected** again.

You do not need to restart the tool or re-open the workspace.

---

## Understanding playback status

| Status message | Meaning |
|---|---|
| `✓ Execution completed: RecordingName  Report: recording_...html` | All actions passed |
| `Playback failed: <error>  Report: recording_...html` | At least one action failed |

---

## Understanding execution results / HTML report

After playback, click **View Report** (or open the file from the status bar)
to view the HTML report. The report contains:

- **Execution Summary**: recording name, workspace, overall PASS/FAIL, duration,
  start/end timestamps, total/passed/failed action counts.
- **Action Results table**: each action listed with type, value/locator,
  PASS/FAIL badge, and duration.
- **Failure Details**: for failed actions — error message and screenshot path.

Reports are saved as:
```
reports/html/recording_{name}_{YYYYMMDD_HHmmss}_{id}.html
```

Each execution produces a **separate uniquely-named file**. Running Recording A
and Recording B produces two separate reports that never overwrite each other.

---

## Handling failed playback

If playback fails:
- The DA Tool is still restored and fully usable.
- The Run button is re-enabled.
- A failure report is generated with the failed action highlighted.
- The failure screenshot (if captured) is referenced in the report.

Fix the root cause (missing window, wrong locator, timing issue) and run again.

---

## Expected application cleanup behavior

- **Apps launched via a LAUNCH action**: the framework owns the process and can
  forcibly terminate it via `quit()`.
- **Apps launched via a keyboard hotkey** (e.g. Win+R → type `notepad` → Enter):
  the framework does **not** own the process. The recording itself should include
  an `Alt+F4` or `Ctrl+F4` hotkey action to close the app.
- If the target app is still open after playback, close it manually.
  It will not interfere with the next recording.

---

## Keyboard actions supported

| Type | Example | How recorded |
|---|---|---|
| TYPE | `Hello World` | Consecutive printable characters |
| KEY | `enter`, `backspace`, `tab`, `escape`, `delete`, `f5`, `arrow keys` | Single standalone key press |
| HOTKEY | `ctrl+c`, `alt+f4`, `cmd+r`, `ctrl+shift+s` | Modifier held + key pressed |
