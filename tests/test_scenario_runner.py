from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from spt_vision_tester.scenario_runner import run_scenario


class ArtifactStub:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.timeline: list[tuple[str, dict]] = []

    def append_timeline(self, event: str, **fields: object) -> None:
        self.timeline.append((event, fields))

    def write_analysis(self, analysis: dict) -> None:
        pass


class ScenarioRunnerTests(unittest.TestCase):
    def test_conditional_wait_is_a_complete_action(self) -> None:
        scenario = {
            "schemaVersion": 1,
            "name": "conditional-wait-regression",
            "description": "Verify a completed wait condition is not treated as an unknown action.",
            "requiresComputerUse": False,
            "requiresKeyboardMouseInput": False,
            "requiresClientLaunch": False,
            "allowRaidAutomation": False,
            "maxSeconds": 30,
            "maxInputActions": 1,
            "steps": [
                {"action": "wait", "condition": "wait_for_window", "timeoutSeconds": 5}
            ],
        }
        config = SimpleNamespace(
            allow_computer_use=False,
            allow_keyboard_mouse_input=False,
            allow_raid_automation=False,
            scenario_max_seconds=30,
            max_input_actions=1,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = ArtifactStub(Path(temp_dir))
            with patch("spt_vision_tester.scenario_runner.InputController"), \
                 patch("spt_vision_tester.scenario_runner.assert_scenario_active"), \
                 patch("spt_vision_tester.scenario_runner.wait_for_window", return_value=True):
                result = run_scenario(config, scenario, artifact, Path(temp_dir) / "state.json")

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["error"])


if __name__ == "__main__":
    unittest.main()
