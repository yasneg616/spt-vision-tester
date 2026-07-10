# SPT Vision Tester

`spt-vision-tester` is a Codex plugin for repeatable visual smoke tests of a configured local SPT/EFT offline mod installation. It starts only configured SPT components, runs bounded UI scenarios, captures screenshots, collects logs, analyzes likely failures, and stops only processes it recorded.

> [!CAUTION]
> This project is exclusively for local SPT offline testing. Never point it at official Escape from Tarkov, Battlestate Launcher, BattlEye, an online session, or account/login/payment screens. Multi-monitor placement limits where the SPT window may appear, but Windows keyboard focus and mouse input are still shared across every display.

This project is not affiliated with Battlestate Games or the SPT project. It does not modify original game files and must not be used to delete profiles, saves, configs, cache, logs, or mods.

## What it provides

- Server-only startup, readiness checks, log collection, and error analysis.
- A normal local offline Raid scenario.
- A lower-risk local offline Raid scenario that sets AI amount to none and verifies zero AI counters in Raid.
- A versioned JSON interface for user-defined, allowlisted UI actions.
- Target-monitor discovery, window placement, containment checks, and cooperative desktop input.
- A Computer Use session mode for window-level screenshots and interactive Codex debugging.
- Per-run screenshots, timeline, log manifest, `analysis.md`, and `analysis.json`.
- PID-and-executable identity checks so stop operations target only recorded processes.

## Install

Clone this repository into the source location used by your local Codex plugin marketplace, then install or refresh `spt-vision-tester` from that marketplace. The bundle is identified by `.codex-plugin/plugin.json`.

For direct source use:

```powershell
git clone https://github.com/yasneg616/spt-vision-tester.git
cd .\spt-vision-tester
```

The first start creates a local `.venv` and installs `tools/requirements.txt`. Runtime state, private config, virtual environments, screenshots, logs, and local scenarios are excluded from Git.

## Configure

Copy the safe example:

```powershell
Copy-Item .\config\spt-vision-config.example.json .\config\spt-vision-config.json
```

Set `SptRoot` to the root of your local SPT installation. Do not use the official EFT installation directory. Executable paths may remain blank when the standard SPT names are present.

Client and desktop automation are disabled by default. Enable only the capabilities needed for a reviewed run:

```json
{
  "AllowClientLaunch": true,
  "AllowComputerUse": true,
  "AllowKeyboardMouseInput": true,
  "AllowRaidAutomation": false
}
```

`AllowRaidAutomation` is required only for automated Raid navigation. Keep `AllowTextInput=false`; custom scenarios do not expose text or clipboard actions.

Optional monitor policy is disabled by default:

```json
{
  "TargetMonitorIndex": 2,
  "TargetMonitorDeviceName": "\\\\.\\DISPLAY1",
  "MoveTargetWindowToMonitor": true,
  "RequireTargetWindowOnMonitor": true,
  "TargetMonitorMinCoverage": 0.95,
  "TargetWindowPlacement": "preserve",
  "CooperativeDesktopMode": true,
  "UserIdleSecondsBeforeInput": 1.5,
  "MaxUserIdleWaitSeconds": 30.0,
  "RestoreUserFocusAfterInput": true,
  "RestoreCursorAfterInput": true
}
```

Do not copy a device name blindly. Enumerate the current machine first; index `1` is always the primary monitor, followed by the remaining connected monitors.

## Start with server-only

Run this after code changes and before any client test:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -ServerOnly -CollectLogs -AnalyzeLogs
```

## Multi-monitor Computer Use

List connected displays without launching SPT:

```powershell
.\scripts\Get-SptVisionMonitors.ps1
```

Start the local server and configured launcher, wait for its window, and place it on the configured target monitor without sending UI input:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -ComputerUseSession -CollectLogs -AnalyzeLogs
```

After the launcher starts the game and a new client window appears, re-apply target placement:

```powershell
.\scripts\Move-SptWindowToTargetMonitor.ps1 `
  -ConfigPath .\config\spt-vision-config.json
