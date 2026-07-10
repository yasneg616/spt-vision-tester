from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MAX_SCENARIO_SECONDS = 1800
MAX_SCENARIO_INPUT_ACTIONS = 300
MAX_STEPS = 500
MAX_WAIT_SECONDS = 300
MAX_HOLD_SECONDS = 10
MAX_SEQUENCE_KEYS = 20
MAX_MOUSE_DELTA = 1000

SUPPORTED_ACTIONS = {
    "analyze_logs",
    "click_center",
    "click_window_percent",
    "collect_logs",
    "double_click_window_percent",
    "focus_target_window",
    "hold",
    "move_mouse_relative",
    "press",
    "press_sequence",
    "screenshot",
    "wait",
}

INPUT_ACTIONS = {
    "click_center",
    "click_window_percent",
    "double_click_window_percent",
    "focus_target_window",
    "hold",
    "move_mouse_relative",
    "press",
    "press_sequence",
}

SUPPORTED_CONDITIONS = {
    "wait_for_log_quiet",
    "wait_for_seconds",
    "wait_for_stable_image",
    "wait_for_window",
}

SUPPORTED_KEYS = {
    "a",
    "alt",
    "b",
    "backspace",
    "c",
    "ctrl",
    "d",
    "delete",
    "down",
    "e",
    "end",
    "enter",
    "esc",
    "f",
    "f1",
    "f2",
    "f3",
    "f4",
    "f5",
    "f6",
    "f7",
    "f8",
    "f9",
    "f10",
    "f11",
    "f12",
    "g",
    "home",
    "left",
    "m",
    "n",
    "pagedown",
    "pageup",
    "q",
    "r",
    "right",
    "s",
    "shift",
    "space",
    "tab",
    "up",
    "v",
    "w",
    "x",
    "z",
}

TOP_LEVEL_FIELDS = {
    "$schema",
    "allowRaidAutomation",
    "description",
    "maxInputActions",
    "maxSeconds",
    "name",
    "notes",
    "requiresClientLaunch",
    "requiresComputerUse",
    "requiresKeyboardMouseInput",
    "requiresManualRaidEntry",
    "schemaVersion",
    "steps",
}

VERSIONED_REQUIRED_FIELDS = {
    "allowRaidAutomation",
    "description",
    "maxInputActions",
    "maxSeconds",
    "name",
    "requiresClientLaunch",
    "requiresComputerUse",
    "requiresKeyboardMouseInput",
    "schemaVersion",
    "steps",
}

ACTION_FIELDS = {
    "analyze_logs": {"action", "label"},
    "click_center": {"action", "label"},
    "click_window_percent": {"action", "label", "xPercent", "yPercent"},
    "collect_logs": {"action", "label"},
    "double_click_window_percent": {"action", "label", "xPercent", "yPercent"},
    "focus_target_window": {"action", "label"},
    "hold": {"action", "key", "label", "seconds"},
    "move_mouse_relative": {"action", "label", "x", "y"},
    "press": {"action", "key", "label"},
    "press_sequence": {"action", "intervalSeconds", "keys", "label"},
    "screenshot": {"action", "label"},
    "wait": {"action", "condition", "label", "seconds", "timeoutSeconds"},
}


class ScenarioValidationError(ValueError):
    pass


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _validate_number(
    errors: list[str],
    path: str,
    value: Any,
    minimum: float,
    maximum: float,
    *,
    integer: bool = False,
) -> None:
    if not _is_number(value):
        errors.append(f"{path} must be a finite number.")
        return
    if integer and not isinstance(value, int):
        errors.append(f"{path} must be an integer.")
        return
    if not minimum <= value <= maximum:
        errors.append(f"{path} must be between {minimum} and {maximum}.")


def _validate_key(errors: list[str], path: str, value: Any) -> None:
    if not isinstance(value, str) or value not in SUPPORTED_KEYS:
        errors.append(f"{path} must be one of: {', '.join(sorted(SUPPORTED_KEYS))}.")


def _input_cost(step: dict[str, Any]) -> int:
    action = step.get("action")
    if action == "press_sequence":
        keys = step.get("keys")
        return len(keys) if isinstance(keys, list) else 0
    return 1 if action in INPUT_ACTIONS else 0


