from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


class SafetyViolation(RuntimeError):
    pass


LOGIN_PATTERNS = (
    re.compile(r"\blogin\b", re.I),
    re.compile(r"\bsign\s*in\b", re.I),
    re.compile(r"\baccount\b", re.I),
    re.compile(r"\bpayment\b", re.I),
    re.compile(r"\bcaptcha\b", re.I),
    re.compile(r"\bbrowser\b", re.I),
    re.compile(r"battlestate", re.I),
)


@dataclass
class ProcessSnapshot:
    pid: int
    name: str
    exe: str | None


def assert_path_within_root(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SafetyViolation(f"Refusing executable outside SptRoot: {path}") from exc


def scan_denied_processes(denied_names: list[str]) -> list[ProcessSnapshot]:
    if psutil is None:
        return []
    denied = {name.lower() for name in denied_names}
    matches: list[ProcessSnapshot] = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info.get("name") or ""
            if name.lower() in denied:
                matches.append(ProcessSnapshot(proc.info["pid"], name, proc.info.get("exe")))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def assert_no_denied_processes(denied_names: list[str]) -> None:
    matches = scan_denied_processes(denied_names)
    if matches:
        names = ", ".join(f"{p.name}({p.pid})" for p in matches)
        raise SafetyViolation(f"Denied official/BattlEye process detected: {names}")


def assert_title_safe(title: str) -> None:
    for pattern in LOGIN_PATTERNS:
        if pattern.search(title or ""):
            raise SafetyViolation(f"Unsafe foreground/window title detected: {title}")
