from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

from .config import VisionConfig
from .safety import SafetyViolation, assert_no_denied_processes, assert_path_within_root


class ProcessGuard:
    def __init__(self, config: VisionConfig, state_file: Path):
        self.config = config
        self.state_file = state_file.resolve()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def validate_spt_root(self) -> list[str]:
        if not self.config.spt_root.is_dir():
            raise SafetyViolation(f"SptRoot does not exist: {self.config.spt_root}")
        markers = [
            "user",
            "BepInEx",
            "SPT",
            "SPT_Data",
            "SPT.Server.exe",
            "Aki.Server.exe",
            "SPT.Launcher.exe",
            "Aki.Launcher.exe",
            "EscapeFromTarkov.exe",
            "sptLogger.json",
        ]
        found = [m for m in markers if (self.config.spt_root / m).exists()]
        server_path = self.config.server_path()
        launcher_path = self.config.launcher_path()
        has_user_or_bepinex = any(m in found for m in ("user", "BepInEx"))
        has_server = (
            any(m in found for m in ("SPT.Server.exe", "Aki.Server.exe", "SPT_Data", "sptLogger.json"))
            or server_path is not None
        )
        if server_path:
            assert_path_within_root(server_path, self.config.spt_root)
            found.append(str(server_path.relative_to(self.config.spt_root)))
        if launcher_path:
            assert_path_within_root(launcher_path, self.config.spt_root)
            found.append(str(launcher_path.relative_to(self.config.spt_root)))
        if len(found) < 2 or not has_user_or_bepinex or not has_server:
            raise SafetyViolation(f"Refusing to run: SptRoot is not confirmed as local SPT offline install. Found: {found}")
        return found

    def _load_state(self) -> list[dict[str, Any]]:
        if not self.state_file.exists():
            return []
        text = self.state_file.read_text(encoding="utf-8-sig").strip()
        return json.loads(text) if text else []

    def _write_state(self, records: list[dict[str, Any]]) -> None:
        self.state_file.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def record_process(self, process: subprocess.Popen[Any], role: str, exe_path: Path) -> None:
        records = self._load_state()
        records.append({
            "pid": process.pid,
            "role": role,
            "path": str(exe_path),
            "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        self._write_state(records)

    def launch(self, role: str, exe_path: Path) -> subprocess.Popen[Any]:
        assert_no_denied_processes(self.config.denied_process_names)
        assert_path_within_root(exe_path, self.config.spt_root)
        if exe_path.name not in self.config.allowed_process_names:
            raise SafetyViolation(f"Executable is not in AllowedProcessNames: {exe_path.name}")
        creationflags = 0
        if role == "server" and os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        proc = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent), creationflags=creationflags)
        self.record_process(proc, role, exe_path)
        return proc

    def wait_for_server(self) -> bool:
        parsed = urllib.parse.urlparse(self.config.server_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        deadline = time.monotonic() + self.config.startup_timeout_seconds
        while time.monotonic() < deadline:
            assert_no_denied_processes(self.config.denied_process_names)
            try:
                with urllib.request.urlopen(self.config.server_url, timeout=3):
                    return True
            except Exception:
                try:
                    with socket.create_connection((host, port), timeout=3):
                        return True
                except OSError:
                    pass
                time.sleep(2)
        return False

    def stop_recorded(self) -> list[dict[str, Any]]:
        records = self._load_state()
        results: list[dict[str, Any]] = []
        records_to_stop = list(records)
        seen = {int(record["pid"]) for record in records_to_stop if "pid" in record}
        if psutil is not None:
            for record in records:
                try:
                    parent = psutil.Process(int(record["pid"]))
                    for child in parent.children(recursive=True):
                        if child.pid in seen:
                            continue
                        try:
                            child_path = Path(child.exe()).resolve()
                            assert_path_within_root(child_path, self.config.spt_root)
                        except Exception:
                            continue
                        if child.name() not in self.config.allowed_process_names:
                            continue
                        records_to_stop.append({
                            "pid": child.pid,
                            "role": "child",
                            "path": str(child_path),
                            "parentPid": parent.pid,
                        })
                        seen.add(child.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        for record in records_to_stop:
            pid = int(record["pid"])
            role = record.get("role", "unknown")
            if psutil is None:
                results.append({"pid": pid, "role": role, "status": "skipped", "detail": "psutil unavailable"})
                continue
            try:
                proc = psutil.Process(pid)
                expected_path = record.get("path")
                if not expected_path:
                    results.append({"pid": pid, "role": role, "status": "identity_unverified", "detail": "Recorded path is missing."})
                    continue
                try:
                    current_path = proc.exe()
                except psutil.AccessDenied as exc:
                    results.append({"pid": pid, "role": role, "status": "identity_unverified", "detail": str(exc)})
                    continue
                if os.path.normcase(str(Path(current_path).resolve())) != os.path.normcase(str(Path(expected_path).resolve())):
                    results.append({
                        "pid": pid,
                        "role": role,
                        "status": "identity_mismatch",
                        "expectedPath": expected_path,
                        "actualPath": current_path,
                    })
                    continue
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                    status = "stopped"
                except psutil.TimeoutExpired:
                    status = "still_running"
                results.append({"pid": pid, "role": role, "status": status})
            except psutil.NoSuchProcess:
                results.append({"pid": pid, "role": role, "status": "not_running"})
            except psutil.AccessDenied as exc:
                results.append({"pid": pid, "role": role, "status": "failed", "detail": str(exc)})
        remaining_pids = {
            int(result["pid"])
            for result in results
            if result.get("status") in {"failed", "still_running", "identity_unverified"}
        }
        remaining_records = [record for record in records if int(record["pid"]) in remaining_pids]
        self._write_state(remaining_records)
        return results