def _validate_step(step: Any, index: int, errors: list[str]) -> int:
    path = f"steps[{index}]"
    if not isinstance(step, dict):
        errors.append(f"{path} must be an object.")
        return 0

    action = step.get("action")
    if not isinstance(action, str) or action not in SUPPORTED_ACTIONS:
        errors.append(f"{path}.action must be one of: {', '.join(sorted(SUPPORTED_ACTIONS))}.")
        return 0

    unknown = set(step) - ACTION_FIELDS[action]
    if unknown:
        errors.append(f"{path} contains unsupported fields for {action}: {', '.join(sorted(unknown))}.")

    label = step.get("label")
    if label is not None and (not isinstance(label, str) or not 1 <= len(label) <= 100):
        errors.append(f"{path}.label must be a string between 1 and 100 characters.")

    if action in {"press", "hold"}:
        if "key" not in step:
            errors.append(f"{path}.key is required for {action}.")
        else:
            _validate_key(errors, f"{path}.key", step["key"])

    if action == "press_sequence":
        keys = step.get("keys")
        if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_SEQUENCE_KEYS:
            errors.append(f"{path}.keys must contain 1 to {MAX_SEQUENCE_KEYS} supported keys.")
        else:
            for key_index, key in enumerate(keys):
                _validate_key(errors, f"{path}.keys[{key_index}]", key)
        if "intervalSeconds" in step:
            _validate_number(errors, f"{path}.intervalSeconds", step["intervalSeconds"], 0, 5)

    if action == "hold":
        if "seconds" not in step:
            errors.append(f"{path}.seconds is required for hold.")
        else:
            _validate_number(errors, f"{path}.seconds", step["seconds"], 0.05, MAX_HOLD_SECONDS)

    if action == "move_mouse_relative":
        for axis in ("x", "y"):
            if axis not in step:
                errors.append(f"{path}.{axis} is required for move_mouse_relative.")
            else:
                _validate_number(
                    errors,
                    f"{path}.{axis}",
                    step[axis],
                    -MAX_MOUSE_DELTA,
                    MAX_MOUSE_DELTA,
                    integer=True,
                )

    if action in {"click_window_percent", "double_click_window_percent"}:
        for field in ("xPercent", "yPercent"):
            if field not in step:
                errors.append(f"{path}.{field} is required for {action}.")
            else:
                _validate_number(errors, f"{path}.{field}", step[field], 0, 1)

    if action == "wait":
        condition = step.get("condition")
        if condition is not None and condition not in SUPPORTED_CONDITIONS:
            errors.append(f"{path}.condition must be one of: {', '.join(sorted(SUPPORTED_CONDITIONS))}.")
        if condition == "wait_for_window":
            if "timeoutSeconds" not in step:
                errors.append(f"{path}.timeoutSeconds is required for wait_for_window.")
            else:
                _validate_number(errors, f"{path}.timeoutSeconds", step["timeoutSeconds"], 0.1, MAX_WAIT_SECONDS)
            if "seconds" in step:
                errors.append(f"{path}.seconds is not used with wait_for_window.")
        else:
            if "seconds" not in step:
                errors.append(f"{path}.seconds is required for wait actions other than wait_for_window.")
            else:
                _validate_number(errors, f"{path}.seconds", step["seconds"], 0, MAX_WAIT_SECONDS)
            if "timeoutSeconds" in step:
                errors.append(f"{path}.timeoutSeconds is only valid with wait_for_window.")

    return _input_cost(step)


