from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .artifact_writer import ArtifactWriter
from .config import VisionConfig, load_scenario
from .detectors import analyze_run
from .log_collector import collect_logs
from .monitor_manager import list_monitors, validate_monitor_configuration
from .process_guard import ProcessGuard
from .safety import SafetyViolation, assert_no_denied_processes
from .scenario_runner import run_scenario
from .scenario_validator import assert_valid_scenario, scenario_summary, validate_scenario
from .window_finder import assert_window_on_target_monitor, find_target_window, position_target_window


def state_file_for(config: VisionConfig) -> Path:
    return config.artifacts_root.parent / "started-processes.json"


def command_run(args: argparse.Namespace) -> int:
    config = VisionConfig.load(args.config)
    default_name = "computer-use-session" if args.computer_use_session else "server-only"
    scenario = load_scenario(args.scenario) if args.scenario else {"name": default_name, "steps": []}
    artifact = ArtifactWriter(config.artifacts_root, scenario.get("name"))
    state_file = state_file_for(config)
    guard = ProcessGuard(config, state_file)
    summary: dict[str, object] = {
        "ok": False,
        "runDir": str(artifact.run_dir),
        "stateFile": str(state_file),
        "scenario": scenario.get("name"),
        "started": [],
    }
    try:
        if args.computer_use_session and (args.server_only or args.scenario):
            raise SafetyViolation("Computer Use session cannot be combined with server-only or a scenario file.")
        if not args.server_only and not args.computer_use_session and not args.scenario:
            raise SafetyViolation("A scenario is required unless using server-only or Computer Use session mode.")
        if args.scenario:
            assert_valid_scenario(scenario, require_schema_version=args.require_scenario_schema)
            summary["scenarioValidation"] = scenario_summary(scenario)
        if not args.server_only:
            summary["monitorPolicy"] = validate_monitor_configuration(
                config,
                require_target=args.computer_use_session,
            )
        markers = guard.validate_spt_root()
        assert_no_denied_processes(config.denied_process_names)
        server_path = config.server_path()
        if not server_path:
            raise SafetyViolation("Server executable was not found under SptRoot.")
        server_proc = guard.launch("server", server_path)
        summary["started"] = [{"role": "server", "pid": server_proc.pid, "path": str(server_path)}]
        server_ready = guard.wait_for_server()
        summary["serverReady"] = server_ready
        if not server_ready and (args.launch_client or scenario.get("requiresClientLaunch")):
            raise SafetyViolation(f"ServerUrl was not reachable before timeout: {config.server_url}")
        if scenario.get("requiresClientLaunch") and not args.launch_client:
            raise SafetyViolation("Scenario requires client launch. Re-run with -LaunchClient or -AutoRaid.")
        if args.launch_client and not args.server_only:
            if not config.allow_client_launch:
                raise SafetyViolation("Client launch requested but AllowClientLaunch=false.")
            target = config.launcher_path() if config.open_launcher_instead_of_client else config.client_path()
            if not target:
                raise SafetyViolation("Launcher/client executable was not found under SptRoot.")
            role = "launcher" if config.open_launcher_instead_of_client else "client"
            proc = guard.launch(role, target)
            summary["started"].append({"role": role, "pid": proc.pid, "path": str(target)})
        if args.server_only:
            if args.collect_logs:
                collect_logs(config, artifact)
            if args.analyze_logs:
                analysis = analyze_run(config, artifact.run_dir, state_file)
                artifact.write_analysis(analysis)
            result = {"status": "ok", "runDir": str(artifact.run_dir), "serverOnly": True}
        elif args.computer_use_session:
            if not args.launch_client:
                raise SafetyViolation("Computer Use session requires client/launcher launch.")
            if not config.allow_computer_use:
                raise SafetyViolation("Computer Use session requires AllowComputerUse=true.")
            deadline = time.monotonic() + config.client_boot_timeout_seconds
            window = None
            while time.monotonic() < deadline:
                assert_no_denied_processes(config.denied_process_names)
                window = find_target_window(config)
                if window:
                    break
                time.sleep(1)
            if window is None:
                raise SafetyViolation("Timed out waiting for a targetable local SPT launcher/client window.")
            placement = None
            if config.move_target_window_to_monitor:
                window, placement = position_target_window(config)
            assert_window_on_target_monitor(config, window)
            if args.collect_logs:
                collect_logs(config, artifact)
            if args.analyze_logs:
                analysis = analyze_run(config, artifact.run_dir, state_file)
                artifact.write_analysis(analysis)
            result = {
                "status": "ok",
                "runDir": str(artifact.run_dir),
                "computerUseSession": True,
                "inputIsolation": False,
                "concurrentUseWarning": (
                    "Computer Use window snapshots can remain backgrounded, but every click/key activates the SPT window "
                    "and uses the shared Windows input desktop."
                ),
                "targetWindow": {
                    "processName": window.process_name,
                    "processPath": window.process_path,
                    "pid": window.pid,
                    "bounds": [window.left, window.top, window.width, window.height],
                    "monitorIndex": window.monitor_index,
                    "monitorDeviceName": window.monitor_device_name,
                    "targetMonitorCoverage": window.target_monitor_coverage,
                },
                "placement": placement,
            }
        else:
            if not args.use_computer and scenario.get("requiresComputerUse"):
                raise SafetyViolation("Scenario requires -UseComputer.")
            result = run_scenario(config, scenario, artifact, state_file)
            if args.collect_logs:
                collect_logs(config, artifact)
            if args.analyze_logs:
                analysis = analyze_run(config, artifact.run_dir, state_file)
                artifact.write_analysis(analysis)
        summary.update(result)
        summary["ok"] = result.get("status") == "ok"
        summary["markers"] = markers
        artifact.write_run(summary)
        print(json.dumps(summary, indent=2))
        return 0 if summary["ok"] else 2
    except Exception as exc:
        summary["ok"] = False
        summary["error"] = str(exc)
        artifact.append_timeline("run_error", error=str(exc), type=type(exc).__name__)
        artifact.write_run(summary)
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 2


