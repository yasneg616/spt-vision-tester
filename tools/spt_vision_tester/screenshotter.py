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
from .window_finder import WindowInfo, active_window, activate_target_window, find_target_window


def capture_window(artifact: ArtifactWriter, config: Any, label: str | None = None) -> dict[str, Any]:
    info: WindowInfo | None = find_target_window(config)
    output = artifact.next_screenshot_path(label)
    risk = None
    if info and mss is not None and info.width > 0 and info.height > 0:
        active = active_window()
        if not active or active.pid != info.pid:
            activate_target_window(config)
            time.sleep(0.2)
            active = active_window()
        if not active or active.pid != info.pid:
            raise SafetyViolation("Refusing to screenshot target coordinates while the SPT target window is not foreground.")
        with mss.mss() as sct:
            monitor = {"left": info.left, "top": info.top, "width": info.width, "height": info.height}
            image = sct.grab(monitor)
            from PIL import Image

            Image.frombytes("RGB", image.size, image.rgb).save(output)
    elif ImageGrab is not None:
        ImageGrab.grab().save(output)
        risk = "Fell back to foreground/fullscreen capture because target window capture was unavailable."
    else:
        raise RuntimeError("No screenshot backend available. Install mss and pillow.")
    meta = {
        "path": str(output),
        "windowTitle": info.title if info else None,
        "processName": info.process_name if info else None,
        "pid": info.pid if info else None,
        "risk": risk,
    }
    artifact.append_timeline("screenshot", **meta)
    return meta


def latest_screenshot(run_dir: Path) -> Path | None:
    shots = sorted((run_dir / "screenshots").glob("*.png"))
    return shots[-1] if shots else None
