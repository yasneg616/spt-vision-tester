from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from spt_vision_tester.desktop_coordinator import DesktopContext
from spt_vision_tester.input_controller import InputController
from spt_vision_tester.safety import SafetyViolation


class ArtifactStub:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.events: list[tuple[str, dict[str, object]]] = []

    def append_timeline(self, event: str, **details: object) -> None:
        self.events.append((event, details))


def make_config() -> SimpleNamespace:
    return SimpleNamespace(
        allow_computer_use=True,
        allow_keyboard_mouse_input=True,
        cooperative_desktop_mode=True,
        denied_process_names=[],
        max_input_actions=20,
        scenario_max_seconds=60.0,
    )


class InputControllerTests(unittest.TestCase):
    def test_focus_interruption_is_deferred_without_claiming_user_input(self) -> None:
        target = SimpleNamespace(hwnd=200)
        user_window = SimpleNamespace(hwnd=300)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = ArtifactStub(Path(temp_dir))
            controller = InputController(make_config(), artifact)
            controller.last_injected_input_tick = 77

            with patch("spt_vision_tester.input_controller.pyautogui", object()), \
                 patch("spt_vision_tester.input_controller.wait_for_user_idle"), \
                 patch(
                     "spt_vision_tester.input_controller.capture_desktop_context",
                     return_value=DesktopContext(foreground_hwnd=100, cursor_position=(10, 20)),
                 ), \
                 patch("spt_vision_tester.input_controller.activate_target_window", return_value=target), \
                 patch("spt_vision_tester.input_controller.capture_window"), \
                 patch("spt_vision_tester.input_controller.active_window", return_value=user_window), \
                 patch("spt_vision_tester.input_controller.last_input_tick", side_effect=[80, 81]), \
                 patch(
                     "spt_vision_tester.input_controller.restore_desktop_context",
                     return_value={"focus": "kept_user_change", "cursor": "unchanged"},
                 ):
                controller.focus_target_window()

        self.assertEqual(controller.actions, 1)
        self.assertEqual(controller.last_injected_input_tick, 77)
        deferred = [details for event, details in artifact.events if event == "cooperative_interruption_deferred"]
        self.assertEqual(deferred[0]["reasons"], ["focus_changed", "user_input_detected"])

    def test_click_interruption_remains_a_safety_violation(self) -> None:
        target = SimpleNamespace(hwnd=200, left=0, top=0, width=1000, height=800)
        user_window = SimpleNamespace(hwnd=300)
        click = Mock()

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = ArtifactStub(Path(temp_dir))
            controller = InputController(make_config(), artifact)

            with patch("spt_vision_tester.input_controller.pyautogui", SimpleNamespace(click=click)), \
                 patch("spt_vision_tester.input_controller.wait_for_user_idle"), \
                 patch(
                     "spt_vision_tester.input_controller.capture_desktop_context",
                     side_effect=[
                         DesktopContext(foreground_hwnd=100, cursor_position=(10, 20)),
                         DesktopContext(foreground_hwnd=200, cursor_position=(925, 724)),
                     ],
                 ), \
                 patch("spt_vision_tester.input_controller.activate_target_window", return_value=target), \
                 patch("spt_vision_tester.input_controller.assert_foreground_allowed", return_value=target), \
                 patch("spt_vision_tester.input_controller.capture_window"), \
                 patch("spt_vision_tester.input_controller.active_window", return_value=user_window), \
                 patch("spt_vision_tester.input_controller.last_input_tick", side_effect=[80, 81]), \
                 patch(
                     "spt_vision_tester.input_controller.restore_desktop_context",
                     return_value={"focus": "kept_user_change", "cursor": "kept_user_change"},
                 ):
                with self.assertRaisesRegex(SafetyViolation, "Foreground changed during cooperative input"):
                    controller.click_window_percent(0.925, 0.905)

        click.assert_called_once_with(x=925, y=724)


if __name__ == "__main__":
    unittest.main()
