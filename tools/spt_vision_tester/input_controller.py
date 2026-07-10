from __future__ import annotations

import time
from pathlib import Path
from typing import Any

try:
    import pyautogui
except Exception:  # pragma: no cover
    pyautogui = None

from .artifact_writer import ArtifactWriter
from .config import VisionConfig
from .desktop_coordinator import (
    capture_desktop_context,
    last_input_tick,
    restore_desktop_context,
    wait_for_user_idle,
)
from .safety import SafetyViolation
from .screenshotter import capture_window
from .window_finder import active_window, activate_target_window, assert_foreground_allowed


class InputController:
    def __init__(
        self,
        config: VisionConfig,
        artifact: ArtifactWriter,
        *,
        max_actions: int | None = None,
        max_seconds: float | None = None,
    ):
        self.config = config
        self.artifact = artifact
        self.actions = 0
        self.started = time.monotonic()
        self.stop_file = artifact.run_dir / "EMERGENCY_STOP"
        requested_actions = config.max_input_actions if max_actions is None else max_actions
        requested_seconds = config.scenario_max_seconds if max_seconds is None else max_seconds
        self.max_actions = min(requested_actions, config.max_input_actions)
        self.max_seconds = min(requested_seconds, config.scenario_max_seconds)
        self.last_injected_input_tick: int | None = None

    def _check_limits(self, require_foreground: bool = True) -> None:
        if not self.config.allow_computer_use or not self.config.allow_keyboard_mouse_input:
            raise SafetyViolation("Keyboard/mouse input requires AllowComputerUse=true and AllowKeyboardMouseInput=true.")
        if pyautogui is None:
            raise SafetyViolation("pyautogui is unavailable; install requirements first.")
        if self.stop_file.exists():
            raise SafetyViolation(f"Emergency stop file exists: {self.stop_file}")
        if self.actions >= self.max_actions:
            raise SafetyViolation("MaxInputActions reached.")
        if time.monotonic() - self.started > self.max_seconds:
            raise SafetyViolation("ScenarioMaxSeconds reached.")
        if require_foreground:
            assert_foreground_allowed(self.config)

    def _before_after(self, name: str, fn: Any, *, activate_first: bool = False) -> None:
        cooperative = self.config.cooperative_desktop_mode
        self._check_limits(require_foreground=not (cooperative or activate_first))
        context = None
        target = None
        plugin_cursor = None
        plugin_input_tick = None
        if cooperative:
            remaining_seconds = max(0.0, self.max_seconds - (time.monotonic() - self.started))
            if remaining_seconds <= 0:
                raise SafetyViolation("ScenarioMaxSeconds reached while waiting for cooperative desktop input.")
            wait_for_user_idle(
                self.config,
                self.stop_file,
                ignored_input_tick=self.last_injected_input_tick,
                max_wait_seconds=remaining_seconds,
            )
            context = capture_desktop_context()

        try:
            if cooperative or activate_first:
                target = activate_target_window(self.config)
            else:
                target = assert_foreground_allowed(self.config)
            capture_window(self.artifact, self.config, f"before_{name}")
            fn()
            self.actions += 1
            plugin_input_tick = last_input_tick()
            self.last_injected_input_tick = plugin_input_tick
            plugin_cursor = capture_desktop_context().cursor_position

            if cooperative:
                foreground = active_window()
                if not foreground or foreground.hwnd != target.hwnd:
                    raise SafetyViolation("Foreground changed during cooperative input; stopping before another action.")
            time.sleep(0.1)
            try:
                capture_window(self.artifact, self.config, f"after_{name}")
            except SafetyViolation as exc:
                self.artifact.append_timeline("post_input_screenshot_skipped", action=name, reason=str(exc))
            if cooperative:
                foreground = active_window()
                if not foreground or foreground.hwnd != target.hwnd:
                    raise SafetyViolation("User changed focus during cooperative input; stopping before another action.")
                if plugin_input_tick is not None and last_input_tick() != plugin_input_tick:
                    raise SafetyViolation("User input was detected during cooperative action verification; stopping.")
            self.artifact.append_timeline("input", action=name, count=self.actions)
        finally:
            if cooperative and context is not None:
                try:
                    restoration = restore_desktop_context(
                        self.config,
                        context,
                        target_hwnd=target.hwnd if target else None,
                        plugin_cursor_position=plugin_cursor,
                        plugin_input_tick=plugin_input_tick,
                    )
                    self.artifact.append_timeline("cooperative_desktop_restore", action=name, **restoration)
                except Exception as exc:
                    self.artifact.append_timeline(
                        "cooperative_desktop_restore_error",
                        action=name,
                        error=str(exc),
                    )

    def press(self, key: str) -> None:
        self._before_after(f"press_{key}", lambda: pyautogui.press(key))

    def hotkey(self, keys: list[str]) -> None:
        self._before_after("hotkey", lambda: pyautogui.hotkey(*keys))

    def hold(self, key: str, seconds: float) -> None:
        def run() -> None:
            pyautogui.keyDown(key)
            try:
                time.sleep(seconds)
            finally:
                pyautogui.keyUp(key)

        self._before_after(f"hold_{key}", run)

    def move_mouse_relative(self, x: int, y: int) -> None:
        self._before_after("move_mouse_relative", lambda: pyautogui.moveRel(x, y, duration=0.1))

    def click(self) -> None:
        def run() -> None:
            window = assert_foreground_allowed(self.config)
            pyautogui.click(x=window.left + window.width // 2, y=window.top + window.height // 2)

        self._before_after("click_center", run)

    def click_window_percent(self, x_percent: float, y_percent: float) -> None:
        def run() -> None:
            window = assert_foreground_allowed(self.config)
            x = window.left + int(window.width * x_percent)
            y = window.top + int(window.height * y_percent)
            pyautogui.click(x=x, y=y)

        self._before_after(f"click_pct_{x_percent:.3f}_{y_percent:.3f}", run)

    def double_click_window_percent(self, x_percent: float, y_percent: float) -> None:
        def run() -> None:
            window = assert_foreground_allowed(self.config)
            x = window.left + int(window.width * x_percent)
            y = window.top + int(window.height * y_percent)
            pyautogui.doubleClick(x=x, y=y)

        self._before_after(f"double_click_pct_{x_percent:.3f}_{y_percent:.3f}", run)

    def focus_target_window(self) -> None:
        self.artifact.append_timeline("focus_attempt")
        self._before_after("focus_target_window", lambda: None, activate_first=True)

    def press_sequence(self, keys: list[str], interval: float = 0.2) -> None:
        for key in keys:
            self.press(key)
            time.sleep(interval)

    def wait(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._check_limits()
            time.sleep(min(0.5, deadline - time.monotonic()))

    def text(self, value: str) -> None:
        if not self.config.allow_text_input:
            raise SafetyViolation("Text input is disabled unless AllowTextInput=true.")
        self._before_after("text", lambda: pyautogui.write(value))
