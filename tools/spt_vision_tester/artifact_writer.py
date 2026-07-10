from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactWriter:
    def __init__(self, artifacts_root: Path, scenario_name: str | None = None):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = f"-{scenario_name}" if scenario_name else ""
        self.run_dir = (artifacts_root / f"{stamp}{suffix}").resolve()
        self.screenshots_dir = self.run_dir / "screenshots"
        self.logs_dir = self.run_dir / "logs"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.timeline_path = self.run_dir / "timeline.jsonl"
        self.run_json_path = self.run_dir / "run.json"
        self.analysis_json_path = self.run_dir / "analysis.json"
        self.analysis_md_path = self.run_dir / "analysis.md"
        self._screenshot_index = 0

    def write_run(self, payload: dict[str, Any]) -> None:
        data = {"updatedAtUtc": utc_now(), **payload}
        self.run_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def append_timeline(self, event: str, **payload: Any) -> None:
        entry = {"timeUtc": utc_now(), "event": event, **payload}
        with self.timeline_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def next_screenshot_path(self, label: str | None = None) -> Path:
        self._screenshot_index += 1
        clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (label or "step"))
        return self.screenshots_dir / f"step_{self._screenshot_index:04d}_{clean}.png"

    def write_analysis(self, analysis: dict[str, Any]) -> None:
        self.analysis_json_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = [
            "# SPT Vision Test Analysis",
            "",
            f"- Run: `{self.run_dir}`",
            f"- Analyzed at UTC: {utc_now()}",
            f"- Likely root cause: {analysis.get('likelyRootCause', 'Unknown')}",
            f"- Safety stop: {analysis.get('safetyStop', False)}",
            "",
            "## Evidence",
            "",
        ]
        evidence = analysis.get("evidence", [])
        if not evidence:
            lines.append("No high-signal evidence was found.")
        else:
            for item in evidence:
                lines.append(f"- {item}")
        lines.extend(["", "## Suggested next inspection", "", analysis.get("suggestedNextInspection", "Review timeline and logs.")])
        self.analysis_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
