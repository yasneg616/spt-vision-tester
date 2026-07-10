from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SERVER_CANDIDATES = ("SPT.Server.exe", "Aki.Server.exe", "Server.exe")
LAUNCHER_CANDIDATES = ("SPT.Launcher.exe", "Aki.Launcher.exe", "Launcher.exe")
CLIENT_CANDIDATES = ("EscapeFromTarkov.exe",)


@dataclass
class VisionConfig:
    spt_root: Path
    server_exe: str = ""
    launcher_exe: str = ""
    client_exe: str = ""
    server_url: str = "http://127.0.0.1:6969"
    allow_client_launch: bool = False
    allow_computer_use: bool = False
    allow_keyboard_mouse_input: bool = False
    allow_raid_automation: bool = False
    allow_text_input: bool = False
    open_launcher_instead_of_client: bool = True
    allowed_process_names: list[str] = field(default_factory=list)
    denied_process_names: list[str] = field(default_factory=list)
    startup_timeout_seconds: int = 90
    client_boot_timeout_seconds: int = 240
    scenario_max_seconds: int = 180
    max_input_actions: int = 80
    screenshot_interval_ms: int = 1000
    emergency_stop_hotkey: str = "ctrl+alt+pause"
    target_monitor_index: int = 0
    target_monitor_device_name: str = ""
    move_target_window_to_monitor: bool = False
    require_target_window_on_monitor: bool = False
    target_monitor_min_coverage: float = 0.9
    target_window_placement: str = "preserve"
    cooperative_desktop_mode: bool = False
    user_idle_seconds_before_input: float = 2.0
    max_user_idle_wait_seconds: float = 30.0
    restore_user_focus_after_input: bool = True
    restore_cursor_after_input: bool = True
    artifacts_root: Path = Path(".spt-vision-tester") / "runs"
    log_globs: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "VisionConfig":
        config_path = Path(path).expanduser().resolve()
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
        root = Path(data["SptRoot"]).expanduser()
        artifacts_root = Path(data.get("ArtifactsRoot", ".spt-vision-tester\\runs"))
        if not artifacts_root.is_absolute():
            artifacts_root = Path.cwd() / artifacts_root
        return cls(
            spt_root=root.resolve(),
            server_exe=data.get("ServerExe", ""),
            launcher_exe=data.get("LauncherExe", ""),
            client_exe=data.get("ClientExe", ""),
            server_url=data.get("ServerUrl", "http://127.0.0.1:6969"),
            allow_client_launch=bool(data.get("AllowClientLaunch", False)),
            allow_computer_use=bool(data.get("AllowComputerUse", False)),
            allow_keyboard_mouse_input=bool(data.get("AllowKeyboardMouseInput", False)),
            allow_raid_automation=bool(data.get("AllowRaidAutomation", False)),
            allow_text_input=bool(data.get("AllowTextInput", False)),
            open_launcher_instead_of_client=bool(data.get("OpenLauncherInsteadOfClient", True)),
            allowed_process_names=list(data.get("AllowedProcessNames", [])),
            denied_process_names=list(data.get("DeniedProcessNames", [])),
            startup_timeout_seconds=int(data.get("StartupTimeoutSeconds", 90)),
            client_boot_timeout_seconds=int(data.get("ClientBootTimeoutSeconds", 240)),
            scenario_max_seconds=int(data.get("ScenarioMaxSeconds", 180)),
            max_input_actions=int(data.get("MaxInputActions", 80)),
            screenshot_interval_ms=int(data.get("ScreenshotIntervalMs", 1000)),
            emergency_stop_hotkey=data.get("EmergencyStopHotkey", "ctrl+alt+pause"),
            target_monitor_index=int(data.get("TargetMonitorIndex", 0)),
            target_monitor_device_name=str(data.get("TargetMonitorDeviceName", "")),
            move_target_window_to_monitor=bool(data.get("MoveTargetWindowToMonitor", False)),
            require_target_window_on_monitor=bool(data.get("RequireTargetWindowOnMonitor", False)),
            target_monitor_min_coverage=float(data.get("TargetMonitorMinCoverage", 0.9)),
            target_window_placement=str(data.get("TargetWindowPlacement", "preserve")),
            cooperative_desktop_mode=bool(data.get("CooperativeDesktopMode", False)),
            user_idle_seconds_before_input=float(data.get("UserIdleSecondsBeforeInput", 2.0)),
            max_user_idle_wait_seconds=float(data.get("MaxUserIdleWaitSeconds", 30.0)),
            restore_user_focus_after_input=bool(data.get("RestoreUserFocusAfterInput", True)),
            restore_cursor_after_input=bool(data.get("RestoreCursorAfterInput", True)),
            artifacts_root=artifacts_root.resolve(),
            log_globs=list(data.get("LogGlobs", [])),
            raw=data,
        )

    def resolve_under_root(self, value: str) -> Path | None:
        if not value:
            return None
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.spt_root / candidate
        return candidate.resolve()

    def find_executable(self, configured: str, candidates: tuple[str, ...]) -> Path | None:
        configured_path = self.resolve_under_root(configured)
        if configured_path and configured_path.is_file():
            return configured_path
        for name in candidates:
            path = (self.spt_root / name).resolve()
            if path.is_file():
                return path
        return None

    def server_path(self) -> Path | None:
        return self.find_executable(self.server_exe, SERVER_CANDIDATES)

    def launcher_path(self) -> Path | None:
        return self.find_executable(self.launcher_exe, LAUNCHER_CANDIDATES)

    def client_path(self) -> Path | None:
        return self.find_executable(self.client_exe, CLIENT_CANDIDATES)


def load_scenario(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))
