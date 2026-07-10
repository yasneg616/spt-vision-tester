from __future__ import annotations

from dataclasses import dataclass

try:
    import pygetwindow as gw
except Exception:  # pragma: no cover
    gw = None

try:
    import win32api
    import win32gui
    import win32process
    import psutil
except Exception:  # pragma: no cover
    win32api = None
    win32gui = None
    win32process = None
    psutil = None

from .config import VisionConfig
from .safety import SafetyViolation, assert_title_safe


@dataclass
class WindowInfo:
    title: str
    left: int
    top: int
    width: int
    height: int
    process_name: str | None = None
    pid: int | None = None


def _process_for_hwnd(hwnd: int) -> tuple[str | None, int | None]:
    if not (win32process and psutil):
        return None, None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        return proc.name(), pid
    except Exception:
        return None, None


def active_window() -> WindowInfo | None:
    if gw is None:
        return None
    window = gw.getActiveWindow()
    if not window:
        return None
    process_name = None
    pid = None
    if win32gui:
        hwnd = win32gui.GetForegroundWindow()
        process_name, pid = _process_for_hwnd(hwnd)
    return WindowInfo(window.title or "", window.left, window.top, window.width, window.height, process_name, pid)


def find_target_window(config: VisionConfig) -> WindowInfo | None:
    if gw is None:
        return None
    candidates = []
    for window in gw.getAllWindows():
        title = window.title or ""
        if not title.strip() or window.width <= 0 or window.height <= 0:
            continue
        lower = title.lower()
        if "spt" in lower or "launcher" in lower or "escape from tarkov" in lower or "tarkov" in lower:
            process_name = None
            pid = None
            if win32gui and win32process and psutil:
                hwnd = win32gui.FindWindow(None, title)
                process_name, pid = _process_for_hwnd(hwnd) if hwnd else (None, None)
                if process_name not in config.allowed_process_names:
                    continue
            candidates.append((window, process_name, pid))
    if not candidates:
        return None
    window, process_name, pid = candidates[0]
    return WindowInfo(window.title or "", window.left, window.top, window.width, window.height, process_name, pid)


def assert_foreground_allowed(config: VisionConfig) -> WindowInfo:
    info = active_window()
    if info is None:
        raise SafetyViolation("Unable to identify foreground window.")
    assert_title_safe(info.title)
    if info.process_name and info.process_name not in config.allowed_process_names:
        raise SafetyViolation(f"Foreground window process is not allowed: {info.process_name}")
    return info


def activate_target_window(config: VisionConfig) -> WindowInfo:
    info = find_target_window(config)
    if info is None:
        raise SafetyViolation("Unable to find a target SPT window to activate.")
    assert_title_safe(info.title)
    hwnd = win32gui.FindWindow(None, info.title) if win32gui else None
    if hwnd and win32gui:
        attached_threads = []
        try:
            foreground = win32gui.GetForegroundWindow()
            foreground_thread, _ = win32process.GetWindowThreadProcessId(foreground) if foreground and win32process else (None, None)
            target_thread, _ = win32process.GetWindowThreadProcessId(hwnd) if win32process else (None, None)
            current_thread = win32api.GetCurrentThreadId() if win32api else None
            if current_thread and win32process:
                for thread_id in {foreground_thread, target_thread}:
                    if thread_id and thread_id != current_thread:
                        try:
                            win32process.AttachThreadInput(current_thread, thread_id, True)
                            attached_threads.append(thread_id)
                        except Exception:
                            pass
            win32gui.ShowWindow(hwnd, 9)
            win32gui.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            win32gui.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        finally:
            if win32api and win32process:
                current_thread = win32api.GetCurrentThreadId()
                for thread_id in attached_threads:
                    try:
                        win32process.AttachThreadInput(current_thread, thread_id, False)
                    except Exception:
                        pass
    if gw is not None:
        for window in gw.getAllWindows():
            if (window.title or "") == info.title:
                try:
                    if window.isMinimized:
                        window.restore()
                    window.activate()
                except Exception:
                    pass
                break
    active = active_window() or info
    if active.process_name and active.process_name not in config.allowed_process_names:
        raise SafetyViolation(f"Activated foreground process is not allowed: {active.process_name}")
    return active