def command_collect(args: argparse.Namespace) -> int:
    config = VisionConfig.load(args.config)
    run_dir = Path(args.run) if args.run else None
    artifact = ArtifactWriter(config.artifacts_root, "collect") if run_dir is None else ArtifactWriter.__new__(ArtifactWriter)
    if run_dir is not None:
        artifact.run_dir = run_dir.resolve()
        artifact.logs_dir = artifact.run_dir / "logs"
        artifact.screenshots_dir = artifact.run_dir / "screenshots"
        artifact.timeline_path = artifact.run_dir / "timeline.jsonl"
        artifact.analysis_json_path = artifact.run_dir / "analysis.json"
        artifact.analysis_md_path = artifact.run_dir / "analysis.md"
        artifact.logs_dir.mkdir(parents=True, exist_ok=True)
    manifest = collect_logs(config, artifact)
    print(json.dumps({"ok": True, "runDir": str(artifact.run_dir), "logCount": len(manifest)}, indent=2))
    return 0


def command_analyze(args: argparse.Namespace) -> int:
    config = VisionConfig.load(args.config)
    run_dir = Path(args.run).resolve()
    artifact = ArtifactWriter.__new__(ArtifactWriter)
    artifact.run_dir = run_dir
    artifact.analysis_json_path = run_dir / "analysis.json"
    artifact.analysis_md_path = run_dir / "analysis.md"
    analysis = analyze_run(config, run_dir, state_file_for(config))
    ArtifactWriter.write_analysis(artifact, analysis)
    print(json.dumps({"ok": True, "runDir": str(run_dir), "analysis": analysis}, indent=2))
    return 0


def command_stop(args: argparse.Namespace) -> int:
    config = VisionConfig.load(args.config)
    guard = ProcessGuard(config, state_file_for(config))
    results = guard.stop_recorded()
    print(json.dumps({"ok": True, "stateFile": str(state_file_for(config)), "results": results}, indent=2))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
        errors = validate_scenario(scenario, require_schema_version=not args.allow_legacy_without_version)
        payload = {
            "ok": not errors,
            "scenarioPath": str(Path(args.scenario).expanduser().resolve()),
            "summary": scenario_summary(scenario),
            "errors": errors,
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "scenarioPath": str(Path(args.scenario).expanduser()),
            "errors": [str(exc)],
        }
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 2


def command_monitors(_args: argparse.Namespace) -> int:
    monitors = [monitor.to_dict() for monitor in list_monitors()]
    print(json.dumps({"ok": True, "monitorCount": len(monitors), "monitors": monitors}, indent=2))
    return 0


def command_position_window(args: argparse.Namespace) -> int:
    config = VisionConfig.load(args.config)
    policy = validate_monitor_configuration(config, require_target=True)
    guard = ProcessGuard(config, state_file_for(config))
    guard.validate_spt_root()
    assert_no_denied_processes(config.denied_process_names)
    window, placement = position_target_window(config)
    payload = {
        "ok": True,
        "monitorPolicy": policy,
        "window": {
            "processName": window.process_name,
            "processPath": window.process_path,
            "pid": window.pid,
            "bounds": [window.left, window.top, window.width, window.height],
            "monitorIndex": window.monitor_index,
            "monitorDeviceName": window.monitor_device_name,
            "targetMonitorCoverage": window.target_monitor_coverage,
        },
        "placement": placement,
    }
    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spt-vision-tester")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--scenario")
    run.add_argument("--server-only", action="store_true")
    run.add_argument("--launch-client", action="store_true")
    run.add_argument("--use-computer", action="store_true")
    run.add_argument("--collect-logs", action="store_true")
    run.add_argument("--analyze-logs", action="store_true")
    run.add_argument("--require-scenario-schema", action="store_true")
    run.add_argument("--computer-use-session", action="store_true")
    run.set_defaults(func=command_run)
    collect = sub.add_parser("collect")
    collect.add_argument("--config", required=True)
    collect.add_argument("--run")
    collect.set_defaults(func=command_collect)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--config", required=True)
    analyze.add_argument("--run", required=True)
    analyze.set_defaults(func=command_analyze)
    stop = sub.add_parser("stop")
    stop.add_argument("--config", required=True)
    stop.set_defaults(func=command_stop)
    validate = sub.add_parser("validate-scenario")
    validate.add_argument("--scenario", required=True)
    validate.add_argument("--allow-legacy-without-version", action="store_true")
    validate.set_defaults(func=command_validate)
    monitors = sub.add_parser("monitors")
    monitors.set_defaults(func=command_monitors)
    position = sub.add_parser("position-window")
    position.add_argument("--config", required=True)
    position.set_defaults(func=command_position_window)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
