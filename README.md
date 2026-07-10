# SPT Vision Tester

`spt-vision-tester` is a Codex plugin for repeatable visual smoke tests of a configured local SPT/EFT offline mod installation. It starts only configured SPT components, runs bounded UI scenarios, captures screenshots, collects logs, analyzes likely failures, and stops only processes it recorded.

> [!CAUTION]
> This project is exclusively for local SPT offline testing. Never point it at official Escape from Tarkov, Battlestate Launcher, BattlEye, an online session, or account/login/payment screens. UI scenarios take over the foreground Windows desktop; review every scenario before running it and do not use the computer during automation.

This project is not affiliated with Battlestate Games or the SPT project. It does not modify original game files and must not be used to delete profiles, saves, configs, cache, logs, or mods.

## What it provides

- Server-only startup, readiness checks, log collection, and error analysis.
- A normal local offline Raid scenario.
- A lower-risk local offline Raid scenario that sets AI amount to none and disables bosses.
- A versioned JSON interface for user-defined, allowlisted UI actions.
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

## Start with server-only

Run this after code changes and before any client test:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -ServerOnly -CollectLogs -AnalyzeLogs
```

## Built-in Raid scenarios

Normal local offline Raid:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -AutoRaid
```

Local offline Raid with AI amount set to none and bosses disabled:

```powershell
.\scripts\Start-SptVisionTest.ps1 `
  -ConfigPath .\config\spt-vision-config.json `
  -AutoRaidNoAi
```

The no-AI route was calibrated on SPT 4.0.13, Chinese UI, 2048x1152, where the in-Raid HUD reported `Scav:0 PMC:0 Boss:0`. Percentage coordinates may need recalibration after any resolution, language, UI, game-version, or mod change.

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
