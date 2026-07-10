from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from spt_vision_tester.window_finder import _allowed_process


class WindowFinderTests(unittest.TestCase):
    def test_allowed_window_process_must_be_under_spt_root(self) -> None:
        config = SimpleNamespace(
            allowed_process_names=["SPT.Launcher.exe"],
            spt_root=Path(r"C:\spt-fixture"),
        )
        self.assertTrue(
            _allowed_process(
                config,
                "SPT.Launcher.exe",
                r"C:\spt-fixture\SPT.Launcher.exe",
            )
        )
        self.assertFalse(
            _allowed_process(
                config,
                "SPT.Launcher.exe",
                r"C:\other-folder\SPT.Launcher.exe",
            )
        )


if __name__ == "__main__":
    unittest.main()
