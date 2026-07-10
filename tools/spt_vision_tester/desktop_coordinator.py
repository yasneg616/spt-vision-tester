from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import win32api
    import win32gui
except Exception:  # pragma: no cover
    win32api = None
    win32gui = None

from .safety import SafetyViolation, assert_no_denied_processes


@dataclass(frozen=True)
class DesktopContext:
    foreground_hwnd: int | None
    cursor_position: tuple[int, int] | None


def last_input_tick() -> int | None:
    if win32api is None or not hasattr(win32api, "GetLastInputInfo"):
        return None
    return int(win32api.GetLastInputInfo())


def _idle_seconds() -> float:
    if win32api is None or not hasattr(win32api, "GetLastInputInfo"):
        return 0.0
    current = int(win32api.GetTickCount())
    last = int(win32api.GetLastInputInfo())
    return ((current - last) & 0xFFFFFFFF) / 1000.0


def wait_for_user_idle(
    config: Any,
    stop_file: Path,
    *,
    ignored_input_tick: int | None = None,
    max_wait_seconds: float | None = None,
) -> None:
    required = float(getattr(config, "user_idle_seconds_before_input", 2.0))
    if required <= 0:
        return
    configured_wait = float(getattr(config, "max_user_idle_wait_seconds", 30.0))
    deadline = time.monotonic() + min(configured_wait, max_wait_seconds or configured_wait)
    while time.monotonic() < deadline:
        if stop_file.exists():
            raise SafetyViolation(f"Emergency stop file exists: {stop_file}")
        assert_no_denied_processes(config.denied_process_names)
        current_tick = last_input_tick()
        if ignored_input_tick is not None and current_tick == ignored_input_tick:
            return
        if _idle_seconds() >= required:
            return
        time.sleep(0.1)
    raise SafetyViolation("User input remained active; cooperative desktop action was not attempted.")


def capture_desktop_context() -> DesktopContext:
    foreground = int(win32gui.GetForegroundWindow()) if win32gui else None
    cursor = tuple(win32api.GetCursorPos()) if win32api else None
    return DesktopContext(foreground_hwnd=foreground or None, cursor_position=cursor)


def restore_desktop_context(
    config: Any,
    context: DesktopContext,
    *,
    target_hwnd: int | None,
    plugin_cursor_position: tuple[int, int] | None,
    plugin_input_tick: int | None,
) -> dict[str, str]:
    results: dict[str, str] = {}
    if win32gui and bool(getattr(config, "restore_user_focus_after_input", True)):
        current = int(win32gui.GetForegroundWindow())
        if current != target_hwnd:
            results["focus"] = "kept_user_change"
        elif context.foreground_hwnd and context.foreground_hwnd != target_hwnd and win32gui.IsWindow(context.foreground_hwnd):
            try:
                win32gui.SetForegroundWindow(context.foreground_hwnd)
                results["focus"] = "restored"
            except Exception:
                results["focus"] = "restore_failed"
        else:
            results["focus"] = "unchanged"

    if win32api and bool(getattr(config, "restore_cursor_after_input", True)):
        current_cursor = tuple(win32api.GetCursorPos())
        current_tick = last_input_tick()
        if plugin_cursor_position is None:
            results["cursor"] = "unchanged"
        elif plugin_input_tick is not None and current_tick != plugin_input_tick:
            results["cursor"] = "kept_user_change"
        elif current_cursor != plugin_cursor_position:
            results["cursor"] = "kept_user_change"
        elif context.cursor_position is not None:
            try:
                win32api.SetCursorPos(context.cursor_position)
                results["cursor"] = "restored"
            except Exception:
                results["cursor"] = "restore_failed"
        else:
            results["cursor"] = "unchanged"
    return results