def validate_scenario(scenario: Any, *, require_schema_version: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(scenario, dict):
        return ["Scenario root must be a JSON object."]

    unknown = set(scenario) - TOP_LEVEL_FIELDS
    if unknown:
        errors.append(f"Scenario contains unsupported top-level fields: {', '.join(sorted(unknown))}.")

    required = VERSIONED_REQUIRED_FIELDS if require_schema_version else {"name", "steps"}
    missing = required - set(scenario)
    if missing:
        errors.append(f"Scenario is missing required fields: {', '.join(sorted(missing))}.")

    version = scenario.get("schemaVersion")
    if version is not None and version != SCHEMA_VERSION:
        errors.append(f"schemaVersion must be {SCHEMA_VERSION}.")

    schema_reference = scenario.get("$schema")
    if schema_reference is not None and (
        not isinstance(schema_reference, str) or not 1 <= len(schema_reference) <= 500
    ):
        errors.append("$schema must be a string between 1 and 500 characters.")

    name = scenario.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name):
        errors.append("name must be 1-64 lowercase letters, digits, dots, underscores, or hyphens.")

    description = scenario.get("description")
    if description is not None and (not isinstance(description, str) or not 1 <= len(description) <= 500):
        errors.append("description must be a string between 1 and 500 characters.")

    notes = scenario.get("notes")
    if notes is not None:
        if not isinstance(notes, list) or not 1 <= len(notes) <= 20:
            errors.append("notes must contain 1 to 20 strings.")
        elif any(not isinstance(note, str) or not 1 <= len(note) <= 500 for note in notes):
            errors.append("Each notes item must be a string between 1 and 500 characters.")

    boolean_fields = (
        "allowRaidAutomation",
        "requiresClientLaunch",
        "requiresComputerUse",
        "requiresKeyboardMouseInput",
        "requiresManualRaidEntry",
    )
    for field in boolean_fields:
        if field in scenario and not isinstance(scenario[field], bool):
            errors.append(f"{field} must be true or false.")

    if "maxSeconds" in scenario:
        _validate_number(errors, "maxSeconds", scenario["maxSeconds"], 1, MAX_SCENARIO_SECONDS)
    if "maxInputActions" in scenario:
        _validate_number(
            errors,
            "maxInputActions",
            scenario["maxInputActions"],
            0,
            MAX_SCENARIO_INPUT_ACTIONS,
            integer=True,
        )

    steps = scenario.get("steps")
    input_actions = 0
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        errors.append(f"steps must contain 1 to {MAX_STEPS} action objects.")
    else:
        for index, step in enumerate(steps):
            input_actions += _validate_step(step, index, errors)

    if input_actions:
        if scenario.get("requiresComputerUse") is not True:
            errors.append("Scenarios with input actions must set requiresComputerUse=true.")
        if scenario.get("requiresKeyboardMouseInput") is not True:
            errors.append("Scenarios with input actions must set requiresKeyboardMouseInput=true.")

    max_input_actions = scenario.get("maxInputActions")
    if isinstance(max_input_actions, int) and input_actions > max_input_actions:
        errors.append(
            f"Scenario declares maxInputActions={max_input_actions}, but its steps require at least {input_actions}."
        )

    max_seconds = scenario.get("maxSeconds")
    if _is_number(max_seconds) and isinstance(steps, list):
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            for field in ("seconds", "timeoutSeconds"):
                value = step.get(field)
                if _is_number(value) and value > max_seconds:
                    errors.append(f"steps[{index}].{field} cannot exceed maxSeconds={max_seconds}.")

    if scenario.get("allowRaidAutomation") is True:
        for field in ("requiresClientLaunch", "requiresComputerUse", "requiresKeyboardMouseInput"):
            if scenario.get(field) is not True:
                errors.append(f"Raid automation requires {field}=true.")
    if scenario.get("requiresManualRaidEntry") is True and scenario.get("allowRaidAutomation") is True:
        errors.append("requiresManualRaidEntry and allowRaidAutomation cannot both be true.")

    return errors


def assert_valid_scenario(scenario: Any, *, require_schema_version: bool = True) -> None:
    errors = validate_scenario(scenario, require_schema_version=require_schema_version)
    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise ScenarioValidationError(f"Scenario validation failed:\n{details}")


def scenario_summary(scenario: Any) -> dict[str, Any]:
    if not isinstance(scenario, dict):
        return {
            "schemaVersion": None,
            "name": None,
            "stepCount": 0,
            "estimatedInputActions": 0,
            "maxInputActions": None,
            "maxSeconds": None,
            "requirements": {},
            "actions": {},
        }
    raw_steps = scenario.get("steps", [])
    steps = raw_steps if isinstance(raw_steps, list) else []
    action_counts = Counter(
        step.get("action")
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("action"), str)
    )
    input_actions = sum(_input_cost(step) for step in steps if isinstance(step, dict))
    return {
        "schemaVersion": scenario.get("schemaVersion"),
        "name": scenario.get("name"),
        "stepCount": len(steps),
        "estimatedInputActions": input_actions,
        "maxInputActions": scenario.get("maxInputActions"),
        "maxSeconds": scenario.get("maxSeconds"),
        "requirements": {
            "clientLaunch": bool(scenario.get("requiresClientLaunch")),
            "computerUse": bool(scenario.get("requiresComputerUse")),
            "keyboardMouseInput": bool(scenario.get("requiresKeyboardMouseInput")),
            "manualRaidEntry": bool(scenario.get("requiresManualRaidEntry")),
            "raidAutomation": bool(scenario.get("allowRaidAutomation")),
        },
        "actions": dict(sorted(action_counts.items())),
    }


def load_scenario_file(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8-sig"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spt-vision-scenario-validator")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--allow-legacy-without-version", action="store_true")
    args = parser.parse_args(argv)

    try:
        scenario = load_scenario_file(args.scenario)
        errors = validate_scenario(
            scenario,
            require_schema_version=not args.allow_legacy_without_version,
        )
        payload = {
            "ok": not errors,
            "scenarioPath": str(Path(args.scenario).expanduser().resolve()),
            "summary": scenario_summary(scenario),
            "errors": errors,
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "scenarioPath": str(Path(args.scenario).expanduser()),
            "errors": [str(exc)],
        }

    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
