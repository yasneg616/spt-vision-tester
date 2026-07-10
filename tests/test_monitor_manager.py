from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from spt_vision_tester.monitor_manager import (
    MonitorInfo,
    coverage_ratio,
    select_target_monitor,
    validate_monitor_configuration,
)
from spt_vision_tester.safety import SafetyViolation


def monitor(index: int, device: str, primary: bool, bounds: tuple[int, int, int, int]) -> MonitorInfo:
    left, top, right, bottom = bounds
    return MonitorInfo(
        index=index,
        handle=index * 10,
        device_name=device,
        primary=primary,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        work_left=left,
        work_top=top,
        work_right=right,
        work_bottom=bottom,
    )


MONITORS = [
    monitor(1, r"\\.\DISPLAY2", True, (0, 0, 3840, 2160)),
    monitor(2, r"\\.\DISPLAY1", False, (-2560, 1022, 0, 2462)),
    monitor(3, r"\\.\DISPLAY3", False, (-2560, -603, 0, 997)),
]


class MonitorManagerTests(unittest.TestCase):
    def test_selects_matching_index_and_device(self) -> None:
        config = SimpleNamespace(target_monitor_index=2, target_monitor_device_name=r"\\.\DISPLAY1")
        self.assertEqual(select_target_monitor(config, MONITORS), MONITORS[1])

    def test_rejects_index_device_mismatch(self) -> None:
        config = SimpleNamespace(target_monitor_index=2, target_monitor_device_name=r"\\.\DISPLAY3")
        with self.assertRaises(SafetyViolation):
            select_target_monitor(config, MONITORS)

    def test_rejects_negative_monitor_index(self) -> None:
        config = SimpleNamespace(target_monitor_index=-1, target_monitor_device_name="")
        with self.assertRaises(SafetyViolation):
            select_target_monitor(config, MONITORS)

    def test_calculates_monitor_coverage(self) -> None:
        self.assertEqual(coverage_ratio((-2560, 1022, 0, 2462), MONITORS[1]), 1.0)
        self.assertEqual(coverage_ratio((0, 0, 100, 100), MONITORS[1]), 0.0)

    def test_cooperative_mode_requires_monitor_enforcement(self) -> None:
        config = SimpleNamespace(
            target_monitor_index=2,
            target_monitor_device_name=r"\\.\DISPLAY1",
            target_window_placement="preserve",
            target_monitor_min_coverage=0.9,
            cooperative_desktop_mode=True,
            move_target_window_to_monitor=True,
            require_target_window_on_monitor=False,
            user_idle_seconds_before_input=1.0,
            max_user_idle_wait_seconds=30.0,
        )
        with patch("spt_vision_tester.monitor_manager.list_monitors", return_value=MONITORS):
            with self.assertRaises(SafetyViolation):
                validate_monitor_configuration(config)


if __name__ == "__main__":
    unittest.main()
