from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageStat
except Exception:  # pragma: no cover
    Image = None
    ImageStat = None

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

from .config import VisionConfig
from .log_collector import scan_logs
from .window_finder import active_window


def detect_black_screen(image_path: Path, threshold: float = 8.0) -> dict[str, Any] | None:
    if Image is None or ImageStat is None or not image_path:
        return None
    try:
        image = Image.open(image_path).convert("L")
        stat = ImageStat.Stat(image)
        mean = stat.mean[0]
        if mean < threshold:
            return {"type": "black_screen", "image": str(image_path), "meanBrightness": mean}
    except Exception as exc:
        return {"type": "image_check_failed", "image": str(image_path), "error": str(exc)}
    return None


def detect_static_image(previous: Path | None, current: Path | None) -> dict[str, Any] | None:
    if Image is None or not previous or not current or previous == current:
        return None
    try:
        a = Image.open(previous).resize((64, 64)).convert("L")
        b = Image.open(current).resize((64, 64)).convert("L")
        diff = sum(abs(x - y) for x, y in zip(a.tobytes(), b.tobytes())) / (64 * 64)
        if diff < 0.5:
            return {"type": "static_image", "previous": str(previous), "current": str(current), "diff": diff}
    except Exception as exc:
        return {"type": "image_diff_failed", "error": str(exc)}
    return None


def detect_window_focus(config: VisionConfig) -> dict[str, Any] | None:
    window = active_window()
    if not window:
        return {"type": "window_lost_focus", "detail": "No active window found."}
    if window.process_name and window.process_name not in config.allowed_process_names:
        return {"type": "window_lost_focus", "processName": window.process_name, "titleRedacted": True}
    return None


def detect_crashed_processes(state_file: Path) -> list[dict[str, Any]]:
    if psutil is None or not state_file.exists():
        return []
    records = json.loads(state_file.read_text(encoding="utf-8-sig") or "[]")
    findings = []
    for record in records:
        pid = int(record["pid"])
        if not psutil.pid_exists(pid):
            findings.append({"type": "process_exited", "pid": pid, "role": record.get("role")})
    return findings


def analyze_run(config: VisionConfig, run_dir: Path, state_file: Path | None = None) -> dict[str, Any]:
    evidence: list[str] = []
    detector_json = run_dir / "detectors.json"
    findings: list[dict[str, Any]] = []
    screenshots = sorted((run_dir / "screenshots").glob("*.png"))
    if screenshots:
        black = detect_black_screen(screenshots[-1])
        if black:
            findings.append(black)
        if len(screenshots) >= 2:
            static = detect_static_image(screenshots[-2], screenshots[-1])
            if static:
                findings.append(static)
    focus = detect_window_focus(config)
    if focus:
        findings.append(focus)
    if state_file:
        findings.extend(detect_crashed_processes(state_file))
    log_findings = scan_logs(run_dir)
    for item in findings[:20]:
        evidence.append(json.dumps(item, ensure_ascii=False))
    for item in log_findings[:20]:
        evidence.append(f"{item['logKind']} {item['file']}:{item['lineNumber']} {item['lineText']}")
    if log_findings:
        root = "A log error or mod load failure is likely. Inspect the earliest evidence line first."
    elif any(f.get("type") == "black_screen" for f in findings):
        root = "The latest screenshot appears black; inspect rendering, loading state, and client logs."
    elif any(f.get("type") == "window_lost_focus" for f in findings):
        root = "The target window lost focus or a non-allowed foreground window appeared."
    elif any(f.get("type") == "process_exited" for f in findings):
        root = "A recorded SPT process exited during the test."
    else:
        root = "No obvious severe issue was detected by simple screenshot/log detectors."
    detector_json.write_text(json.dumps({"findings": findings, "logFindings": log_findings[:100]}, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "likelyRootCause": root,
        "safetyStop": bool(focus),
        "evidence": evidence,
        "suggestedNextInspection": "Review timeline.jsonl, screenshots, manifest.json, and the first log evidence above.",
        "detectorsPath": str(detector_json),
        "logFindingCount": len(log_findings),
    }
