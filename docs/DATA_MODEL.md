# Recording Data Model — Desktop Automation POC

## JSON file structure

New recordings are saved in a versioned envelope format:

```json
{
  "meta": {
    "version": 1,
    "screen_width": 1920,
    "screen_height": 1080
  },
  "actions": [
    {
      "action_type": "hotkey",
      "locator": null,
      "value": "cmd+r",
      "timeout_seconds": null,
      "metadata": {}
    },
    {
      "action_type": "type",
      "locator": null,
      "value": "notepad",
      "timeout_seconds": null,
      "metadata": { "target_independent": true }
    },
    {
      "action_type": "key",
      "locator": null,
      "value": "enter",
      "timeout_seconds": null,
      "metadata": {}
    },
    {
      "action_type": "click",
      "locator": { "by": "auto_id", "value": "TextEditor" },
      "value": null,
      "timeout_seconds": null,
      "metadata": {
        "recorded_x": 640,
        "recorded_y": 400,
        "screen_width": 1920,
        "screen_height": 1080
      }
    },
    {
      "action_type": "type",
      "locator": { "by": "auto_id", "value": "TextEditor" },
      "value": "Hello automation",
      "timeout_seconds": null,
      "metadata": {}
    },
    {
      "action_type": "hotkey",
      "locator": null,
      "value": "alt+f4",
      "timeout_seconds": null,
      "metadata": {}
    }
  ]
}
```

---

## Field reference

### meta (recording-level)

| Field | Type | Description |
|---|---|---|
| `version` | int | Schema version (currently 1) |
| `screen_width` | int | Virtual screen width in pixels at record time |
| `screen_height` | int | Virtual screen height in pixels at record time |

### action fields

| Field | Type | Description |
|---|---|---|
| `action_type` | string | One of: `launch`, `click`, `type`, `key`, `hotkey`, `wait`, `assert_exists`, `assert_text` |
| `locator` | object or null | `{ "by": "auto_id"\|"title"\|"control_type", "value": "..." }` — target control identifier |
| `value` | string or null | Text for TYPE/HOTKEY/KEY/LAUNCH; null for CLICK |
| `timeout_seconds` | number or null | Used by WAIT and assertion actions |
| `metadata` | object | Action-specific extra data (see below) |

### metadata per action type

**CLICK:**
```json
{
  "recorded_x": 640,
  "recorded_y": 400,
  "screen_width": 1920,
  "screen_height": 1080
}
```
`recorded_x/y` are the raw screen coordinates at record time.
`screen_width/height` are used to scale coordinates to the current resolution at playback.

**TYPE (target-independent):**
```json
{ "target_independent": true }
```
Indicates the type was performed without a focused control (e.g. into the Win+R dialog).

---

## Backward compatibility

Legacy recordings saved as a flat list `[action, …]` are still loaded correctly.
`RecordingStore.load()` detects the format by checking whether the JSON root is a
`dict` (new) or a `list` (legacy). Legacy files do not have screen resolution data;
coordinates are used as-is (no scaling applied).

---

## Locator resolution priority

When recording a click, `_resolve_locator_at(x, y)` tries to identify the control
using pywinauto UIA in this priority order:

1. `auto_id` — automation ID (most stable across sessions)
2. `title` — accessible name / window text (meaningful labels ≤ 80 chars)
3. `control_type` — structural class name (last resort)
4. `null` — if no meaningful identifier found

At playback, when coordinates are present, the locator is used only as a
fallback if the coordinate path fails. When no coordinates are present, the
locator drives resolution.
