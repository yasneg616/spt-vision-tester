from __future__ import annotations

import fnmatch
import json
import shutil
from pathlib import Path
from typing import Any

from .artifact_writer import ArtifactWriter
from .config import VisionConfig


def log_kind(path: Path) -> str:
    lower = str(path).lower()
    if "bepinex" in lower:
        return "bepinex"
    if "server" in lower or "spt_data" in lower or "backend" in lower:
        return "server"
    if "client" in lower or "application" in lower or "errors" in lower or "escapefromtarkov" in lower:
        return "client"
    return "unknown"


def tail_copy(source: Path, destination: Path, tail_bytes: int) -> str:
    if source.stat().st_size <= tail_bytes:
        shutil.copy2(source, destination)
        return "full"
    with source.open("rb") as src:
        src.seek(max(0, source.stat().st_size - tail_bytes))
        with destination.open("wb") as dst:
            dst.write(src.read())
    return "tail"


def collect_logs(config: VisionConfig, artifact: ArtifactWriter, max_files: int = 80, tail_bytes: int = 1_048_576) -> list[dict[str, Any]]:
    matches: list[Path] = []
    for pattern in config.log_globs:
        matches.extend(config.spt_root.glob(pattern))
    unique = sorted({p.resolve() for p in matches if p.is_file()}, key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    manifest: list[dict[str, Any]] = []
    for index, source in enumerate(unique, 1):
        rel = source.relative_to(config.spt_root) if source.is_relative_to(config.spt_root) else source.name
        safe = "_".join(Path(rel).parts).replace(":", "_")
        destination = artifact.logs_dir / f"{index:03d}_{safe}"
        mode = tail_copy(source, destination, tail_bytes)
        manifest.append({
            "originalPath": str(source),
            "collectedPath": str(destination),
            "sizeBytes": source.stat().st_size,
            "modifiedTime": source.stat().st_mtime,
            "copyMode": mode,
            "logKind": log_kind(source),
        })
    manifest_path = artifact.run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    artifact.append_timeline("collect_logs", count=len(manifest), manifest=str(manifest_path))
    return manifest


KEYWORDS = (
    "ERROR",
    "Exception",
    "Fatal",
    "NullReference",
    "Harmony",
    "missing",
    "incompatible",
    "failed",
    "cannot find",
    "dependency",
)


def scan_logs(run_dir: Path, context_lines: int = 3) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    logs_dir = run_dir / "logs"
    for path in logs_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for idx, line in enumerate(lines):
            if not any(k.lower() in line.lower() for k in KEYWORDS):
                continue
            start = max(0, idx - context_lines)
            end = min(len(lines), idx + context_lines + 1)
            findings.append({
                "file": str(path),
                "logKind": log_kind(path),
                "lineNumber": idx + 1,
                "lineText": line,
                "context": lines[start:end],
            })
    return findings