```

Computer Use can inspect an occluded SPT window through window-level capture without taking focus. Every click or key action still activates that window and uses the shared Windows input desktop. Cooperative mode waits for a user-input quiet period, records and defers an interrupted focus-only handoff, stops if focus or input changes during a click, key, or movement action, and restores the previous focus and cursor only when the user has not intervened.

This is best-effort coexistence, not input isolation. For uninterrupted work on the other displays while an automated Raid continuously uses keyboard and mouse, run SPT in a VM, a separate Windows session with its own interactive desktop, or another machine. See [Multi-Monitor Mode](docs/MULTI_MONITOR.md).

## Built-in Raid scenarios

Normal local offline Raid:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -AutoRaid
```

Local offline Raid with AI amount set to none:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -AutoRaidNoAi
```

The no-AI route was calibrated on SPT 4.0.13, Chinese UI, at 16:9 resolutions including 2560x1440. Selecting AI amount `None` disables the dependent spawn controls; the scenario does not click their grayed checkboxes. The verified in-Raid HUD reported `Scav:0 PMC:0 Boss:0`. Percentage coordinates may need recalibration after any aspect-ratio, language, UI, game-version, or mod change.

Both commands require all relevant local config permissions. They remain local/offline-only and never authorize official EFT interaction.

## Custom action interface

Copy `examples/custom-scenario.example.json`, keep `schemaVersion` set to `1`, and edit only allowlisted steps. Validate it without launching SPT:

```powershell
.\scripts\Test-SptVisionScenario.ps1 `
  -ScenarioPath .\examples\custom-scenario.example.json
```

Run the included validated launcher scenario:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -CustomScenarioPath .\examples\custom-scenario.example.json `
  -LaunchClient -UseComputer -CollectLogs -AnalyzeLogs
```

Add `-LaunchClient` only when the scenario declares `requiresClientLaunch=true` and local config has `AllowClientLaunch=true`. Full format, action fields, limits, and sharing guidance are in [Custom Scenarios](docs/CUSTOM_SCENARIOS.md).

The validator rejects unknown actions and fields, shell commands, arbitrary paths, text/clipboard actions, unsupported keys, out-of-range coordinates, excessive waits, and inconsistent permission declarations. Validation cannot determine whether a valid coordinate is correct for the current screen, so screenshots and human review remain required.

## Stop recorded processes

```powershell
.\scripts\Stop-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json
```

The stop workflow reads only `.spt-vision-tester\started-processes.json`, verifies both PID and executable path, and never kills by process name.

## Emergency stop

Create `EMERGENCY_STOP` in the active run directory:

```powershell
New-Item .\.spt-vision-tester\runs\<run>\EMERGENCY_STOP -ItemType File
```

The configured emergency hotkey remains an operator convention; the file and foreground-process checks are the enforced runtime stops.

## Artifacts

Each run writes under `.spt-vision-tester\runs\<timestamp>-<scenario>\`:

- `run.json`
- `timeline.jsonl`
- `screenshots\`
- `logs\` and `manifest.json`
- `analysis.md` and `analysis.json`
- `detectors.json`

Screenshots and logs can contain private screen content, usernames, mod names, profile identifiers, or local paths. Review artifacts before sharing them.

## Common failures

- `SptRoot` is missing or does not contain enough SPT markers.
- A configured executable resolves outside `SptRoot`.
- `ServerUrl` is unreachable before `StartupTimeoutSeconds`.
- Required client, Computer Use, keyboard/mouse, or Raid permissions are false.
- The foreground window is not owned by an allowed local SPT process.
- The configured monitor index and device name no longer identify the same display.
- The SPT window cannot reach the required target-monitor coverage.
- User input remains active longer than `MaxUserIdleWaitSeconds` in cooperative mode.
- UI coordinates no longer match the current resolution, language, or mod layout.
- A denied official launcher, BattlEye, browser, or unrelated process is detected.
- The scenario exceeds its time/input budget or the emergency stop file exists.

## Non-goals and safety boundaries

- No official online EFT or Battlestate Launcher.
- No account, login, payment, browser, matchmaking, trade, or flea-market automation.
- No modification of original game files.
- No deletion of profiles, saves, configs, cache, logs, or mods.
- No arbitrary command execution through scenario JSON.
- No global process-name termination.
- No hardcoded private SPT paths.
- No claim of per-monitor keyboard or mouse isolation on one Windows desktop.
