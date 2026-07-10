from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

try:
    import win32api
    import win32con
    import win32gui
except Exception:  # pragma: no cover
    win32api = None
    win32con = None
    win32gui = None

from .safety import SafetyViolation


@dataclass(frozen=True)
class MonitorInfo:
    index: int
    handle: int
    device_name: str
    primary: bool
    left: int
    top: int
    right: int
    bottom: int
    work_left: int
    work_top: int
    work_right: int
    work_bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def work_width(self) -> int:
        return self.work_right - self.work_left

    @property
    def work_height(self) -> int:
        return self.work_bottom - self.work_top

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    @property
    def work_bounds(self) -> tuple[int, int, int, int]:
        return self.work_left, self.work_top, self.work_right, self.work_bottom

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "width": self.width,
                "height": self.height,
                "workWidth": self.work_width,
                "workHeight": self.work_height,
            }
        )
        return payload


def list_monitors() -> list[MonitorInfo]:
    if win32api is None:
        raise SafetyViolation("Windows monitor APIs are unavailable; install pywin32 first.")
    raw: list[dict[str, Any]] = []
    for order, (handle, _dc, _rect) in enumerate(win32api.EnumDisplayMonitors()):
        details = win32api.GetMonitorInfo(handle)
        left, top, right, bottom = details["Monitor"]
        work_left, work_top, work_right, work_bottom = details["Work"]
        raw.append(
            {
                "order": order,
                "handle": int(handle),
                "device_name": str(details.get("Device", "")),
                "primary": bool(details.get("Flags", 0) & 1),
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
                "work_left": work_left,
                "work_top": work_top,
                "work_right": work_right,
                "work_bottom": work_bottom,
            }
        )
    raw.sort(key=lambda item: (not item["primary"], item["order"]))
    return [
        MonitorInfo(index=index, **{key: value for key, value in item.items() if key != "order"})
        for index, item in enumerate(raw, 1)
    ]


def select_target_monitor(config: Any, monitors: list[MonitorInfo] | None = None) -> MonitorInfo | None:
    available = monitors if monitors is not None else list_monitors()
    configured_index = int(getattr(config, "target_monitor_index", 0) or 0)
    configured_device = str(getattr(config, "target_monitor_device_name", "") or "").strip()
    if configured_index < 0:
        raise SafetyViolation("TargetMonitorIndex cannot be negative.")

    by_device = None
    if configured_device:
        by_device = next(
            (monitor for monitor in available if monitor.device_name.casefold() == configured_device.casefold()),
            None,
        )
        if by_device is None:
            raise SafetyViolation(f"Configured target monitor is not connected: {configured_device}")

    by_index = None
    if configured_index:
        by_index = next((monitor for monitor in available if monitor.index == configured_index), None)
        if by_index is None:
            raise SafetyViolation(
                f"TargetMonitorIndex={configured_index} is unavailable; {len(available)} monitor(s) were detected."
            )

    if by_device and by_index and by_device.handle != by_index.handle:
        raise SafetyViolation(
            "TargetMonitorIndex and TargetMonitorDeviceName select different displays; review monitor diagnostics."
        )
    return by_device or by_index


def validate_monitor_configuration(config: Any, *, require_target: bool = False) -> dict[str, Any]:
    monitors = list_monitors()
    target = select_target_monitor(config, monitors)
    placement = str(getattr(config, "target_window_placement", "preserve"))
    coverage = float(getattr(config, "target_monitor_min_coverage", 0.9))
    cooperative = bool(getattr(config, "cooperative_desktop_mode", False))

    if placement not in {"preserve", "working-area", "full-monitor"}:
        raise SafetyViolation("TargetWindowPlacement must be preserve, working-area, or full-monitor.")
    if not 0.5 <= coverage <= 1.0:
        raise SafetyViolation("TargetMonitorMinCoverage must be between 0.5 and 1.0.")
    if float(getattr(config, "user_idle_seconds_before_input", 2.0)) < 0:
        raise SafetyViolation("UserIdleSecondsBeforeInput cannot be negative.")
    if float(getattr(config, "max_user_idle_wait_seconds", 30.0)) <= 0:
        raise SafetyViolation("MaxUserIdleWaitSeconds must be positive.")

    monitor_policy_enabled = any(
        (
            require_target,
            bool(getattr(config, "move_target_window_to_monitor", False)),
            bool(getattr(config, "require_target_window_on_monitor", False)),
            cooperative,
        )
    )
    if monitor_policy_enabled and target is None:
        raise SafetyViolation("A target monitor must be configured for the requested monitor policy.")
    if cooperative and not bool(getattr(config, "require_target_window_on_monitor", False)):
        raise SafetyViolation("CooperativeDesktopMode requires RequireTargetWindowOnMonitor=true.")

    return {
        "detected": [monitor.to_dict() for monitor in monitors],
        "target": target.to_dict() if target else None,
        "moveTargetWindow": bool(getattr(config, "move_target_window_to_monitor", False)),
        "requireTargetWindow": bool(getattr(config, "require_target_window_on_monitor", False)),
        "placement": placement,
        "cooperativeDesktopMode": cooperative,
        "inputIsolation": False,
    }


def intersection_area(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> int:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    return max(0, right - left) * max(0, bottom - top)


def coverage_ratio(rect: tuple[int, int, int, int], monitor: MonitorInfo) -> float:
    area = max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])
    return intersection_area(rect, monitor.bounds) / area if area else 0.0


def assert_rect_on_target_monitor(config: Any, rect: tuple[int, int, int, int]) -> MonitorInfo | None:
    target = select_target_monitor(config)
    if target is None:
        return None
    ratio = coverage_ratio(rect, target)
    required = float(getattr(config, "target_monitor_min_coverage", 0.9))
    if bool(getattr(config, "require_target_window_on_monitor", False)) and ratio < required:
        raise SafetyViolation(
            f"SPT window is not contained by target monitor {target.index} ({target.device_name}); "
            f"coverage={ratio:.3f}, required={required:.3f}."
        )
    return target


def monitor_for_window(hwnd: int) -> MonitorInfo | None:
    if win32api is None:
        return None
    handle = int(win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST))
    return next((monitor for monitor in list_monitors() if monitor.handle == handle), None)


def move_window_to_target_monitor(config: Any, hwnd: int) -> dict[str, Any]:
    if win32gui is None or win32con is None:
        raise SafetyViolation("Windows window-placement APIs are unavailable.")
    target = select_target_monitor(config)
    if target is None:
        raise SafetyViolation("No target monitor is configured.")
    if not win32gui.IsWindow(hwnd):
        raise SafetyViolation("Target SPT window is no longer available.")

    current = win32gui.GetWindowRect(hwnd)
    placement = str(getattr(config, "target_window_placement", "preserve"))
    if placement == "full-monitor":
        left, top, right, bottom = target.bounds
    elif placement == "working-area":
        left, top, right, bottom = target.work_bounds
    else:
        width = min(max(1, current[2] - current[0]), target.work_width)
        height = min(max(1, current[3] - current[1]), target.work_height)
        left = target.work_left + max(0, (target.work_width - width) // 2)
        top = target.work_top + max(0, (target.work_height - height) // 2)
        right = left + width
        bottom = top + height

    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    flags = win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
    win32gui.SetWindowPos(hwnd, 0, left, top, right - left, bottom - top, flags)
    updated = win32gui.GetWindowRect(hwnd)
    ratio = coverage_ratio(updated, target)
    return {
        "target": target.to_dict(),
        "before": list(current),
        "after": list(updated),
        "coverage": ratio,
        "placement": placement,
    }
