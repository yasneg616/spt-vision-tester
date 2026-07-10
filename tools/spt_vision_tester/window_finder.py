from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import pygetwindow as gw
except Exception:  # pragma: no cover
    gw = None

try:
    import psutil
    import win32api
    import win32con
    import win32gui
    import win32process
except Exception:  # pragma: no cover
    psutil = None
    win32api = None
    win32con = None
    win32gui = None
    win32process = None

from .config import VisionConfig
from .monitor_manager import (
    assert_rect_on_target_monitor,
    coverage_ratio,
    list_monitors,
    monitor_for_window,
    move_window_to_target_monitor,
    select_target_monitor,
)
from .safety import SafetyViolation, assert_title_safe


@dataclass
class WindowInfo:
    title: str
    left: int
    top: int
    width: int
    height: int
    process_name: str | None = None
    process_path: str | None = None
    pid: int | None = None
    hwnd: int | None = None
    monitor_index: int | None = None
    monitor_device_name: str | None = None
    target_monitor_coverage: float | None = None

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.left + self.width, self.top + self.height


def _process_for_hwnd(hwnd: int) -> tuple[str | None, str | None, int | None]:
    if not (win32process and psutil):
        return None, None, None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        return proc.name(), proc.exe(), pid
    except Exception:
        return None, None, None


def _window_info_for_hwnd(hwnd: int, config: VisionConfig | None = None) -> WindowInfo | None:
    if not win32gui or not win32gui.IsWindow(hwnd):
        return None
    try:
        title = win32gui.GetWindowText(hwnd) or ""
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None
    process_name, process_path, pid = _process_for_hwnd(hwnd)
    monitor = monitor_for_window(hwnd) if config is not None else None
    target = select_target_monitor(config) if config is not None else None
    return WindowInfo(
        title=title,
        left=left,
        top=top,
        width=max(0, right - left),
        height=max(0, bottom - top),
        process_name=process_name,
        process_path=process_path,
        pid=pid,
        hwnd=hwnd,
        monitor_index=monitor.index if monitor else None,
        monitor_device_name=monitor.device_name if monitor else None,
        target_monitor_coverage=coverage_ratio((left, top, right, bottom), target) if target else None,
    )


def active_window() -> WindowInfo | None:
    if win32gui:
        hwnd = int(win32gui.GetForegroundWindow())
        return _window_info_for_hwnd(hwnd) if hwnd else None
    if gw is None:
        return None
    window = gw.getActiveWindow()
    if not window:
        return None
    return WindowInfo(window.title or "", window.left, window.top, window.width, window.height)


def _allowed_process(config: VisionConfig, process_name: str | None, process_path: str | None) -> bool:
    if not process_name or not process_path:
        return False
    allowed = {name.casefold() for name in config.allowed_process_names}
    if process_name.casefold() not in allowed:
        return False
    try:
        Path(process_path).resolve().relative_to(config.spt_root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _candidate_priority(config: VisionConfig, info: WindowInfo) -> tuple[int, int, int]:
    process = (info.process_name or "").casefold()
    if process == "escapefromtarkov.exe".casefold():
        role = 0
    elif "launcher" in process:
        role = 1
    else:
        role = 2
    target_rank = 0 if (info.target_monitor_coverage or 0) >= config.target_monitor_min_coverage else 1
    return role, target_rank, -(info.width * info.height)


def find_target_window(config: VisionConfig) -> WindowInfo | None:
    target_configured = bool(config.target_monitor_index or config.target_monitor_device_name)
    if target_configured:
        list_monitors()
        select_target_monitor(config)

    candidates: list[WindowInfo] = []
    if win32gui:
        hwnds: list[int] = []

        def collect(hwnd: int, _extra: object) -> bool:
            if win32gui.IsWindowVisible(hwnd):
                hwnds.append(int(hwnd))
            return True

        win32gui.EnumWindows(collect, None)
        for hwnd in hwnds:
            info = _window_info_for_hwnd(hwnd)
            if not info or not info.title.strip() or info.width <= 0 or info.height <= 0:
                continue
            lower = info.title.casefold()
            if not any(marker in lower for marker in ("spt", "launcher", "escape from tarkov", "tarkov")):
                continue
            if not _allowed_process(config, info.process_name, info.process_path):
                continue
            annotated = _window_info_for_hwnd(hwnd, config)
            if annotated:
                candidates.append(annotated)
    elif gw is not None:
        for window in gw.getAllWindows():
            title = window.title or ""
            lower = title.casefold()
            if title.strip() and any(marker in lower for marker in ("spt", "launcher", "escape from tarkov", "tarkov")):
                candidates.append(WindowInfo(title, window.left, window.top, window.width, window.height))

    return min(candidates, key=lambda info: _candidate_priority(config, info)) if candidates else None


def assert_window_on_target_monitor(config: VisionConfig, info: WindowInfo) -> None:
    assert_rect_on_target_monitor(config, info.rect)


def assert_foreground_allowed(config: VisionConfig) -> WindowInfo:
    info = active_window()
    if info is None:
        raise SafetyViolation("Unable to identify foreground window.")
    assert_title_safe(info.title)
    if not _allowed_process(config, info.process_name, info.process_path):
        raise SafetyViolation(f"Foreground window process is not allowed: {info.process_name}")
    assert_window_on_target_monitor(config, info)
    return info


def position_target_window(config: VisionConfig) -> tuple[WindowInfo, dict[str, object]]:
    info = find_target_window(config)
    if info is None or info.hwnd is None:
        raise SafetyViolation("Unable to find a target SPT window to position.")
    assert_title_safe(info.title)
    placement = move_window_to_target_monitor(config, info.hwnd)
    updated = _window_info_for_hwnd(info.hwnd, config)
    if updated is None:
        raise SafetyViolation("SPT window disappeared while it was being positioned.")
    assert_window_on_target_monitor(config, updated)
    return updated, placement


def activate_target_window(config: VisionConfig) -> WindowInfo:
    info = find_target_window(config)
    if info is None:
        raise SafetyViolation("Unable to find a target SPT window to activate.")
    assert_title_safe(info.title)
    if config.move_target_window_to_monitor:
        target = select_target_monitor(config)
        if target and coverage_ratio(info.rect, target) < config.target_monitor_min_coverage:
            info, _placement = position_target_window(config)
    assert_window_on_target_monitor(config, info)

    hwnd = info.hwnd
    if hwnd and win32gui:
        attached_threads: list[int] = []
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
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
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
    elif gw is not None:
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
    if not _allowed_process(config, active.process_name, active.process_path):
        raise SafetyViolation(f"Activated foreground process is not allowed: {active.process_name}")
    assert_window_on_target_monitor(config, active)
    return active
