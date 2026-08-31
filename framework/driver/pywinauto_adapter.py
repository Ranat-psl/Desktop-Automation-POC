from __future__ import annotations

import logging
import re
import time

from pywinauto import Application, Desktop

from framework.core.models import Locator
from framework.driver.keyboard_engine import (
    KeyboardEngine,
    find_typeable_child,
    is_typeable,
    _safe_control_type,
)
from framework.driver.locator_resolver import to_kwargs

_log = logging.getLogger(__name__)


class PyWinAutoAdapter:
    """Thin pywinauto wrapper to isolate external library calls."""

    def __init__(self, backend: str = "uia") -> None:
        self.backend = backend
        self._app: Application | None = None
        self._window = None
        self._window_pid: int | None = None
        self._owns_app_process = False
        self._keyboard = KeyboardEngine()

    def start(self, executable_path: str) -> None:
        _log.debug("Starting application: %s (backend=%s)", executable_path, self.backend)
        self._app = Application(backend=self.backend).start(executable_path)
        self._owns_app_process = True
        _log.debug("Application started")

    def connect(self, **kwargs: str) -> None:
        self._app = Application(backend=self.backend).connect(**kwargs)
        self._owns_app_process = False

    def focus_window(self, locator: Locator) -> None:
        if self._app is None:
            raise RuntimeError("Application is not started or connected.")

        # Prefer process-bound top-level window discovery for Win11 apps.
        raw_process = getattr(self._app, "process", None)
        if callable(raw_process):
            raw_process = raw_process()

        process_id: int | None
        try:
            process_id = int(raw_process)
        except (TypeError, ValueError):
            process_id = None

        windows = []
        if process_id is not None:
            _log.debug("Searching top-level windows by process id=%s", process_id)
            deadline = time.time() + 2.0
            while time.time() < deadline:
                windows = Desktop(backend=self.backend).windows(
                    process=process_id,
                    top_level_only=True,
                    visible_only=True,
                )
                if windows:
                    _log.debug("Found %d window(s) via process id", len(windows))
                    break
                time.sleep(0.2)

        # Fallback: title-regex search on Desktop — handles Win11 Store apps that
        # spawn in a different host process than the launcher PID.
        if not windows:
            _log.debug("No windows found by process id; trying title-regex fallback")
            search_hint = locator.value if locator.by in ("title", "class_name") else None
            if search_hint:
                deadline2 = time.time() + 5.0
                while time.time() < deadline2:
                    windows = Desktop(backend=self.backend).windows(
                        title_re=f".*{search_hint}.*",
                        top_level_only=True,
                        visible_only=True,
                    )
                    if windows:
                        _log.debug("Found %d window(s) via title-regex", len(windows))
                        break
                    time.sleep(0.2)

        if windows:
            # Prefer a top-level window that has a title if available.
            titled_windows = [w for w in windows if w.window_text().strip()]
            self._window = titled_windows[0] if titled_windows else windows[0]
            _log.debug("Focused window: '%s'", self._window.window_text())
        else:
            _log.debug("Desktop search exhausted; falling back to app-bound lookup")
            try:
                self._window = self._app.top_window()
            except Exception:
                self._window = self._app.window(**to_kwargs(locator))

        # Record the actual window process ID so quit() can kill it even when
        # Win11 Store apps spawn in a host process different from _app.process.
        try:
            if hasattr(self._window, "process_id") and callable(self._window.process_id):
                self._window_pid = int(self._window.process_id())
                _log.debug("focus_window: window process_id=%d", self._window_pid)
        except Exception:
            pass

        self._window.set_focus()
        _log.debug("set_focus() called")

    def maximize_window(self) -> None:
        """Maximize the currently focused window. Fails gracefully if not possible."""
        if self._window is None:
            _log.debug("maximize_window: no window focused, skipping")
            return
        try:
            self._window.maximize()
            _log.debug("maximize_window: maximize() called")
        except Exception as exc:  # noqa: BLE001
            _log.debug("maximize_window: could not maximize (%s)", exc)

    def click(self, locator: Locator, coords: tuple[int, int] | None = None) -> None:
        """Click a control. When coords are provided, uses SendInput directly."""
        if coords is not None:
            _log.debug(
                "click: recorded coords (%d, %d) present — using SendInput directly",
                coords[0], coords[1],
            )
            self._sendinput_click(coords[0], coords[1])
            return
        control = self._resolve_control(locator)
        self._invoke_click(control)

    def _invoke_click(self, control, coords: tuple[int, int] | None = None) -> None:
        """Interact with a resolved control without physical cursor movement."""
        try:
            if hasattr(control, "invoke"):
                control.invoke()
                _log.debug("_invoke_click: invoke() succeeded")
                return
        except Exception as exc:
            _log.debug("_invoke_click: invoke() failed (%s); trying click()", exc)
        try:
            control.click()
            _log.debug("_invoke_click: click() succeeded")
            return
        except Exception as exc:
            _log.debug("_invoke_click: click() failed (%s); trying SendInput", exc)
        try:
            if coords is not None:
                cx, cy = coords
            else:
                rect = control.rectangle()
                cx = (rect.left + rect.right) // 2
                cy = (rect.top + rect.bottom) // 2
            self._sendinput_click(cx, cy)
        except Exception as exc:
            _log.debug("_invoke_click: SendInput failed (%s); last resort click_input()", exc)
            control.click_input()

    def _sendinput_click(self, x: int, y: int) -> None:
        """Synthesise a left-button click via SendInput (no SetCursorPos)."""
        import ctypes
        SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        vx = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        nx = int((x - vx) * 65535 / vw) if vw else 0
        ny = int((y - vy) * 65535 / vh) if vh else 0
        MOUSEEVENTF_MOVE = 0x0001
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        MOUSEEVENTF_ABSOLUTE = 0x8000
        MOUSEEVENTF_VIRTUALDESK = 0x4000
        INPUT_MOUSE = 0
        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
        class _INPUT_UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]
        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("_union", _INPUT_UNION)]
        def _make_mouse(flags, dx=0, dy=0):
            inp = INPUT(); inp.type = INPUT_MOUSE
            inp._union.mi.dx = dx; inp._union.mi.dy = dy; inp._union.mi.dwFlags = flags
            return inp
        move_flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        events = (INPUT * 3)(_make_mouse(move_flags, nx, ny),
                             _make_mouse(MOUSEEVENTF_LEFTDOWN), _make_mouse(MOUSEEVENTF_LEFTUP))
        sent = ctypes.windll.user32.SendInput(3, events, ctypes.sizeof(INPUT))
        if sent != 3:
            raise RuntimeError(f"SendInput sent {sent}/3 events")
        _log.debug("_sendinput_click: sent 3 INPUT events at (%d, %d)", x, y)

    def type_text(self, locator: Locator, text: str) -> None:
        _log.debug("type_text: locator=%s|%s", locator.by, locator.value)
        control = self._resolve_typeable_control(locator)
        self._keyboard.type_into(control, text)

    def _resolve_typeable_control(self, locator: Locator):
        """Resolve a locator to a focusable text-input control.

        Semantic Element Resolution v1 — resolution priority:
          1. If the locator directly resolves to a typeable control, use it.
          2. If resolution fails or the resolved element is a window/app container,
             search the active window for the currently focused or first available
             Edit/Document control.
          3. As a final fallback, use the active window itself (relies on
             set_foreground + type_keys to land in the correct child).

        This allows TYPE actions recorded with an app-level AutomationId (e.g.
        ``Appid: Microsoft.WindowsNotepad_8wekyb3d8bbwe!App``) to still work
        correctly at playback time by finding the actual edit area.
        """
        # --- Step 1: standard resolution -----------------------------------
        control = None
        try:
            control = self._resolve_control(locator)
        except Exception as exc:
            _log.debug("_resolve_typeable_control: standard resolution failed: %s", exc)

        # --- Step 2: check whether what we got is actually typeable --------
        if control is not None and is_typeable(control):
            _log.debug("_resolve_typeable_control: resolved to typeable control")
            return control

        if control is not None:
            _log.debug(
                "_resolve_typeable_control: resolved control is not typeable "
                "(control_type=%s); searching for edit child",
                _safe_control_type(control),
            )

        # --- Step 3: find focused / first typeable child in active window ---
        self._ensure_window()
        typeable = find_typeable_child(self._window)
        if typeable is not None:
            _log.debug("_resolve_typeable_control: found typeable child in active window")
            return typeable

        # --- Step 4: window-level fallback ---------------------------------
        if control is not None:
            _log.debug("_resolve_typeable_control: falling back to original resolved control")
            return control

        _log.debug("_resolve_typeable_control: falling back to active window itself")
        return self._window

    def type_text_global(self, text: str) -> None:
        """Type text globally without a locator (e.g. into Win+R Run dialog)."""
        self._keyboard.type_global(text)

    def press_key(self, key_name: str) -> None:
        """Press and release a single named key (Enter, F5, arrow keys, …)."""
        self._keyboard.press_key(key_name)

    def hotkey(self, hotkey_str: str) -> None:
        """Press a hotkey combination such as 'ctrl+c', 'ctrl+shift+s'."""
        self._keyboard.hotkey(hotkey_str)

    def exists(self, locator: Locator, timeout_seconds: float = 5.0) -> bool:
        _log.debug("exists: locator=%s|%s", locator.by, locator.value)
        try:
            control = self._resolve_control(locator)
        except Exception:
            _log.debug("exists: control not found -> False")
            return False
        if hasattr(control, "exists"):
            # WindowSpecification supports exists(timeout=...).
            result = control.exists(timeout=timeout_seconds)
            _log.debug("exists: WindowSpecification result=%s", result)
            return result
        # Concrete UIAWrapper — resolution already confirmed it exists.
        _log.debug("exists: UIAWrapper resolved -> True")
        return control is not None

    def quit(self) -> None:
        """Terminate the specific application process started by this adapter."""
        if self._app is None:
            return
        if not self._owns_app_process:
            _log.debug("quit: adapter is connected to an external process; skipping kill")
            self._app = None
            self._window = None
            self._window_pid = None
            return
        raw_process = getattr(self._app, "process", None)
        if callable(raw_process):
            raw_process = raw_process()
        try:
            pid = int(raw_process)
        except (TypeError, ValueError):
            _log.debug("quit: cannot determine PID — skipping kill")
            return
        _log.debug("quit: killing PID %d", pid)
        import subprocess
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], check=False, capture_output=True)
        if self._window_pid is not None and self._window_pid != pid:
            _log.debug("quit: also killing window PID %d", self._window_pid)
            subprocess.run(["taskkill", "/PID", str(self._window_pid), "/F", "/T"], check=False, capture_output=True)
        self._app = None
        self._window = None
        self._window_pid = None
        self._owns_app_process = False

    def get_text(self, locator: Locator) -> str:
        _log.debug("get_text: locator=%s|%s", locator.by, locator.value)
        control = self._resolve_control(locator)
        try:
            text = str(control.window_text())
            _log.debug("get_text: result='%s'", text)
            return text
        except Exception:
            _log.debug("get_text: window_text() raised, returning empty string")
            return ""

    def _resolve_control(self, locator: Locator):
        self._ensure_window()
        kwargs = to_kwargs(locator)
        control = self._try_resolve_in_parent(self._window, kwargs, locator)
        if control is not None:
            return control

        _log.debug(
            "_resolve_control: active-window miss for %s|%s; trying desktop fallback",
            locator.by,
            locator.value,
        )
        desktop = Desktop(backend=self.backend)
        for window in desktop.windows(top_level_only=True, visible_only=True):
            control = self._try_resolve_in_parent(window, kwargs, locator)
            if control is not None:
                _log.debug(
                    "_resolve_control: fallback matched under top-level '%s'",
                    window.window_text(),
                )
                return control

        from framework.core.exceptions import LocatorResolutionError
        raise LocatorResolutionError(f"Control not found: {locator.by}={locator.value}")

    def _try_resolve_in_parent(self, parent, kwargs: dict[str, str], locator: Locator):
        if hasattr(parent, "child_window"):
            _log.debug("_resolve_control: child_window path for %s|%s", locator.by, locator.value)
            try:
                return parent.child_window(**kwargs).wrapper_object()
            except Exception:
                pass

            if locator.by == "auto_id":
                for fallback_kwargs in self._auto_id_fallback_kwargs(locator.value):
                    try:
                        return parent.child_window(**fallback_kwargs).wrapper_object()
                    except Exception:
                        continue
                return None
            return None

        _log.debug("_resolve_control: descendants path for %s|%s", locator.by, locator.value)
        try:
            matches = parent.descendants(**kwargs)
            return matches[0] if matches else None
        except Exception:
            return None

    def _auto_id_fallback_kwargs(self, raw_value: str) -> list[dict[str, str]]:
        value = raw_value.strip()
        if not value:
            return []

        human = self._humanize_token(value)
        stem = self._strip_control_suffix(human)

        candidates: list[dict[str, str]] = [
            {"title": value},
            {"best_match": value},
        ]

        if human and human != value:
            candidates.append({"best_match": human})
            candidates.append({"title": human})

        if stem and stem not in (value, human):
            candidates.append({"best_match": stem})
            candidates.append({"title_re": f".*{re.escape(stem)}.*"})

        deduped: list[dict[str, str]] = []
        seen: set[tuple[tuple[str, str], ...]] = set()
        for item in candidates:
            key = tuple(sorted(item.items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _humanize_token(self, token: str) -> str:
        step1 = re.sub(r"[_\-]+", " ", token)
        step2 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", step1)
        return re.sub(r"\s+", " ", step2).strip()

    def _strip_control_suffix(self, text: str) -> str:
        return re.sub(
            r"\s+(Button|Edit|Entry|Field|Label|Pane|Panel|Tab|Item|List|Tree|Grid|View)$",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

    def _ensure_window(self) -> None:
        """Select the active foreground window when no window has been explicitly set."""
        if self._window is not None:
            return

        _log.debug("_ensure_window: no active window — connecting to OS foreground window")
        try:
            import ctypes
            hwnd: int = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                raise RuntimeError("GetForegroundWindow() returned a null handle.")

            self._app = Application(backend=self.backend).connect(handle=hwnd)
            self._owns_app_process = False
            self._window = self._app.top_window()

            try:
                if hasattr(self._window, "process_id") and callable(self._window.process_id):
                    self._window_pid = int(self._window.process_id())
            except Exception:
                pass

            _log.info(
                "_ensure_window: connected to foreground window '%s' (pid=%s)",
                self._window.window_text(),
                self._window_pid,
            )
        except Exception as exc:
            _log.warning("_ensure_window: failed to connect to foreground window: %s", exc)
            raise RuntimeError(
                f"No active window is selected and auto-connect to foreground window failed: {exc}"
            ) from exc


# (Semantic element resolution helpers and keyboard key resolution are in
#  framework/driver/keyboard_engine.py)
