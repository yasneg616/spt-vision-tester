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
from .safety import SafetyViolation
from .screenshotter import capture_window
from .window_finder import activate_target_window, assert_foreground_allowed


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

    def _before_after(self, name: str, fn: Any) -> None:
        self._check_limits()
        capture_window(self.artifact, self.config, f"before_{name}")
        fn()
        self.actions += 1
        time.sleep(0.1)
        try:
            capture_window(self.artifact, self.config, f"after_{name}")
        except SafetyViolation as exc:
            self.artifact.append_timeline("post_input_screenshot_skipped", action=name, reason=str(exc))
        self.artifact.append_timeline("input", action=name, count=self.actions)

    def press(self, key: str) -> None:
        self._before_after(f"press_{key}", lambda: pyautogui.press(key))

    def hotkey(self, keys: list[str]) -> None:
        self._before_after("hotkey", lambda: pyautogui.hotkey(*keys))

    def hold(self, key: str, seconds: float) -> None:
        def run() -> None:
            pyautogui.keyDown(key)
            time.sleep(seconds)
            pyautogui.keyUp(key)

        self._before_after(f"hold_{key}", run)

    def move_mouse_relative(self, x: int, y: int) -> None:
        self._before_after("move_mouse_relative", lambda: pyautogui.moveRel(x, y, duration=0.1))

    def click(self) -> None:
        self._before_after("click", lambda: pyautogui.click())

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
        self._check_limits(require_foreground=False)
        self.artifact.append_timeline("focus_attempt")
        activate_target_window(self.config)
        assert_foreground_allowed(self.config)
        self.actions += 1
        time.sleep(0.1)
        capture_window(self.artifact, self.config, "after_focus_target_window")
        self.artifact.append_timeline("input", action="focus_target_window", count=self.actions)

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
