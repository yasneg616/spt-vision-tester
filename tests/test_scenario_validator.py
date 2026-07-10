from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from spt_vision_tester.scenario_validator import scenario_summary, validate_scenario


VALID_SCENARIO = {
    "schemaVersion": 1,
    "name": "custom-navigation-check",
    "description": "A bounded local SPT navigation example.",
    "requiresComputerUse": True,
    "requiresKeyboardMouseInput": True,
    "requiresClientLaunch": False,
    "allowRaidAutomation": False,
    "maxSeconds": 30,
    "maxInputActions": 4,
    "steps": [
        {"action": "focus_target_window"},
        {"action": "screenshot", "label": "before"},
        {"action": "press", "key": "tab"},
        {"action": "wait", "seconds": 1},
        {"action": "press", "key": "tab"},
        {"action": "screenshot", "label": "after"},
    ],
}


class ScenarioValidatorTests(unittest.TestCase):
    def test_valid_scenario(self) -> None:
        self.assertEqual(validate_scenario(VALID_SCENARIO), [])

    def test_rejects_unknown_action(self) -> None:
        scenario = copy.deepcopy(VALID_SCENARIO)
        scenario["steps"][0] = {"action": "run_shell", "command": "whoami"}
        errors = validate_scenario(scenario)
        self.assertTrue(any("action must be one of" in error for error in errors))

    def test_rejects_arbitrary_step_fields(self) -> None:
        scenario = copy.deepcopy(VALID_SCENARIO)
        scenario["steps"][1]["path"] = "C:\\private"
        errors = validate_scenario(scenario)
        self.assertTrue(any("unsupported fields" in error for error in errors))

    def test_rejects_out_of_bounds_click(self) -> None:
        scenario = copy.deepcopy(VALID_SCENARIO)
        scenario["steps"][1] = {
            "action": "click_window_percent",
            "xPercent": 1.2,
            "yPercent": 0.5,
        }
        errors = validate_scenario(scenario)
        self.assertTrue(any("xPercent" in error for error in errors))

    def test_rejects_too_small_input_budget(self) -> None:
        scenario = copy.deepcopy(VALID_SCENARIO)
        scenario["maxInputActions"] = 2
        errors = validate_scenario(scenario)
        self.assertTrue(any("require at least" in error for error in errors))

    def test_requires_version_for_public_interface(self) -> None:
        scenario = copy.deepcopy(VALID_SCENARIO)
        del scenario["schemaVersion"]
        errors = validate_scenario(scenario)
        self.assertTrue(any("schemaVersion" in error for error in errors))

    def test_rejects_step_longer_than_scenario_budget(self) -> None:
        scenario = copy.deepcopy(VALID_SCENARIO)
        scenario["steps"][3]["seconds"] = 31
        errors = validate_scenario(scenario)
        self.assertTrue(any("cannot exceed maxSeconds" in error for error in errors))

    def test_invalid_step_can_still_be_summarized(self) -> None:
        scenario = copy.deepcopy(VALID_SCENARIO)
        scenario["steps"].append({"label": "missing-action"})
        summary = scenario_summary(scenario)
        self.assertEqual(summary["stepCount"], len(scenario["steps"]))

    def test_all_bundled_scenarios_are_valid(self) -> None:
        scenarios_dir = Path(__file__).resolve().parents[1] / "config" / "scenarios"
        for scenario_path in scenarios_dir.glob("*.json"):
            if scenario_path.name.endswith(".schema.json"):
                continue
            with self.subTest(scenario=scenario_path.name):
                import json

                scenario = json.loads(scenario_path.read_text(encoding="utf-8-sig"))
                self.assertEqual(validate_scenario(scenario), [])


if __name__ == "__main__":
    unittest.main()
