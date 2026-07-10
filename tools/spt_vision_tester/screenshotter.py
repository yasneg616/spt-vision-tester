from __future__ import annotations

from pathlib import Path
import time
from typing import Any

try:
    import mss
except Exception:  # pragma: no cover
    mss = None

try:
    from PIL import ImageGrab
except Exception:  # pragma: no cover
    ImageGrab = None

from .artifact_writer import ArtifactWriter
from .safety import SafetyViolation
from .window_finder import (
    WindowInfo,
    active_window,
    activate_target_window,
    assert_window_on_target_monitor,
    find_target_window,
)


def capture_window(artifact: ArtifactWriter, config: Any, label: str | None = None) -> dict[str, Any]:
    info: WindowInfo | None = find_target_window(config)
    output = artifact.next_screenshot_path(label)
    risk = None
    if info is None:
        raise SafetyViolation("Unable to find an allowed SPT window for screenshot capture.")
    assert_window_on_target_monitor(config, info)
    if info and mss is not None and info.width > 0 and info.height > 0:
        active = active_window()
        if not active or active.pid != info.pid:
            if config.cooperative_desktop_mode:
                risk = "Background screen-region capture may include an occluding window; prefer Computer Use window capture."
            else:
                activate_target_window(config)
                time.sleep(0.2)
                active = active_window()
                if not active or active.pid != info.pid:
                    raise SafetyViolation("Refusing screenshot capture because the SPT target window is not foreground.")
        with mss.mss() as sct:
            monitor = {"left": info.left, "top": info.top, "width": info.width, "height": info.height}
            image = sct.grab(monitor)
            from PIL import Image

            Image.frombytes("RGB", image.size, image.rgb).save(output)
    elif ImageGrab is not None and info.width > 0 and info.height > 0:
        bbox = (info.left, info.top, info.left + info.width, info.top + info.height)
        ImageGrab.grab(bbox=bbox, all_screens=True).save(output)
        risk = "Used bounded screen-region fallback; an occluding window may be visible."
    else:
        raise RuntimeError("No screenshot backend available. Install mss and pillow.")
    meta = {
        "path": str(output),
        "windowTitle": info.title if info else None,
        "processName": info.process_name if info else None,
        "processPath": info.process_path if info else None,
        "pid": info.pid if info else None,
        "monitorIndex": info.monitor_index if info else None,
        "monitorDeviceName": info.monitor_device_name if info else None,
        "targetMonitorCoverage": info.target_monitor_coverage if info else None,
        "risk": risk,
    }
    artifact.append_timeline("screenshot", **meta)
    return meta


def latest_screenshot(run_dir: Path) -> Path | None:
    shots = sorted((run_dir / "screenshots").glob("*.png"))
    return shots[-1] if shots else None
