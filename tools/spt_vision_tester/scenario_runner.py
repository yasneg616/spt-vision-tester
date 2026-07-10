from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .artifact_writer import ArtifactWriter
from .config import VisionConfig
from .detectors import analyze_run
from .input_controller import InputController
from .log_collector import collect_logs
from .safety import SafetyViolation, assert_no_denied_processes
from .scenario_validator import assert_valid_scenario
from .screenshotter import capture_window
from .window_finder import find_target_window


def require_scenario_permissions(config: VisionConfig, scenario: dict[str, Any]) -> None:
    if scenario.get("requiresComputerUse") and not config.allow_computer_use:
        raise SafetyViolation("Scenario requires AllowComputerUse=true.")
    if scenario.get("requiresKeyboardMouseInput") and not config.allow_keyboard_mouse_input:
        raise SafetyViolation("Scenario requires AllowKeyboardMouseInput=true.")
    if scenario.get("allowRaidAutomation") and not config.allow_raid_automation:
        raise SafetyViolation("Scenario requires AllowRaidAutomation=true.")


def assert_scenario_active(config: VisionConfig, stop_file: Path) -> None:
    assert_no_denied_processes(config.denied_process_names)
    if stop_file.exists():
        raise SafetyViolation(f"Emergency stop file exists: {stop_file}")


def require_time_budget(deadline: float, seconds: float, label: str) -> float:
    remaining = max(0.0, deadline - time.monotonic())
    if seconds > remaining:
        raise SafetyViolation(f"{label} exceeds the remaining scenario time budget.")
    return seconds


def wait_for_window(config: VisionConfig, timeout: float, stop_file: Path) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert_scenario_active(config, stop_file)
        if find_target_window(config):
            return True
        time.sleep(1)
    return False


def wait_for_seconds(config: VisionConfig, seconds: float, stop_file: Path) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert_scenario_active(config, stop_file)
        time.sleep(min(0.5, deadline - time.monotonic()))


def run_scenario(config: VisionConfig, scenario: dict[str, Any], artifact: ArtifactWriter, state_file: Path) -> dict[str, Any]:
    assert_valid_scenario(scenario, require_schema_version=False)
    require_scenario_permissions(config, scenario)
    max_seconds = min(float(scenario.get("maxSeconds", config.scenario_max_seconds)), config.scenario_max_seconds)
    max_actions = min(int(scenario.get("maxInputActions", config.max_input_actions)), config.max_input_actions)
    input_ctl = InputController(config, artifact, max_actions=max_actions, max_seconds=max_seconds)
    deadline = time.monotonic() + max_seconds
    stop_file = artifact.run_dir / "EMERGENCY_STOP"
    status = "ok"
    error = None
    artifact.append_timeline("scenario_start", name=scenario.get("name"), maxSeconds=max_seconds)
    try:
        for index, step in enumerate(scenario.get("steps", []), 1):
            if time.monotonic() > deadline:
                raise SafetyViolation("Scenario maximum duration reached.")
            assert_scenario_active(config, stop_file)
            action = step.get("action")
            artifact.append_timeline("step_start", index=index, action=action, step=step)
            condition = step.get("condition")
            if condition == "wait_for_window":
                timeout = require_time_budget(
                    deadline,
                    float(step.get("timeoutSeconds", 30)),
                    "wait_for_window",
                )
                if not wait_for_window(config, timeout, stop_file):
                    raise SafetyViolation("Timed out waiting for target SPT window.")
            elif condition == "wait_for_stable_image":
                seconds = require_time_budget(deadline, float(step.get("seconds", 3)), condition)
                wait_for_seconds(config, seconds, stop_file)
            elif condition == "wait_for_log_quiet":
                seconds = require_time_budget(deadline, float(step.get("seconds", 5)), condition)
                wait_for_seconds(config, seconds, stop_file)
            elif condition == "wait_for_seconds":
                seconds = require_time_budget(deadline, float(step.get("seconds", 1)), condition)
                wait_for_seconds(config, seconds, stop_file)

            if action == "screenshot":
                capture_window(artifact, config, step.get("label"))
            elif action == "press":
                input_ctl.press(step["key"])
            elif action == "hold":
                seconds = require_time_budget(deadline, float(step.get("seconds", 0.5)), "hold")
                input_ctl.hold(step["key"], seconds)
            elif action == "move_mouse_relative":
                input_ctl.move_mouse_relative(int(step.get("x", 0)), int(step.get("y", 0)))
            elif action == "click_center":
                input_ctl.click()
            elif action == "click_window_percent":
                input_ctl.click_window_percent(float(step["xPercent"]), float(step["yPercent"]))
            elif action == "double_click_window_percent":
                input_ctl.double_click_window_percent(float(step["xPercent"]), float(step["yPercent"]))
            elif action == "focus_target_window":
                input_ctl.focus_target_window()
            elif action == "press_sequence":
                input_ctl.press_sequence(list(step.get("keys", [])), float(step.get("intervalSeconds", 0.2)))
            elif action == "wait":
                if condition is None:
                    seconds = require_time_budget(deadline, float(step.get("seconds", 1)), "wait")
                    wait_for_seconds(config, seconds, stop_file)
            elif action == "collect_logs":
                collect_logs(config, artifact)
            elif action == "analyze_logs":
                analysis = analyze_run(config, artifact.run_dir, state_file)
                artifact.write_analysis(analysis)
            else:
                raise SafetyViolation(f"Unsupported scenario action: {action}")
            if time.monotonic() > deadline:
                raise SafetyViolation("Scenario maximum duration reached during a step.")
            artifact.append_timeline("step_end", index=index, action=action)
    except Exception as exc:
        status = "failed"
        error = str(exc)
        artifact.append_timeline("scenario_error", error=error, type=type(exc).__name__)
        try:
            collect_logs(config, artifact)
            analysis = analyze_run(config, artifact.run_dir, state_file)
            analysis["likelyRootCause"] = f"Scenario stopped: {error}. {analysis.get('likelyRootCause', '')}"
            analysis["safetyStop"] = isinstance(exc, SafetyViolation)
            artifact.write_analysis(analysis)
        except Exception as inner:
            artifact.append_timeline("failure_analysis_error", error=str(inner))
    artifact.append_timeline("scenario_end", status=status)
    return {"status": status, "error": error, "runDir": str(artifact.run_dir)}
