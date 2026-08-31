
---

# 4. `docs/CHANGELOG.md`

For this one, **don't try to list every individual code change**. Keep it as a milestone-level history.

```markdown
# Changelog

All notable project milestones and major functional improvements are documented here.

The changelog focuses on meaningful product and engineering changes rather than every individual source-code modification.

---

# Current Baseline

## Recorder Playback Reliability and Click Automation

### Major Improvements

The current baseline established a significantly more reliable recorder and playback foundation.

### Recording

- Improved recording lifecycle handling.
- Improved recorder UI state reset.
- Fixed recording timeline state persistence between sessions.
- Improved workspace-aware recording behavior.
- Improved recording persistence.

### Workspace

- Fixed workspace name/path handling.
- Improved workspace persistence.
- Improved workspace-specific recording paths.

### Playback

- Improved playback lifecycle.
- Improved cleanup handling.
- Improved application/window lifecycle handling.
- Improved consecutive playback behavior.
- Improved playback state reset.
- Improved handling of playback success and failure.

### Mouse Automation

- Added/strengthened CLICK action handling.
- Added screen-width and screen-height metadata to CLICK actions.
- Added coordinate scaling during playback.
- Added validation for click reliability.
- Added mixed keyboard and mouse playback validation.

### Recording Format

- Introduced versioned recording envelope support.
- Added recording-level metadata.
- Added backward compatibility for legacy recording formats.

### Reporting

- Improved recording execution reports.
- Added/maintained action-level execution results.
- Added execution duration information.
- Improved report generation across the recording lifecycle.

### Testing

Focused click-reliability validation reached:

- 32 passed
- 0 skipped
- 0 failed

The full regression validation at the documented baseline reached:

- 567 passed
- 4 skipped
- 0 failed

---

# Important Bugs Fixed

## Recorder Timeline State

### Problem

Messages/events from an earlier recording session could remain visible during a later recording session.

### Resolution

Recording-session state is cleared appropriately when a new recording begins.

---

## Recorder UI State

### Problem

Recorder controls could retain an incorrect state after recording/playback lifecycle transitions.

### Resolution

Recorder state-reset and button-state handling were improved.

---

## Workspace Path/Name Handling

### Problem

Workspace information and associated paths required correction.

### Resolution

Workspace management and path handling were corrected and validated.

---

## Playback Lifecycle

### Problem

The desktop automation application and target application lifecycle required more reliable handling during playback.

### Resolution

Playback initialization, completion and cleanup behavior were improved.

---

## Click Reliability

### Problem

Recorded click coordinates can become unreliable when the playback screen dimensions differ from the recording environment.

### Resolution

Screen dimensions are captured as metadata and coordinate scaling is applied during playback where supported.

---

# Current Known Limitations

The current baseline still has known limitations including:

- Per-monitor DPI scaling is not fully implemented.
- Keyboard-launched applications may require explicit close actions.
- The supported mouse-action set is still limited.
- Window appearance timing depends on the current execution strategy/inter-action delays.
- More advanced element/control identification is still future work.

---

# Future Development

Future roadmap areas include:

- Per-monitor DPI support.
- Additional mouse actions.
- More robust window identification.
- Control/element-based identification.
- Recording editing.
- Test case management.
- Code generation.
- Advanced reporting.
- CI/CD integration.
- Parallel execution.
- AI-assisted automation.

See [ROADMAP.md](ROADMAP.md) for the detailed development roadmap.

---

# Baseline Repository Information

Current protected baseline:

- Branch: `recovery/before-mvp-recovery`
- Commit: `940ffbf`
- Commit message: `Baseline: recorder playback reliability and click automation`

The documentation should be updated whenever a future development phase materially changes the behavior or architecture of the product.